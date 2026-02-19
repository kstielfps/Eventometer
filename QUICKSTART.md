# 🚀 Quick Start Guide

Get Eventometer running in 5 minutes!

## For Local Development

```bash
# 1. Clone and setup
git clone <repo-url>
cd eventometer
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your Discord token and other settings

# 4. Setup database
python manage.py migrate
python manage.py createsuperuser

# 5. Run the application
# Terminal 1 - Django
python manage.py runserver

# Terminal 2 - Discord Bot
python manage.py runbot
```

## For Railway Deployment

```bash
# 1. Push to GitHub
git init
git add .
git commit -m "Initial commit"
git push origin main

# 2. Deploy to Railway
- Go to railway.app
- New Project → Deploy from GitHub
- Add PostgreSQL database
- Set environment variables (see DEPLOYMENT_CHECKLIST.md)

# 3. Create superuser
railway run python manage.py createsuperuser

# Done! Visit your-app.up.railway.app/admin/
```

## Essential Environment Variables

```bash
SECRET_KEY=<generate-random-string>
DEBUG=False
DISCORD_TOKEN=<your-bot-token>
DISCORD_GUILD_ID=<your-server-id>
DISCORD_FALLBACK_CATEGORY_ID=<category-id>
```

## Next Steps

1. ✅ Link your Discord account in Django admin (Admin Profiles)
2. ✅ Create position templates (DEL, GND, TWR, APP, CTR)
3. ✅ Import your first event: `/importar event_id:12345`
4. ✅ Announce it: `/anunciar`

## Documentation

- [Full Deployment Guide](DEPLOY.md)
- [Deployment Checklist](DEPLOYMENT_CHECKLIST.md)
- [Environment Variables](.env.example)

## Support

- 📚 Django Admin: `/admin/`
- 🏥 Health Check: `/health/`
- 🤖 Bot Status: `/bot-status/`
