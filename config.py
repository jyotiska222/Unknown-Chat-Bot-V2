import os
from dotenv import load_dotenv

# Load environment variables from credentials.txt
load_dotenv('credentials.txt')

class Config:
    # Flask settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    DEBUG = False  # Force debug to False to prevent duplicate messages
    
    # Telegram settings
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')
    TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    
    # Data storage settings
    DATA_DIR = 'data'
    USERS_FILE = os.path.join(DATA_DIR, 'users.json')
    CHATS_FILE = os.path.join(DATA_DIR, 'chats.json')
    BROADCASTS_FILE = os.path.join(DATA_DIR, 'broadcasts.json')
    
    # Admin credentials
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'password')
    
    # Chat settings
    CHAT_TIMEOUT = 3600  # 1 hour in seconds
    MAX_WAITING_TIME = 300  # 5 minutes in seconds
    
    # Rate limiting settings
    RATE_LIMIT_MESSAGES = 5  # messages per RATE_LIMIT_WINDOW
    RATE_LIMIT_WINDOW = 3  # seconds
    RATE_LIMIT_COMMANDS = 3  # commands per RATE_LIMIT_COMMAND_WINDOW
    RATE_LIMIT_COMMAND_WINDOW = 10  # seconds
    
    # Error handling settings
    MAX_RETRIES = 5
    RETRY_DELAY = 5  # seconds
    
    # Cleanup settings
    CLEANUP_INTERVAL = 300  # 5 minutes
    INACTIVE_TIMEOUT = 1800  # 30 minutes
    
    # Network settings
    POLLING_TIMEOUT = 30  # seconds for long polling
    CONNECT_TIMEOUT = 20  # seconds for connection establishment
    READ_TIMEOUT = 40  # seconds for reading response
    SOCKET_TIMEOUT = 90  # seconds for socket operations
    
    # Connection pool settings
    MAX_CONNECTIONS = 20
    KEEP_ALIVE = True
    
    @staticmethod
    def init_app(app):
        # Create necessary directories
        os.makedirs(Config.DATA_DIR, exist_ok=True)
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        
        # Initialize empty JSON files if they don't exist
        for file_path in [Config.USERS_FILE, Config.CHATS_FILE, Config.BROADCASTS_FILE]:
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('{}') 