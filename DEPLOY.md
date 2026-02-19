# 🎮 Eventometer - ATC Booking System

A comprehensive Discord bot and Django web application for managing VATSIM event ATC position bookings.

## 🚀 Features

- **Discord Integration**: Bot for event announcements and booking interactions
- **VATSIM API Integration**: Automatic event imports and user verification
- **ATC Position Booking**: Multi-slot, multi-position booking system
- **Admin Dashboard**: Full Django admin interface for event management
- **Notification System**: Automated DMs and fallback channel creation
- **Real-time Updates**: Announcement messages update as positions are filled

---

## 📋 Prerequisites

- Python 3.12+
- PostgreSQL database (provided by Railway)
- Discord Bot Token ([Create one here](https://discord.com/developers/applications))
- VATSIM API access (optional)

---

## 🚂 Deploy to Railway

### 1. Create a Railway Account
- Go to [Railway.app](https://railway.app) and sign up
- Create a new project

### 2. Add PostgreSQL Database
- In your Railway project, click **"New"** → **"Database"** → **"PostgreSQL"**
- Railway will automatically set the `DATABASE_URL` environment variable

### 3. Deploy the Application
- Click **"New"** → **"GitHub Repo"** (or deploy from CLI)
- Select this repository
- Railway will automatically detect the Python app and deploy

### 4. Configure Environment Variables
Go to your Railway service → **Variables** and add:

```bash
# Required Variables
SECRET_KEY=<generate-a-long-random-string>
DEBUG=False
ALLOWED_HOSTS=your-app.up.railway.app

DISCORD_TOKEN=<your-bot-token>
DISCORD_GUILD_ID=<your-server-id>
DISCORD_FALLBACK_CATEGORY_ID=<category-id-for-fallback-channels>

# Optional (defaults are usually fine)
VATSIM_EVENTS_URL=https://my.vatsim.net/api/v2/events/latest
VATSIM_API_BASE=https://api.vatsim.net/v2
```

### 5. Generate Django Secret Key
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 6. Create Superuser (After First Deploy)
In Railway, go to your service → **Deployments** → Click on the latest deployment → **View Logs**, then run:
```bash
railway run python manage.py createsuperuser
```

### 7. Access Admin Panel
- Visit: `https://your-app.up.railway.app/admin/`
- Login with superuser credentials

### 8. Link Admin Discord Account
1. In Django admin, go to **Admin Profiles**
2. Create an entry linking your Django user to your Discord ID
   - Get your Discord ID: Enable Developer Mode → Right-click your name → Copy ID
   - This allows you to use admin commands in Discord

---

## 🎯 Discord Bot Setup

### Create Discord Bot
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **"New Application"** → Name it "Eventometer"
3. Go to **"Bot"** → Click **"Add Bot"**
4. Copy the bot token (use in `DISCORD_TOKEN` env variable)
5. Enable these **Privileged Gateway Intents**:
   - Server Members Intent
   - Message Content Intent

### Invite Bot to Server
1. Go to **OAuth2** → **URL Generator**
2. Select scopes:
   - `bot`
   - `applications.commands`
3. Select bot permissions:
   - Manage Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Slash Commands
4. Copy the generated URL and open it to invite the bot

### Setup Fallback Category
1. Create a category in your Discord server (e.g., "📩 Notifications")
2. Right-click → Copy ID → Use in `DISCORD_FALLBACK_CATEGORY_ID`
3. Ensure bot has **Manage Channels** permission in this category

---

## 🎮 Usage

### Admin Commands (Discord Slash Commands)

| Command | Description |
|---------|-------------|
| `/importar` | Import event from VATSIM by ID |
| `/configurar_blocos` | Set time block duration for an event |
| `/adicionar_icao` | Add ICAO codes to an event |
| `/adicionar_posicao` | Add ATC positions to event ICAOs |
| `/abrir_bookings` | Open event for member bookings |
| `/anunciar` | Announce event in a channel |
| `/status_evento` | View booking statistics |

### User Commands

| Command | Description |
|---------|-------------|
| `/eventos` | Browse open events and apply for positions |
| `/revogar` | Revoke pending applications |

### Admin Workflow
1. **Import Event**: `/importar event_id:18010`
2. **Configure Time Blocks**: `/configurar_blocos event_id:18010 duracao:60`
3. **Add ICAOs**: `/adicionar_icao event_id:18010 icaos:SBBR,SBSP,SBGR`
4. **Add Positions**: `/adicionar_posicao event_id:18010` (interactive)
5. **Open for Bookings**: `/abrir_bookings event_id:18010`
6. **Announce**: `/anunciar canal:#eventos`

### Django Admin
- **Events**: Manage events, view booking matrix
- **Booking Applications**: Lock/confirm users, send notifications
- **Position Templates**: Create reusable ATC positions (TWR, APP, GND, etc.)
- **Users**: View VATSIM user data and statistics

---

## 🔧 Local Development

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd eventometer
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
# Edit .env with your values
```

### 5. Run Migrations
```bash
python manage.py migrate
```

### 6. Create Superuser
```bash
python manage.py createsuperuser
```

### 7. Run Development Servers
```bash
# Terminal 1: Django
python manage.py runserver

# Terminal 2: Discord Bot
python manage.py runbot
```

---

## 📁 Project Structure

```
eventometer/
├── bot/                      # Discord bot application
│   ├── cogs/
│   │   ├── admin_cmds.py    # Admin slash commands
│   │   ├── booking.py       # User booking flow
│   │   ├── notifications.py # DM notification system
│   │   └── strings.py       # Localized messages & embeds
│   ├── management/commands/
│   │   └── runbot.py        # Bot startup command
│   └── apps.py
├── core/                     # Django core application
│   ├── models.py            # Database models
│   ├── admin.py             # Django admin customizations
│   ├── vatsim.py            # VATSIM API integration
│   └── views.py
├── eventometer/             # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── templates/               # Django admin templates
├── manage.py
├── requirements.txt
├── Procfile                 # Railway deployment config
├── railway.json             # Railway configuration
├── runtime.txt              # Python version
└── .env.example             # Environment variables template
```

---

## 🔐 Security Notes

- Never commit `.env` file to git
- Use strong `SECRET_KEY` in production
- Keep `DEBUG=False` in production
- Restrict `ALLOWED_HOSTS` to your domains
- Enable all security headers in production
- Bot token should be kept secret

---

## 🐛 Troubleshooting

### Bot Not Responding
- Check `DISCORD_TOKEN` is correct
- Verify bot has required permissions in server
- Check Railway logs for errors

### DM Notifications Failing
- Ensure users have DMs enabled
- Verify `DISCORD_FALLBACK_CATEGORY_ID` is set
- Bot needs "Manage Channels" permission in that category

### Database Connection Issues
- Verify PostgreSQL service is running in Railway
- Check `DATABASE_URL` is automatically set
- View Railway logs for connection errors

### Static Files Not Loading
- Run `python manage.py collectstatic` 
- Verify `STATIC_ROOT` is configured
- Check WhiteNoise is in `MIDDLEWARE`

---

## 📚 Technologies Used

- **Django 6.0** - Web framework
- **py-cord 2.7** - Discord bot library
- **PostgreSQL** - Database
- **httpx** - VATSIM API client
- **python-decouple** - Environment management
- **WhiteNoise** - Static file serving
- **Gunicorn** - WSGI server

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

## 🆘 Support

For issues and questions:
- Check the [Issues](../../issues) page
- Review Railway deployment logs
- Check Django admin logs at `/admin/`

---

## ✨ Credits

Built for VATSIM event management with ❤️ by the community.
