# 🚀 Railway Deployment Checklist

Follow this checklist to ensure a smooth deployment to Railway.

## ✅ Pre-Deployment

### 1. Discord Bot Setup
- [ ] Create Discord application at https://discord.com/developers/applications
- [ ] Enable Privileged Gateway Intents:
  - [ ] Server Members Intent
  - [ ] Message Content Intent
- [ ] Copy bot token for `DISCORD_TOKEN`
- [ ] Generate OAuth2 URL with scopes: `bot`, `applications.commands`
- [ ] Add bot permissions:
  - [ ] Manage Channels
  - [ ] Send Messages
  - [ ] Embed Links
  - [ ] Read Message History
  - [ ] Use Slash Commands
- [ ] Invite bot to your Discord server

### 2. Discord Server Setup
- [ ] Get your server (guild) ID for `DISCORD_GUILD_ID`
- [ ] Create a category for fallback notifications (e.g., "📩 Notifications")
- [ ] Get category ID for `DISCORD_FALLBACK_CATEGORY_ID`
- [ ] Ensure bot has "Manage Channels" permission in that category

### 3. Railway Project Setup
- [ ] Create Railway account at https://railway.app
- [ ] Create new project
- [ ] Add PostgreSQL database service
  - Railway will auto-set `DATABASE_URL`

### 4. Environment Variables
Copy from `.env.example` and configure in Railway:

#### Required Variables
- [ ] `SECRET_KEY` - Generate using:
  ```bash
  python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
  ```
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS=your-app.up.railway.app` (update after deployment)
- [ ] `DISCORD_TOKEN=your-bot-token`
- [ ] `DISCORD_GUILD_ID=your-server-id`
- [ ] `DISCORD_FALLBACK_CATEGORY_ID=your-category-id`

#### Optional Variables
- [ ] `VATSIM_API_KEY` (if you have one)
- [ ] `SECURE_SSL_REDIRECT=True`

---

## 🚂 Deploy to Railway

### 1. Connect Repository
- [ ] Push code to GitHub/GitLab
- [ ] In Railway: "New" → "GitHub Repo"
- [ ] Select repository
- [ ] Railway will auto-detect and deploy

### 2. Configure Environment Variables
- [ ] Go to service → "Variables"
- [ ] Add all required variables listed above
- [ ] Save changes (Railway will redeploy)

### 3. Monitor First Deployment
- [ ] Watch deployment logs for errors
- [ ] Check "Deployments" tab for status
- [ ] Verify database was created successfully

---

## ⚙️ Post-Deployment

### 1. Create Django Superuser
In Railway CLI or using the web console:
```bash
railway run python manage.py createsuperuser
```
Follow prompts to create admin account.

### 2. Link Your Discord Account
- [ ] Visit `https://your-app.up.railway.app/admin/`
- [ ] Login with superuser credentials
- [ ] Go to "Admin Profiles"
- [ ] Create new entry:
  - Select your Django user
  - Add your Discord ID (Right-click your Discord name → Copy ID)
- [ ] Save

### 3. Configure Position Templates
In Django Admin → "Position Templates", create:
- [ ] DEL (Delivery) - S1
- [ ] GND (Ground) - S1
- [ ] TWR (Tower) - S2
- [ ] APP (Approach) - S3
- [ ] DEP (Departure) - S3
- [ ] CTR (Center) - C1
- [ ] FSS (Flight Service) - S2

### 4. Test Discord Bot
- [ ] Check bot is online in Discord
- [ ] Run `/importar` command to test admin access
- [ ] Try importing a test event from VATSIM

---

## 🔍 Verification

### Health Checks
- [ ] Visit `https://your-app.up.railway.app/health/`
  - Should return: `{"status": "healthy", ...}`
- [ ] Visit `https://your-app.up.railway.app/bot-status/`
  - Should show bot connection status

### Bot Functionality
- [ ] Bot appears online in Discord
- [ ] Bot responds to slash commands
- [ ] Admin commands work (use `/importar` as test)
- [ ] User commands work (use `/eventos` as test)

### Database
- [ ] Can log into Django admin
- [ ] Can create/edit database objects
- [ ] PostgreSQL service is running in Railway

---

## 🐛 Troubleshooting

### Bot Not Starting
1. Check Railway logs: Deployments → Latest → View Logs
2. Verify `DISCORD_TOKEN` is correct
3. Check Privileged Gateway Intents are enabled
4. Ensure bot was invited to server

### Database Connection Failed
1. Verify PostgreSQL service is running
2. Check `DATABASE_URL` is set automatically by Railway
3. Review migration logs in deployment

### Static Files Not Loading
1. Run: `railway run python manage.py collectstatic`
2. Check `STATIC_ROOT` in settings
3. Verify WhiteNoise is in MIDDLEWARE

### Cannot Access Admin Commands
1. Verify AdminProfile was created linking Discord ID to Django user
2. Check bot has permissions in Discord server
3. Ensure commands are synced (restart bot if needed)

---

## 📝 Post-Deployment Workflow

### Daily Operations
1. Import events: `/importar event_id:12345`
2. Configure blocks: `/configurar_blocos`
3. Add ICAOs: `/adicionar_icao`
4. Add positions: `/adicionar_posicao`
5. Open bookings: `/abrir_bookings`
6. Announce: `/anunciar canal:#eventos`

### Admin Dashboard
- Use Django admin to manage bookings
- Lock users to positions
- Send notifications
- View booking matrix

---

## 🔄 Updates and Maintenance

### Deploying Updates
1. Push changes to GitHub
2. Railway auto-deploys from main branch
3. Monitor deployment logs
4. Test functionality after deployment

### Database Migrations
Railway automatically runs migrations on deploy via:
```
python manage.py migrate
```

### Viewing Logs
- Railway Dashboard → Service → Deployments → View Logs
- Check for errors or warnings
- Monitor bot activity

---

## 📧 Support

### Railway Issues
- https://railway.app/help
- Railway Discord community

### Application Issues
- Check Django admin logs
- Review Railway deployment logs
- Test with `DEBUG=True` locally first

---

## ✅ Deployment Complete!

Once all items are checked, your Eventometer system is ready for production use! 🎉
