import os
import sys

# Add your project directory to the sys.path
project_dir = '/home/UnknownChatBot/Unknown-Chat-Bot-V2'
if project_dir not in sys.path:
    sys.path.append(project_dir)

# Add user's local site-packages to Python path for PythonAnywhere
user_site_packages = '/home/UnknownChatBot/.local/lib/python3.9/site-packages'
if user_site_packages not in sys.path:
    sys.path.insert(0, user_site_packages)

# Change to the project directory
os.chdir(project_dir)

# Import Flask app and socketio
from app import app
from bot.shared import socketio

# Configure the application
app.config['SECRET_KEY'] = '85d1d239f67b5c8a0b1e7c2d3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2'
app.config['DEBUG'] = False

# Initialize Socket.IO with the app
socketio.init_app(app)

# This is the WSGI application
application = app
