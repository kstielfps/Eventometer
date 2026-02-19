"""
Notifications cog – background task that checks for pending notifications
and sends DMs to users via Discord.

Handles:
- Lock notifications (user selected for a position)
- Reminder notifications (day-of reminder)
- Rejection notifications (position filled, user not selected)
"""

import logging

import discord
from discord.ext import commands, tasks
from asgiref.sync import sync_to_async

from core.models import BookingApplication, ApplicationStatus

logger = logging.getLogger("bot.notifications")


@sync_to_async
def get_pending_notifications():
    """Get applications that need lock notification DMs."""
    return list(
        BookingApplication.objects.filter(
            status=ApplicationStatus.LOCKED,
            notification_sent=True,  # Admin flagged for sending
        ).select_related(
            "user", "event_position__event_icao__event",
            "event_position__position_template",
            "time_block",
        )
    )


@sync_to_async
def get_pending_reminders():
    """Get locked/confirmed applications that need reminder DMs.
    Excludes FULL_CONFIRMED — those users already did the final confirmation."""
    return list(
        BookingApplication.objects.filter(
            status__in=[ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED],
            reminder_sent=True,  # Admin flagged for sending
        ).select_related(
            "user", "event_position__event_icao__event",
            "event_position__position_template",
            "time_block",
        )
    )


@sync_to_async
def mark_reminder_delivered(app_id: int):
    """Clear the reminder_sent flag so this app is not picked up again on restart."""
    BookingApplication.objects.filter(pk=app_id).update(reminder_sent=False)


@sync_to_async
def mark_lock_notification_delivered(app_id: int):
    """Clear the notification_sent flag so this app is not picked up again on restart."""
    BookingApplication.objects.filter(pk=app_id).update(notification_sent=False)


@sync_to_async
def mark_rejection_delivered(app_id: int):
    """Clear the rejection_sent flag so this app is not picked up again on restart."""
    BookingApplication.objects.filter(pk=app_id).update(rejection_sent=False)


@sync_to_async
def get_pending_rejections():
    """Get rejected applications that need rejection DMs.
    
    Only includes rejections where the user was NOT accepted for any position
    in the same event (to avoid confusing users who were accepted elsewhere).
    """
    from django.db.models import Q, Exists, OuterRef
    
    # Subquery: check if user has any accepted application in the same event
    accepted_in_event = BookingApplication.objects.filter(
        user=OuterRef('user'),
        event_position__event_icao__event=OuterRef('event_position__event_icao__event'),
        status__in=[ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED],
    )
    
    return list(
        BookingApplication.objects.filter(
            status=ApplicationStatus.REJECTED,
            rejection_sent=True,  # Admin flagged for sending
        ).exclude(
            Exists(accepted_in_event)  # Exclude if user was accepted for any position in the event
        ).select_related(
            "user", "event_position__event_icao__event",
            "event_position__position_template",
            "time_block",
        )
    )


@sync_to_async
def mark_notification_delivered(app_id: int, field: str):
    """Mark a notification field as 'delivered' by clearing the flag and setting a delivered marker."""
    # We use a convention: notification_sent=True means "queued for send"
    # After sending, we keep notification_sent=True (record that it was sent)
    # but we need a way to not re-send. We'll use a simple approach:
    # After sending, we don't clear the flag, but the status will have changed
    # (LOCKED → still LOCKED but we track via a different mechanism)
    pass


@sync_to_async
def clear_notification_flag(app_id: int, notification_type: str):
    """Clear the notification flag after successful fallback delivery."""
    field_map = {
        'lock': 'notification_sent',
        'reminder': 'reminder_sent',
        'rejection': 'rejection_sent',
    }
    field_name = field_map.get(notification_type)
    if field_name:
        BookingApplication.objects.filter(pk=app_id).update(**{field_name: False})


@sync_to_async
def increment_dm_failure(app_id: int):
    """Increment DM failure count for an application."""
    from django.db.models import F
    BookingApplication.objects.filter(pk=app_id).update(
        dm_failure_count=F('dm_failure_count') + 1
    )
    # Return the updated count
    app = BookingApplication.objects.get(pk=app_id)
    return app.dm_failure_count


