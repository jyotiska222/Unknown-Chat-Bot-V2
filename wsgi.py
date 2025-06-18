import os
import sys

# Add your project directory to the sys.path
project_dir = '/home/UnknownChatBot/Unknown-Chat-Bot-V2'
if project_dir not in sys.path:
    sys.path.append(project_dir)

# Change to the project directory
os.chdir(project_dir)

# Import the Flask app
from app import app as application

# Configure the application
application.config['DEBUG'] = False
