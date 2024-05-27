import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.dispatcher.router import Router
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
import whisper
import openai
import re
import googlemaps
import aiohttp
import csv
import io
import smtplib
import aiofiles
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header
from requests_oauthlib import OAuth2Session
import os
import requests


class EmailStates(StatesGroup):
    awaiting_recipient_name = State()  # New state for recipient's name
    awaiting_sender_email = State()
    awaiting_phone_number = State()
    awaiting_full_name = State()
    awaiting_job_title = State()
    awaiting_company_name = State()
    awaiting_password = State()
    awaiting_email_theme = State()
    awaiting_draft_review = State()
    awaiting_csv_source = State()
    awaiting_csv_upload = State()


class AnswerStates(StatesGroup):
    answer_text = State()
    answer_draft = State()
    answer_correct = State()
    awaiting_sender_email_answer = State()
    awaiting_password_answer = State()


class LinkedInStates(StatesGroup):
    awaiting_search_query = State()
    awaiting_approval = State()
    awaiting_sender_email = State()
    awaiting_password = State()
    awaiting_message_content = State()


# LinkedIn API credentials
LINKEDIN_CLIENT_ID = 'your_client_id'
LINKEDIN_CLIENT_SECRET = 'your_client_secret'
LINKEDIN_REDIRECT_URI = 'https://your.redirect.uri/'
authorization_base_url = 'https://www.linkedin.com/oauth/v2/authorization'
token_url = 'https://www.linkedin.com/oauth/v2/accessToken'

# Define your states
awaiting_email = True


GOOGLE_MAPS_API_KEY = 'AIzaSyCb5dsP-1_Kc7NEkw2sAvQe-WsMFQT4EJM'

# Initialize Google Maps client
gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)

# Set up logging to display information in the console.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot token obtained from BotFather in Telegram.
TOKEN = '7168287295:AAGEBKpR1K3Le_9mCO3H78LNR9XeCRwHrrQ'
bot = Bot(token=TOKEN)
router = Router()
router_email = Router()
router_search = Router()
router_answer = Router()
router_linkedin = Router()

# Load Whisper model
model = whisper.load_model("tiny")

# Set your OpenAI API key here
openai.api_key = 'API_KEY'

# Ключ API и ID поисковой системы для Google Custom Search
GOOGLE_API_KEY = 'AIzaSyCmmg1m0kOMaoRN_k-CHE3_Anf5RbcMOTc'
GOOGLE_CX = 'd040208d062344b7e'

# OAuth2 session for LinkedIn
linkedin = OAuth2Session(LINKEDIN_CLIENT_ID, redirect_uri=LINKEDIN_REDIRECT_URI)

# Define a message handler for the "/start" command.
@router.message(Command("start"))
async def start_message(message: types.Message):
    await message.answer("Hello! Use /search your query by text and after search use /send_email to start sending ")


async def handle_voice(message: types.Message):
    file_info = await bot.get_file(message.voice.file_id)
    file_path = await bot.download_file(file_info.file_path)
    with open("voice_message.ogg", "wb") as f:
        f.write(file_path.read())
    result = model.transcribe("voice_message.ogg")
    text = result['text']
    logger.info(f"Transcribed text from voice: {text}")
    await handle_text_query(message, text)


@router_search.message(Command("search"))
async def handle_text_query(message: types.Message):
    user_input = message.text
    queries = await generate_search_queries(user_input)
    all_results = []
    for query in queries:
        # Очистка запроса: удаление номеров запросов и кавычек
        clean_query = re.sub(r'^\d+\.\s*"', '', query).strip('"')
        if clean_query:  # Ensure query is not empty
            results = await google_search_and_extract(clean_query)
            all_results.extend(results)

    if not all_results:
        await message.answer("No results found.")
        return

    # Combine all results and send them
    response_text = "Here are some companies found:\n\n"
    for name, website, emails in all_results:
        email_list = ", ".join(emails)
        response_text += f"**{name}**:\nWebsite: {website}\nEmails: {email_list}\n\n"
    await send_csv(message.chat.id, all_results)


