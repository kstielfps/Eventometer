"""
Django management command to run the Discord bot.
Usage: python manage.py runbot
"""

import asyncio
import logging

import discord
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger("bot")


class Command(BaseCommand):
    help = "Inicia o bot do Discord (Eventometer)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Iniciando o bot Eventometer..."))

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        bot = discord.Bot(intents=intents)

        # Store guild ID for slash commands
        guild_id = settings.DISCORD_GUILD_ID if settings.DISCORD_GUILD_ID else None

        @bot.event
        async def on_ready():
            logger.info(f"Bot conectado como {bot.user} (ID: {bot.user.id})")
            self.stdout.write(self.style.SUCCESS(f"Bot conectado como {bot.user}"))

        # Load cogs
        bot.load_extension("bot.cogs.booking")
        bot.load_extension("bot.cogs.admin_cmds")
        bot.load_extension("bot.cogs.notifications")

        self.stdout.write("Cogs carregados. Conectando ao Discord...")

        bot.run(settings.DISCORD_TOKEN)