@sync_to_async
def mark_dm_failure_notified(app_id: int):
    """Mark that admin has been notified about DM failure."""
    BookingApplication.objects.filter(pk=app_id).update(dm_failure_notified=True)


@sync_to_async
def save_fallback_channel(app_id: int, channel_id: str):
    """Save the fallback channel ID for an application AND all other apps from
    the same user in the same event, so future notifications (reminders,
    rejections) also go to the fallback channel."""
    try:
        app = BookingApplication.objects.select_related(
            "event_position__event_icao"
        ).get(pk=app_id)
        event_id = app.event_position.event_icao.event_id
        user_id = app.user_id

        # Propagate to ALL apps from this user in this event
        BookingApplication.objects.filter(
            user_id=user_id,
            event_position__event_icao__event_id=event_id,
        ).update(
            fallback_channel_id=channel_id,
            dm_failure_notified=True,
        )
    except BookingApplication.DoesNotExist:
        BookingApplication.objects.filter(pk=app_id).update(
            fallback_channel_id=channel_id,
            dm_failure_notified=True,
        )


@sync_to_async
def clear_fallback_channel(app_id: int):
    """Clear the fallback channel ID after successful confirmation."""
    BookingApplication.objects.filter(pk=app_id).update(fallback_channel_id=None)


@sync_to_async
def get_admin_discord_ids():
    """Get all admin Discord IDs from AdminProfile."""
    from core.models import AdminProfile
    return list(
        AdminProfile.objects.values_list('discord_id', flat=True).filter(discord_id__isnull=False)
    )