async def generate_search_queries(user_input):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Generate three diverse search queries for local business information based on the user's input."},
                {"role": "user", "content": user_input}
            ],
            max_tokens=150
        )
        if 'choices' in response and response['choices']:
            full_text = response['choices'][0]['message']['content'].strip()
            queries = full_text.split("\n")  # Splitting by newline to separate the queries
            queries = [query.strip().strip('"') for query in queries if query]  # Clean up each query
            if len(queries) < 3:
                queries += [""] * (3 - len(queries))  # Ensure there are exactly three queries
            logger.info(f"Generated Queries: {queries}")
            return queries
        else:
            logger.warning("No choices returned by GPT-3.")
            return [""] * 3
    except Exception as e:
        logger.error(f"Error generating GPT queries: {str(e)}")
        return [""] * 3


async def google_search_and_extract(query):
    search_result = await fetch_places(query)
    info = await process_search_results(search_result)
    # Пока существует токен следующей страницы, продолжаем делать запросы
    while 'next_page_token' in search_result:
        await asyncio.sleep(5)  # Google требует задержку перед использованием токена следующей страницы
        search_result = await fetch_places(query, search_result['next_page_token'])

        # Обработка полученных результатов
        more_info = await process_search_results(search_result)
        info.extend(more_info)

    return info


async def fetch_places(query, page_token=None):
    """Отправляет запрос к Google Places API и возвращает результаты."""
    try:
        if page_token:
            # Запрос следующей страницы результатов
            return gmaps.places(query=query, page_token=page_token)
        else:
            # Первоначальный запрос
            return gmaps.places(query=query)
    except Exception as e:
        logger.error(f"Error during fetching places: {str(e)}")
        return {}  # Возвращаем пустой словарь в случае ошибки


async def process_search_results(search_result):
    info = []
    if search_result['status'] == 'OK':
        async with aiohttp.ClientSession() as session:
            tasks = []
            for place in search_result['results']:
                place_id = place['place_id']
                place_details = gmaps.place(place_id=place_id, fields=['name', 'website'])
                company_name = place_details['result'].get('name')
                website = place_details['result'].get('website', 'No website found')
                if website != 'No website found':
                    task = (company_name, website, fetch_and_parse_website(session, website))
                    tasks.append(task)

            results = await asyncio.gather(*[t[2] for t in tasks])
            for (company_name, website, _), emails in zip(tasks, results):
                if emails:  # Добавляем сайты, где найдены email
                    info.append((company_name, website, emails))

    return info


async def fetch_and_parse_website(session, url):
    try:
        async with session.get(url) as response:
            html_content = await response.text()
            emails = parse_html(html_content)
            return emails
    except Exception as e:
        logger.error(f"Error fetching or parsing {url}: {str(e)}")
        return []


