import os
import sys

# Add your project directory to the sys.path
project_dir = '/home/UnknownChatBot/Unknown-Chat-Bot-V2'
if project_dir not in sys.path:
    sys.path.append(project_dir)

# Add user's local site-packages to Python path for PythonAnywhere
user_site_packages = '/home/UnknownChatBot/.local/lib/python3.13/site-packages'
if user_site_packages not in sys.path:
    sys.insert(0, user_site_packages)

# Change to the project directory
os.chdir(project_dir)

# Import the Flask app
from app import app as application

# This is important for PythonAnywhere WSGI
application.debug = False

# Initialize Socket.IO for production
from bot.shared import socketio
application.config['SECRET_KEY'] = 'your-secret-key-here'  # Set your secret key
application.config['DEBUG'] = False
application = socketio.middleware(application)
