# Comprehensive Telegram Bot

This Telegram bot provides a wide range of functionalities including local business search, email generation and sending, and LinkedIn search and messaging. The bot leverages several APIs and libraries to deliver these features seamlessly.

## Features

- **Local Business Search**: Search for local businesses using Google Maps API.
- **Email Generation and Sending**: Generate email drafts using OpenAI's GPT-4 and send emails via SMTP.
- **Voice and Text Queries**: Handle both voice and text input from users.
- **LinkedIn Search and Messaging**: Search for people on LinkedIn and send personalized messages using LinkedIn API.

## Setup and Installation

### Prerequisites

- Python 3.8+
- Telegram Bot Token from BotFather
- LinkedIn API credentials (Client ID and Client Secret)
- Google Maps API Key
- OpenAI API Key

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/your-repo.git
   cd your-repo
Create a virtual environment:

bash
Копировать код
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
Install dependencies:

bash
Копировать код
pip install -r requirements.txt
Create a .env file in the project root and add the following variables:

env
Копировать код
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
LINKEDIN_CLIENT_ID=your_linkedin_client_id
LINKEDIN_CLIENT_SECRET=your_linkedin_client_secret
LINKEDIN_REDIRECT_URI=https://your.redirect.uri/
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
OPENAI_API_KEY=your_openai_api_key
Running the Bot
Run the bot:
bash
Копировать код
python main.py
Functionality Overview

Local Business Search
Command: /search
Description: Searches for local businesses based on the user's query.
Workflow:
User sends /search <query>.
Bot generates search queries using OpenAI.
Bot fetches business information from Google Maps API.
Bot displays the results and optionally sends them in a CSV file.
Email Generation and Sending
Command: /send_email
Description: Generates and sends emails based on user-provided information.
Workflow:
User sends /send_email.
Bot collects sender's email, phone number, and password.
User provides email theme/content.
Bot generates an email draft using OpenAI.
User reviews and approves the draft.
Bot sends emails to recipients listed in a CSV file.
LinkedIn Search and Messaging
Command: /linkedin_search
Description: Searches for people on LinkedIn and sends messages.
Workflow:
User sends /linkedin_search.
Bot initiates LinkedIn OAuth 2.0 authentication.
User provides the authorization code.
Bot performs LinkedIn search based on user query.
Bot displays the results and asks for approval to send messages.
User provides email content.
Bot sends personalized messages to the found LinkedIn profiles.
Project Structure

graphql
Копировать код
your-repo/
│
├── main.py                    # Main entry point of the bot
├── requirements.txt           # List of dependencies
├── .env                       # Environment variables
├── README.md                  # Project documentation
│
└── your_bot/
    ├── __init__.py
    ├── handlers/
    │   ├── __init__.py
    │   ├── search_handler.py  # Handles business search functionality
    │   ├── email_handler.py   # Handles email generation and sending
    │   ├── linkedin_handler.py# Handles LinkedIn search and messaging
    │
    ├── utils/
    │   ├── __init__.py
    │   ├── google_maps.py     # Google Maps API integration
    │   ├── openai_utils.py    # OpenAI API integration
    │   ├── linkedin_api.py    # LinkedIn API integration
    │   ├── email_utils.py     # Email utilities
    │
    └── config.py              # Configuration and environment variables
Dependencies

aiogram: For Telegram bot interactions
aiohttp: For asynchronous HTTP requests
requests: For HTTP requests
requests-oauthlib: For OAuth 2.0 authentication
beautifulsoup4: For web scraping
whisper: For voice-to-text transcription
openai: For OpenAI API integration
googlemaps: For Google Maps API integration
python-dotenv: For managing environment variables
Contributing

Contributions are welcome! Please open an issue or submit a pull request.