def parse_html(html_content):
    emails = set(re.findall(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]{2,}\b", html_content))
    return filter_emails(emails)


def filter_emails(emails):
    ignore_patterns = [
        r'sentry\..+',
        r'wixpress\.com',
        r'polyfill\.io',
        r'lodash\.com',
        r'core-js-bundle\.com',
        r'react-dom\.com',
        r'react\.com',
        r'npm\.js',
        r'@[a-zA-Z0-9]*[0-9]{5,}@',
        r'\b[a-zA-Z]+@[0-9]+\.[0-9]+\.[0-9]+\b',
        r'@\w*\.png',
        r'@\w*\.jpg',
        r'@\w*\.jpeg',
        r'@\w*\.gif',
        r'\w+-v\d+@3x-\d+x\d+\.png',
        r'\w+-v\d+@3x-\d+x\d+\.png.webp',
        r'[a-zA-Z0-9_\-]+@[0-9]+x[0-9]+\.png',
        r'[a-zA-Z0-9_\-]+@[0-9]+x[0-9]+\.jpeg',
        r'[a-zA-Z0-9_\-]+@[0-9]+x[0-9]+\.png.webp',
        r'[a-zA-Z0-9_\-]+@[\d]+x[\d]+\.png',
        r'[a-zA-Z0-9_\-]+@\d+x\d+\.(png|jpg|jpeg|gif)',
        r'[a-zA-Z0-9_\-]+-v\d+_?\d*@[0-9]+x[0-9]+\.png',
        r'[a-zA-Z0-9_\-]+-v\d+_?\d*@[0-9]+x[0-9]+\.png.webp',
        r'IASC',
        r'@\w*\.png.webp',
        r'Mesa-de-trabajo'
    ]
    return [email for email in emails if not any(re.search(pattern, email) for pattern in ignore_patterns)]


async def send_csv(chat_id, data):
    # Создаем CSV файл в памяти
    output = io.StringIO()
    writer = csv.writer(output)
    # Записываем заголовки
    writer.writerow(['Company Name', 'Website', 'Emails'])
    # Записываем данные
    for name, website, emails in data:
        writer.writerow([name, website, ', '.join(emails)])
    # Перемещаем указатель в начало файла
    output.seek(0)
    # Создаем объект FormData
    form_data = aiohttp.FormData()
    form_data.add_field('document', output, filename='companies.csv')
    # Отправляем CSV файл
    async with aiohttp.ClientSession() as session:
        async with session.post(f'https://api.telegram.org/bot{TOKEN}/sendDocument?chat_id={chat_id}',
                                data=form_data) as resp:
            if resp.status != 200:
                print(await resp.text())


# Function to search LinkedIn for people
# Step 1: User Authorization
@router.message(Command("linkedin_search"))
async def linkedin_auth(message: types.Message, state: FSMContext):
    authorization_url, state_token = linkedin.authorization_url(authorization_base_url)
    await message.answer(f"Please go to this URL to authorize access:\n{authorization_url}")
    await state.update_data(state_token=state_token)
    await state.set_state(LinkedInStates.awaiting_auth)

# Step 2: Handling the callback with authorization code
@router.message(LinkedInStates.awaiting_auth)
async def linkedin_callback(message: types.Message, state: FSMContext):
    state_token = (await state.get_data())['state_token']
    linkedin = OAuth2Session(LINKEDIN_CLIENT_ID, state=state_token, redirect_uri=LINKEDIN_REDIRECT_URI)

    code = extract_code_from_message(message.text)
    token = linkedin.fetch_token(token_url, client_secret=LINKEDIN_CLIENT_SECRET, code=code)
    os.environ['LINKEDIN_ACCESS_TOKEN'] = token['access_token']

    await message.answer("LinkedIn authentication successful. Please enter your search query for LinkedIn:")
    await state.set_state(LinkedInStates.awaiting_search_query)

def extract_code_from_message(text):
    return text.split('code=')[1].split('&')[0]

# Function to search people on LinkedIn
async def linkedin_search(query):
    access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    search_url = f"https://api.linkedin.com/v2/search?q=people&keywords={query}"
    response = requests.get(search_url, headers=headers)
    data = response.json()
    results = []
    for result in data['elements']:
        name = result['title']['text']
        profile_url = f"https://www.linkedin.com/in/{result['publicIdentifier']}"
        results.append((name, profile_url))
    return results

# Handle the LinkedIn search query input from the user
@router.message(LinkedInStates.awaiting_search_query)
async def handle_linkedin_search_query(message: types.Message, state: FSMContext):
    query = message.text
    results = await linkedin_search(query)

    if not results:
        await message.answer("No results found on LinkedIn.")
        await state.clear()
        return

    response_text = "Here are some people found on LinkedIn:\n\n"
    for name, profile_url in results:
        response_text += f"**{name}**:\nProfile: {profile_url}\n\n"
    await message.answer(response_text)
    await message.answer("If you approve these results, type 'yes' to proceed with messaging, or 'no' to cancel.")
    await state.set_state(LinkedInStates.awaiting_approval)
    await state.update_data(linkedin_results=results)

# Handle approval for messaging
@router.message(LinkedInStates.awaiting_approval)
async def handle_approval(message: types.Message, state: FSMContext):
    if message.text.lower() == 'yes':
        await message.answer("Please enter your email address for sending messages:")
        await state.set_state(LinkedInStates.awaiting_sender_email)
    else:
        await message.answer("LinkedIn search cancelled.")
        await state.clear()

# Handle the email address input for sending messages
@router.message(LinkedInStates.awaiting_sender_email)
async def handle_sender_email(message: types.Message, state: FSMContext):
    sender_email = message.text
    if is_valid_email(sender_email):
        await state.update_data(sender_email=sender_email)
        await message.answer("Please enter your password for SMTP authentication:")
        await state.set_state(LinkedInStates.awaiting_password)
    else:
        await message.answer("Please enter a valid email address.")

# Handle the password input for SMTP authentication
@router.message(LinkedInStates.awaiting_password)
async def handle_password(message: types.Message, state: FSMContext):
    password = message.text
    await state.update_data(password=password)
    await message.answer("Password set. Please enter the message content you want to send:")
    await state.set_state(LinkedInStates.awaiting_message_content)

# Handle the message content input
@router.message(LinkedInStates.awaiting_message_content)
async def handle_message_content(message: types.Message, state: FSMContext):
    content = message.text
    data = await state.get_data()
    sender_email = data['sender_email']
    password = data['password']
    linkedin_results = data['linkedin_results']

    await message.answer("Sending messages...")

    for name, profile_url in linkedin_results:
        personalized_content = content.replace("[Recipient's Name]", name)
        success = await send_linkedin_message(profile_url, personalized_content)
        if success:
            await message.answer(f"Message sent to {name} ({profile_url})")
        else:
            await message.answer(f"Failed to send message to {name} ({profile_url})")

    await message.answer("Messages have been sent successfully.")
    await state.clear()

# Function to send messages on LinkedIn
async def send_linkedin_message(recipient_profile_url, message_content):
    access_token = os.getenv('LINKEDIN_ACCESS_TOKEN')
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    recipient_id = recipient_profile_url.split('/')[-1]  # Extract the profile ID from the URL
    message_url = f"https://api.linkedin.com/v2/messages"
    payload = {
        "recipients": [recipient_id],
        "subject": "Message Subject",
        "body": message_content
    }

    response = requests.post(message_url, headers=headers, json=payload)
    return response.status_code == 201


# Start the command to input the sender's email address
@router.message(Command("send_email"))
async def send_email_command(message: types.Message, state: FSMContext):
    await message.answer("Please enter your email address:")
    await state.set_state(EmailStates.awaiting_sender_email)


# Utility function to validate an email address format
def is_valid_email(email):
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None


# Handle the email address input from the user
@router.message(EmailStates.awaiting_sender_email)
async def handle_sender_email(message: types.Message, state: FSMContext):
    sender_email = message.text
    if is_valid_email(sender_email):
        await message.answer("Sender email set. Please enter your phone number:")
        await state.update_data(sender_email=sender_email)
        await state.set_state(EmailStates.awaiting_phone_number)
    else:
        await message.answer("Please enter a valid email address.")


# Handle the phone number input from the user
@router.message(EmailStates.awaiting_phone_number)
async def handle_phone_number(message: types.Message, state: FSMContext):
    phone_number = message.text
    await state.update_data(phone_number=phone_number)
    await message.answer("Phone number set. Please enter your password for SMTP authentication:")
    await state.set_state(EmailStates.awaiting_password)


# Handle the password input for SMTP authentication
@router.message(EmailStates.awaiting_password)
async def handle_password(message: types.Message, state: FSMContext):
    password = message.text
    await state.update_data(password=password)
    await message.answer("Password set. What is the theme or main content for your email?(Write your Name.Surname.Job title.Company Name.")
    await state.set_state(EmailStates.awaiting_email_theme)


# Handle the email theme/content input and generate a draft using OpenAI
@router.message(EmailStates.awaiting_email_theme)
async def handle_email_theme(message: types.Message, state: FSMContext):
    prompt = message.text
    data = await state.get_data()
    sender_email = data['sender_email']
    phone_number = data['phone_number']
    draft = await generate_email_content(prompt, sender_email, phone_number)
    if draft:
        await message.answer("Here is a draft based on your input:\n{}\nDo you approve this draft? Type 'yes' to approve, or provide your corrections.".format(draft))
        await state.update_data(draft=draft)
        await state.set_state(EmailStates.awaiting_draft_review)
    else:
        await message.answer("Failed to generate draft, please try entering the theme again.")


async def generate_email_content(prompt, sender_email, phone_number):
    try:
        # Generate the email content
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a skilled email writer. Create a professional business email based on the user's provided theme. "
                        "The email should be concise, polite, and aimed at establishing a professional relationship. Use a formal tone "
                        "and structure the email with appropriate greetings , body content Don't use placeholders like [Recipient's Company] or [specific industry/field], and sign-off."
                        "details of the sender. Ensure the email is structured into clear paragraphs with a maximum of 300 tokens. "
                        "Don't use placeholders like [Recipient's Company] or [specific industry/field].use only [Recipient's Name]"
                        "Separate each paragraph with two newlines."
                        "Don't write contact information."

                    )
                },
                {
                    "role": "user",
                    "content": f"Theme: {prompt}. Please include placeholders for the recipient's name and company."
                }
            ],
            max_tokens=300
        )

        content = response.choices[0].message['content'].strip()

        # Extracting a suitable header from the prompt
        header_response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a skilled email writer. Based on the provided theme, generate a suitable and concise email subject line.Example:Exploring Partnership Opportunities with ... "
                        "The subject should be clear, engaging, and relevant to the email content. Keep it short, ideally within 60 characters."
                    )
                },
                {
                    "role": "user",
                    "content": f"Theme: {prompt}"
                }
            ],
            max_tokens=60
        )

        header = header_response.choices[0].message['content'].strip()

        # Split content into paragraphs
        paragraphs = content.split('\n\n')
        formatted_content = ''.join(f'<p>{para}</p>' for para in paragraphs)

        # Construct the HTML email content with a dynamic header
        html_content = f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                }}
                .header {{
                    background-color: #f8f8f8;
                    padding: 10px;
                    text-align: center;
                    border-bottom: 1px solid #ddd;
                }}
                .content {{
                    padding: 20px;
                }}
                .footer {{
                    padding: 10px;
                    text-align: center;
                    border-top: 1px solid #ddd;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{header}</h1>
            </div>
            <div class="content">
                {formatted_content}
            </div>
            <div class="footer">
                <p>Phone: {phone_number}</p>
                <p>Email: {sender_email}</p>
            </div>
        </body>
        </html>
        """

        return html_content
    except Exception as e:
        print(f"Error generating email content: {str(e)}")
        return None


# Handle the review and approval of the generated email draft
@router.message(EmailStates.awaiting_draft_review)
async def handle_draft_review(message: types.Message, state: FSMContext):
    if message.text:
        response = message.text.lower()
        if response == 'yes':
            await message.answer("Please type 'upload' to upload your CSV or 'default' to use the default CSV.")
            await state.set_state(EmailStates.awaiting_csv_source)
        else:
            await state.update_data(draft=response)
            await message.answer("Draft updated. Type 'yes' to send or provide further corrections.")
    else:
        await message.answer("Please send a text response.")


# Handle the selection between uploading a new CSV file or using a default CSV file
@router.message(EmailStates.awaiting_csv_source)
async def choose_csv_source(message: types.Message, state: FSMContext):
    if message.text:
        user_input = message.text.lower()
        if user_input == 'upload':
            await message.answer("Please upload your CSV file.")
            await state.set_state(EmailStates.awaiting_csv_upload)
        elif user_input == 'default':
            data = await state.get_data()
            sender_email = data['sender_email']
            sender_password = data['password']
            draft = data['draft']
            await send_emails_from_csv(sender_email, sender_password, 'Subject of your emails', draft, "default.csv")
            await message.answer("Emails have been sent successfully using the default CSV.")
            await state.clear()
        else:
            await message.answer("Please type 'upload' to upload your CSV or 'default' to use the default CSV.")
    else:
        await message.answer("Please send a text message indicating your choice.")


# Updated handler to upload a CSV file and send emails
@router.message(EmailStates.awaiting_csv_upload)
async def handle_document(message: types.Message, state: FSMContext):
    if message.document:
        document_id = message.document.file_id
        file_info = await bot.get_file(document_id)
        file_path = await bot.download_file(file_info.file_path)

        unique_filename = f"user_uploaded_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

        async with aiofiles.open(unique_filename, "wb") as f:
            await f.write(file_path.read())
            await f.close()

        data = await state.get_data()
        sender_email = data['sender_email']
        sender_password = data['password']
        draft = data['draft']
        await send_emails_from_csv(sender_email, sender_password, 'Subject of your emails', draft, unique_filename)
        await message.answer(f"Emails have been sent successfully using your uploaded CSV: {unique_filename}.")
        await state.clear()
    else:
        await message.answer("Please upload a CSV file.")


# Function to send an email via SMTP
def send_email(sender_email, sender_password, recipient_email, subject, content):
    print("Preparing message content...")

    # Create the email message object with UTF-8 encoding
    msg = MIMEText(content, 'html', 'utf-8')

    # Set other headers with UTF-8 encoding
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender_email
    msg['To'] = recipient_email

    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    try:
        print("Connecting to SMTP server...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            print("Logging in...")
            server.login(sender_email, sender_password)
            print("Sending email...")
            server.send_message(msg)
            print(f"Email successfully sent to {recipient_email} using {smtp_server}!")
            return True
    except Exception as e:
        print(f"Failed to send email via {smtp_server}: {str(e)}")
        return False

# Updated function to read email addresses from a CSV file and send emails asynchronously
async def send_emails_from_csv(sender_email, sender_password, subject, content, csv_filename):
    """Asynchronously read email addresses from a CSV file and send emails via Gmail SMTP."""
    success_count = 0
    fail_count = 0

    try:
        async with aiofiles.open(csv_filename, mode='r', encoding='utf-8') as csvfile:
            contents = await csvfile.read()
            reader = csv.reader(contents.splitlines(), delimiter=';')
            next(reader)  # Skip the header

            for row in reader:
                print(f"Processing row: {row}")
                if len(row) >= 3:
                    recipient_name = row[0]  # Extract the recipient name from the first column
                    company_name = row[1]    # Extract the company name from the second column
                    recipient_email = row[2]  # Extract the email from the third column

                    # Replace placeholders in the email content
                    personalized_content = content.replace("[Recipient's Name]", recipient_name).replace("[company name]", company_name)

                    success = send_email(sender_email, sender_password, recipient_email, subject, personalized_content)
                    if success:
                        success_count += 1
                        print(f"Email successfully sent to {recipient_email}")
                    else:
                        fail_count += 1
                else:
                    print('Incomplete row found, skipping...')

    except Exception as e:
        print(f"Error reading file or processing data: {str(e)}")

    print(f"Total emails processed: {success_count + fail_count}, Sent: {success_count}, Failed: {fail_count}")


@router.message(Command("send_answer"))
async def send_email_command(message: types.Message, state: FSMContext):
    await message.answer("Hello! Please enter your text, I will write an answer:")
    await state.set_state(AnswerStates.answer_text)


@router.message(AnswerStates.answer_text)
async def answer_text(message: types.Message, state: FSMContext):
    user_text = message.text

    # Extract email address from the user's message
    email_match = re.search(r'\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b', user_text)
    if email_match:
        recipient_email = email_match.group(0)
    else:
        await message.answer("Could not find an email address in your message. Please include an email address.")
        return

    draft = await generate_answer_draft(user_text)
    await state.update_data(draft=draft, recipient_email=recipient_email)
    await message.answer(
        f"Here is the draft of your answer:\n{draft}\nIf it looks good, type 'yes' to proceed. If you need to make changes, type your corrections.")
    await state.set_state(AnswerStates.answer_draft)


async def generate_answer_draft(text):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Create a professional and polite response to the following inquiry"
                                              "Don't use placeholders!!!"
                                              "Ensure that each paragraph is separated by a blank line for clear readability."
                                              "Don't write contact information."
                                              "Don't use placeholders [Your Full Name],[Your Position],[Your Name]"},
                {"role": "user", "content": text}
            ],
            max_tokens=300
        )
        content = response.choices[0].message['content'].strip()
        # Split content into paragraphs
        paragraphs = content.split('\n\n')
        formatted_content = ''.join(f'<p>{para}</p>' for para in paragraphs)
        return formatted_content
    except Exception as e:
        print(f"Error generating answer draft: {str(e)}")
        return "Sorry, I couldn't generate a draft due to an error."


@router.message(AnswerStates.answer_draft)
async def draft_review(message: types.Message, state: FSMContext):
    response = message.text.lower()
    if response == 'yes':
        await message.answer("Please enter the email address you want to use for sending the email:")
        await state.set_state(AnswerStates.awaiting_sender_email_answer)
    else:
        await state.update_data(draft=response)
        await message.answer(
            "Draft updated. Please review and type 'yes' to send, or continue to make further corrections.")
        await state.set_state(AnswerStates.answer_correct)


@router.message(AnswerStates.awaiting_sender_email_answer)
async def handle_sender_email(message: types.Message, state: FSMContext):
    sender_email = message.text
    if is_valid_email(sender_email):
        await state.update_data(sender_email=sender_email)
        await message.answer("Sender email set. Please enter the password for SMTP authentication:")
        await state.set_state(AnswerStates.awaiting_password_answer)
    else:
        await message.answer("Please enter a valid email address.")


@router.message(AnswerStates.awaiting_password_answer)
async def handle_password(message: types.Message, state: FSMContext):
    password = message.text
    await state.update_data(password=password)

    # Proceed to send the email
    data = await state.get_data()
    draft = data['draft']
    recipient_email = data['recipient_email']
    sender_email = data['sender_email']
    sender_password = data['password']

    subject = "Response to your inquiry"
    success = send_email_answer(sender_email, sender_password, recipient_email, subject, draft)
    if success:
        await message.answer(f"Your answer has been sent to {recipient_email}.")
    else:
        await message.answer("Failed to send the email. Please try again later.")

    await state.clear()  # Clear the state


# Function to send an email via SMTP
def send_email_answer(sender_email, sender_password, recipient_email, subject, content):
    print("Preparing message content...")

    # Create the email message object with UTF-8 encoding
    msg = MIMEText(content, 'html', 'utf-8')

    # Set other headers with UTF-8 encoding
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = sender_email
    msg['To'] = recipient_email

    smtp_server = "smtp.gmail.com"
    smtp_port = 587

    try:
        print("Connecting to SMTP server...")
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            print("Logging in...")
            server.login(sender_email, sender_password)
            print("Sending email...")
            server.send_message(msg)
            print(f"Email successfully sent to {recipient_email} using {smtp_server}!")
            return True
    except Exception as e:
        print(f"Failed to send email via {smtp_server}: {str(e)}")
        return False


def is_valid_email_answer(email):
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None


# Main function to start the bot.
async def main():
    dp = Dispatcher()
    dp.include_router(router)
    dp.include_router(router_email)
    dp.include_router(router_search)
    dp.include_router(router_answer)
    dp.include_router(router_linkedin)
    await dp.start_polling(bot)


if __name__ == '__main__':
    # Initialize the email list
    email_list = []
    asyncio.run(main())
