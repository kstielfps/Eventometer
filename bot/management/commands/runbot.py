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

    async def _register_persistent_views(self, bot: discord.Bot):
        """Re-register persistent button views for all open events with announcements."""
        from core.models import Event, EventStatus
        from bot.cogs.admin_cmds import EventBookingButtonView
        from asgiref.sync import sync_to_async

        try:
            events = await sync_to_async(list)(
                Event.objects.filter(
                    status=EventStatus.OPEN,
                    discord_message_id__gt="",
                )
            )
            count = 0
            for event in events:
                view = EventBookingButtonView(event.pk)
                await view.initialize()
                bot.add_view(view, message_id=int(event.discord_message_id))
                count += 1
            if count:
                logger.info(f"Re-registered {count} persistent booking view(s).")
        except Exception as e:
            logger.error(f"Failed to register persistent views: {e}", exc_info=True)

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

            # Re-register persistent views for open event announcements
            await self._register_persistent_views(bot)

        # Load cogs
        bot.load_extension("bot.cogs.booking")
        bot.load_extension("bot.cogs.admin_cmds")
        bot.load_extension("bot.cogs.notifications")

        self.stdout.write("Cogs carregados. Conectando ao Discord...")

        bot.run(settings.DISCORD_TOKEN)
