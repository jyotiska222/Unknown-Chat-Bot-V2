import os
import sys

# Add your project directory to the sys.path
project_home = '/home/yourusername/Unknown-Chat-Bot-V2'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# Import your Flask app
from app import app as application

# Initialize the polling and cleanup threads
if os.environ.get('PYTHONANYWHERE_DOMAIN'):
    import threading
    from app import cleanup_inactive_users, polling_thread
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_inactive_users, daemon=True)
    cleanup_thread.start()
    
    # Start polling thread
    bot_thread = threading.Thread(target=polling_thread, daemon=True)
    bot_thread.start() 