class NotificationsCog(commands.Cog):
    """Background task that sends Discord DMs for booking notifications."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.sent_lock_ids: set[int] = set()
        self.sent_reminder_ids: set[int] = set()
        self.sent_rejection_ids: set[tuple[int, int]] = set()  # (user_id, event_id)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.check_notifications.is_running():
            self.check_notifications.start()
            logger.info("Notification loop started.")

    def cog_unload(self):
        self.check_notifications.cancel()

    @tasks.loop(seconds=30)
    async def check_notifications(self):
        """Check for pending notifications every 30 seconds."""
        try:
            await self._send_lock_notifications()
            await self._send_reminder_notifications()
            await self._send_rejection_notifications()
        except Exception as e:
            logger.error(f"Erro no loop de notificações: {e}", exc_info=True)

    async def _handle_dm_failure(self, app, notification_type: str, message: str, view=None):
        """
        Handle DM failure by tracking attempts and creating fallback channel after 2 failures.
        If a fallback channel already exists, send the message there directly.
        
        Args:
            app: BookingApplication instance
            notification_type: Type of notification ("lock", "reminder", "rejection")
            message: The notification message to send
            view: Optional Discord view (buttons) to attach
        """
        # If a fallback channel already exists, send directly there
        if app.fallback_channel_id:
            await self._send_to_fallback_channel(app, message, view, notification_type)
            return

        # If we already know DMs don't work (dm_failure_notified=True) but
        # no fallback channel exists yet, create one immediately.
        if app.dm_failure_notified:
            logger.info(
                f"DM failures recorded for {app.user.discord_username} but no fallback channel — creating one now "
                f"(notification_type={notification_type})"
            )
            await self._create_fallback_channel(app, notification_type, message, view)
            return

        # First-time failure path: increment counter and create fallback after 2 failures
        failure_count = await increment_dm_failure(app.pk)
        logger.warning(
            f"Cannot DM user {app.user.discord_username} (attempt {failure_count}/2) - "
            f"Notification type: {notification_type}"
        )
        
        if failure_count >= 2:
            await self._create_fallback_channel(app, notification_type, message, view)
            await mark_dm_failure_notified(app.pk)

    async def _send_to_fallback_channel(self, app, message: str, view=None, notification_type: str = "lock"):
        """Send a message to the user's existing fallback channel.
        If the channel was deleted, create a new one automatically."""
        try:
            channel = self.bot.get_channel(int(app.fallback_channel_id))
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(int(app.fallback_channel_id))
                except discord.NotFound:
                    channel = None

            if not channel:
                # Channel was deleted (e.g. after previous confirmation) — create a new one
                logger.info(
                    f"Fallback channel {app.fallback_channel_id} no longer exists for "
                    f"{app.user.discord_username}, creating a new one"
                )
                await self._create_fallback_channel(app, notification_type, message, view)
                return

            if view:
                await channel.send(content=message, view=view)
            else:
                await channel.send(content=message)

            logger.info(
                f"Sent notification to fallback channel #{channel.name} for {app.user.discord_username}"
            )
        except discord.NotFound:
            # Channel disappeared between check and send
            logger.info(
                f"Fallback channel gone for {app.user.discord_username}, creating new one"
            )
            await self._create_fallback_channel(app, notification_type, message, view)
        except Exception as e:
            logger.error(
                f"Failed to send to fallback channel {app.fallback_channel_id}: {e}",
                exc_info=True,
            )

    async def _create_fallback_channel(self, app, notification_type: str, message: str, view=None):
        """
        Create a fallback Discord text channel for notification when DMs fail.
        Channel is visible only to the user, bot admins, and the bot itself.
        """
        from decouple import config
        
        try:
            guild_id = int(config("DISCORD_GUILD_ID", default=0))
            category_id = int(config("DISCORD_FALLBACK_CATEGORY_ID", default=0))
            
            if not guild_id or not category_id:
                logger.error("DISCORD_GUILD_ID or DISCORD_FALLBACK_CATEGORY_ID not configured!")
                return
            
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.error(f"Could not find guild with ID {guild_id}")
                return
            
            category = guild.get_channel(category_id)
            if not category:
                logger.error(f"Could not find category with ID {category_id}")
                return
            
            # Check bot permissions in the category
            bot_permissions = category.permissions_for(guild.me)
            if not bot_permissions.manage_channels:
                logger.error(
                    f"Bot lacks 'Manage Channels' permission in category '{category.name}' ({category_id}). "
                    f"Cannot create fallback channel for {app.user.discord_username}. "
                    f"Please grant the bot 'Manage Channels' permission in this category."
                )
                return
            
            # Get the user as a Member
            user_member = guild.get_member(int(app.user.discord_user_id))
            if not user_member:
                logger.error(f"Could not find member {app.user.discord_user_id} in guild")
                return
            
            # Get admin role members for permissions
            admin_ids = await get_admin_discord_ids()
            
            # Create channel name (sanitized)
            channel_name = f"notificação-{app.user.discord_username}".lower().replace(" ", "-")
            
            # Set up permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user_member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            
            # Add permissions for each admin
            for admin_id in admin_ids:
                admin_member = guild.get_member(int(admin_id))
                if admin_member:
                    overwrites[admin_member] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            # Create the channel
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Notificação para {app.user.discord_username} - {notification_type}"
            )
            
            # Save channel ID to database
            await save_fallback_channel(app.pk, str(channel.id))
            
            # Send the notification message with user mention
            mention_msg = f"{user_member.mention}\n\n{message}"
            
            if view:
                await channel.send(content=mention_msg, view=view)
            else:
                await channel.send(content=mention_msg)
            
            # Clear the notification flag so this app won't be picked up again
            await clear_notification_flag(app.pk, notification_type)
            
            logger.info(f"Created fallback channel {channel.name} (#{channel.id}) for {app.user.discord_username}")
            
        except discord.errors.Forbidden as e:
            logger.error(
                f"Permission error creating fallback channel for {app.user.discord_username}: {e}\n"
                f"Please ensure the bot has 'Manage Channels' permission in the fallback category (ID: {category_id})."
            )
        except Exception as e:
            logger.error(f"Failed to create fallback channel for {app.user.discord_username}: {e}", exc_info=True)

    async def _send_lock_notifications(self):
        """Send DMs to users who were locked into a position."""
        from bot.cogs.booking import ConfirmView
        from bot.cogs.strings import MSGS

        apps = await get_pending_notifications()
        events_to_update = set()  # Track which events need announcement updates
        
        for app in apps:
            if app.pk in self.sent_lock_ids:
                continue

            try:
                event = app.event_position.event
                msg = MSGS["locked_notification"].format(
                    event_name=event.name,
                    position=app.event_position.callsign,
                    time=f"{app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z",
                )
                view = ConfirmView(application_id=app.pk, is_reminder=False)

                # If user already has a fallback channel, send there directly
                if app.fallback_channel_id:
                    await self._send_to_fallback_channel(app, msg, view, notification_type="lock")
                    await mark_lock_notification_delivered(app.pk)
                    self.sent_lock_ids.add(app.pk)
                    events_to_update.add(event.pk)
                    logger.info(f"Lock notification sent to fallback channel for {app.user.discord_username}")
                    continue

                discord_user = await self.bot.fetch_user(int(app.user.discord_user_id))
                if not discord_user:
                    continue

                await discord_user.send(content=msg, view=view)
                await mark_lock_notification_delivered(app.pk)
                self.sent_lock_ids.add(app.pk)
                events_to_update.add(event.pk)
                logger.info(f"Lock notification sent to {app.user.discord_username} for {app.event_position.callsign}")

            except discord.Forbidden:
                view = ConfirmView(application_id=app.pk, is_reminder=False)
                await self._handle_dm_failure(app, "lock", msg, view)
            except Exception as e:
                logger.error(f"Error sending lock notification: {e}", exc_info=True)
        
        # Update announcement messages for affected events
        for event_id in events_to_update:
            from bot.cogs.admin_cmds import update_announcement_message
            await update_announcement_message(self.bot, event_id)

    async def _send_reminder_notifications(self):
        """Send reminder DMs to confirmed users."""
        from bot.cogs.booking import ConfirmView
        from bot.cogs.strings import MSGS

        apps = await get_pending_reminders()
        for app in apps:
            if app.pk in self.sent_reminder_ids:
                continue

            try:
                event = app.event_position.event
                msg = MSGS["reminder_notification"].format(
                    event_name=event.name,
                    position=app.event_position.callsign,
                    icao=app.event_position.event_icao.icao,
                    time=f"{app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z",
                )
                view = ConfirmView(application_id=app.pk, is_reminder=True)

                # If user already has a fallback channel, send there directly
                if app.fallback_channel_id:
                    await self._send_to_fallback_channel(app, msg, view, notification_type="reminder")
                    await mark_reminder_delivered(app.pk)
                    self.sent_reminder_ids.add(app.pk)
                    logger.info(f"Reminder sent to fallback channel for {app.user.discord_username}")
                    continue

                discord_user = await self.bot.fetch_user(int(app.user.discord_user_id))
                if not discord_user:
                    continue

                await discord_user.send(content=msg, view=view)
                await mark_reminder_delivered(app.pk)
                self.sent_reminder_ids.add(app.pk)
                logger.info(f"Reminder sent to {app.user.discord_username}")

            except discord.Forbidden:
                view = ConfirmView(application_id=app.pk, is_reminder=True)
                await self._handle_dm_failure(app, "reminder", msg, view)
            except Exception as e:
                logger.error(f"Error sending reminder: {e}", exc_info=True)

    async def _send_rejection_notifications(self):
        """Send rejection DMs to users not selected.
        
        Only sends ONE notification per user per event, even if they have
        multiple rejected applications.
        """
        from bot.cogs.strings import MSGS

        apps = await get_pending_rejections()
        for app in apps:
            # Track by (user_id, event_id) to send only one message per user per event
            user_event_key = (app.user.cid, app.event_position.event_icao.event.pk)
            if user_event_key in self.sent_rejection_ids:
                continue

            try:
                event = app.event_position.event
                msg = MSGS["rejection_notification"].format(event_name=event.name)

                # If user already has a fallback channel, send there directly
                if app.fallback_channel_id:
                    await self._send_to_fallback_channel(app, msg, notification_type="rejection")
                    await mark_rejection_delivered(app.pk)
                    self.sent_rejection_ids.add(user_event_key)
                    logger.info(f"Rejection sent to fallback channel for {app.user.discord_username}")
                    continue

                discord_user = await self.bot.fetch_user(int(app.user.discord_user_id))
                if not discord_user:
                    continue

                await discord_user.send(content=msg)
                await mark_rejection_delivered(app.pk)
                self.sent_rejection_ids.add(user_event_key)
                logger.info(f"Rejection sent to {app.user.discord_username} for event {event.name}")

            except discord.Forbidden:
                await self._handle_dm_failure(app, "rejection", msg, None)
            except Exception as e:
                logger.error(f"Error sending rejection: {e}", exc_info=True)


def setup(bot: discord.Bot):
    bot.add_cog(NotificationsCog(bot))
