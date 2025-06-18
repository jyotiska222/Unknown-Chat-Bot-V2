from flask_socketio import SocketIO

# Initialize SocketIO instance to be shared across modules
# Don't create Flask app here, it will be created in app.py
socketio = SocketIO(async_mode='gevent')
