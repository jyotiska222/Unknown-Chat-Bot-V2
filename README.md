# Unknown Chat Bot V2

A Telegram bot that enables anonymous chat connections between users. Built with Python, Flask, and Socket.IO.

## Features

- Anonymous chat connections
- Gender preference matching
- Real-time chat monitoring
- Admin dashboard with live statistics
- Beautiful landing page
- Secure and private conversations

## Tech Stack

- Python 3.9+
- Flask & Flask-SocketIO
- Telegram Bot API
- WebSocket for real-time communication
- Modern UI with responsive design

## Setup

1. Clone the repository:
```bash
git clone https://github.com/jyotiska222/Unknown-Chat-Bot-V2.git
cd Unknown-Chat-Bot-V2
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with your configuration:
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_USERNAME=your_admin_username
ADMIN_PASSWORD=your_admin_password
SECRET_KEY=your_secret_key
```

5. Run the application:
```bash
python app.py
```

## Deployment

The bot can be deployed on PythonAnywhere or any other Python hosting service. See deployment instructions in the documentation.

## Admin Dashboard

Access the admin dashboard at `/admin` to:
- Monitor active chats
- View user statistics
- Check system status
- Manage user reports

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 