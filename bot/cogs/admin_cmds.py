"""
Admin commands cog – slash commands for bot admins to manage events in Discord.
Includes: announce event, pull events, import, etc.
"""

import logging

import discord
from discord.ext import commands
from asgiref.sync import sync_to_async

from django.conf import settings

from core.models import Event, EventStatus
from core.vatsim import VATSIMService
from bot.cogs.strings import build_event_embed, LABELS

logger = logging.getLogger("bot.admin")


# ══════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════

@sync_to_async
def import_single_event(event_id: int):
    """Import a single event by its VATSIM ID."""
    return VATSIMService.import_event_by_id(event_id)


@sync_to_async
def get_all_events():
    return list(Event.objects.order_by("-start_time")[:25])


@sync_to_async
def get_open_events_list():
    return list(
        Event.objects.filter(status=EventStatus.OPEN)
        .prefetch_related("icaos", "icaos__positions", "icaos__positions__position_template", "time_blocks")
        .order_by("-start_time")[:25]
    )


@sync_to_async
def get_event(pk: int):
    try:
        return Event.objects.prefetch_related(
            "icaos", "icaos__positions", "icaos__positions__position_template", "time_blocks"
        ).get(pk=pk)
    except Event.DoesNotExist:
        return None


@sync_to_async
def get_available_positions(event_id: int):
    """Get positions that have at least one available slot (not all locked/confirmed)."""
    from core.models import EventPosition, BookingApplication, ApplicationStatus, TimeBlock
    
    taken_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    all_positions = EventPosition.objects.filter(
        event_icao__event_id=event_id
    ).select_related("event_icao", "position_template")
    
    # Get total time blocks for this event
    total_blocks = TimeBlock.objects.filter(event_id=event_id).count()
    
    if total_blocks == 0:
        return {}
    
    # Get positions that have at least one slot without confirmation
    available = {}
    for pos in all_positions:
        taken_slots = BookingApplication.objects.filter(
            event_position=pos,
            status__in=taken_statuses,
        ).count()
        
        if taken_slots < total_blocks:
            available[pos.pk] = pos
    
    return available


@sync_to_async
def get_locked_applications(event_id: int):
    """Get all locked/confirmed applications for an event, grouped by position."""
    from core.models import BookingApplication, ApplicationStatus
    
    confirmed_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    return list(
        BookingApplication.objects.filter(
            event_position__event_icao__event_id=event_id,
            status__in=confirmed_statuses,
        ).select_related("user", "event_position", "event_position__event_icao", "event_position__position_template", "time_block").order_by(
            "event_position__event_icao__icao",
            "event_position__position_template__name",
            "time_block__block_number",
        )
    )


@sync_to_async
def is_event_fully_booked(event_id: int):
    """Check if all positions in an event are fully booked."""
    from core.models import EventPosition, BookingApplication, ApplicationStatus, TimeBlock
    
    taken_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    all_positions = EventPosition.objects.filter(
        event_icao__event_id=event_id
    )
    
    if not all_positions.exists():
        return False
    
    # Get total time blocks for this event
    total_blocks = TimeBlock.objects.filter(event_id=event_id).count()
    
    if total_blocks == 0:
        return False
    
    for pos in all_positions:
        taken_slots = BookingApplication.objects.filter(
            event_position=pos,
            status__in=taken_statuses,
        ).count()
        
        if taken_slots < total_blocks:
            # At least one position has available slots
            return False
    
    return True


async def update_announcement_message(bot: discord.Bot, event_id: int):
    """Update the announcement message with current available positions and selected ATCs.
    
    This function is called whenever a booking application status changes.
    """
    event = await get_event(event_id)
    if not event or not event.discord_channel_id or not event.discord_message_id:
        return False
    
    try:
        channel = bot.get_channel(int(event.discord_channel_id))
        if not channel:
            return False
        
        message = await channel.fetch_message(int(event.discord_message_id))
        if not message:
            return False
        
        # Fetch fresh data
        available_positions = await get_available_positions(event_id)
        locked_applications = await get_locked_applications(event_id)
        
        # Build new embed
        new_embed = build_event_embed(event, available_positions, locked_applications)
        
        # Update button view
        new_view = EventBookingButtonView(event_id)
        await new_view.initialize()
        
        # Re-attach callback to the button in case it's not disabled
        if new_view._button and not new_view._button.disabled:
            new_view._button.callback = new_view.on_book
        
        # Edit the message
        await message.edit(embed=new_embed, view=new_view)
        return True
    except Exception as e:
        logger.error(f"Failed to update announcement message for event {event_id}: {e}")
        return False


@sync_to_async
def update_event_discord_ref(event_id: int, channel_id: str, message_id: str):
    Event.objects.filter(pk=event_id).update(
        discord_channel_id=channel_id,
        discord_message_id=message_id,
    )


@sync_to_async
def get_event_by_vatsim_id(vatsim_id: int):
    try:
        return Event.objects.get(vatsim_id=vatsim_id)
    except Event.DoesNotExist:
        return None


@sync_to_async
def event_has_time_blocks(event_id: int):
    """Check if an event has time blocks configured."""
    from core.models import TimeBlock
    return TimeBlock.objects.filter(event_id=event_id).exists()


@sync_to_async
def generate_time_blocks_for_event(event_id: int, block_duration_minutes: int):
    """Update event block duration and generate time blocks."""
    from datetime import timedelta
    from core.models import TimeBlock
    
    try:
        event = Event.objects.get(pk=event_id)
        event.block_duration_minutes = block_duration_minutes
        event.save(update_fields=["block_duration_minutes"])
        
        # Clear old blocks
        TimeBlock.objects.filter(event=event).delete()
        
        # Generate new blocks
        total_created = 0
        if event.total_blocks > 0:
            for i in range(event.total_blocks):
                block_start = event.start_time + timedelta(minutes=i * event.block_duration_minutes)
                block_end = block_start + timedelta(minutes=event.block_duration_minutes)
                TimeBlock.objects.create(
                    event=event,
                    block_number=i + 1,
                    start_time=block_start,
                    end_time=block_end,
                )
                total_created += 1
        
        return total_created
    except Event.DoesNotExist:
        return 0


@sync_to_async
def create_event_icao(event_id: int, icao: str):
    """Create an ICAO for an event."""
    from core.models import EventICAO
    try:
        event = Event.objects.get(pk=event_id)
        icao_obj, created = EventICAO.objects.get_or_create(
            event=event,
            icao=icao.upper()
        )
        return icao_obj, created
    except Event.DoesNotExist:
        return None, False


@sync_to_async
def get_event_icaos(event_id: int):
    """Get all ICAOs for an event."""
    from core.models import EventICAO
    return list(EventICAO.objects.filter(event_id=event_id).select_related("event"))


@sync_to_async
def get_position_templates():
    """Get all available position templates."""
    from core.models import PositionTemplate
    return list(PositionTemplate.objects.all().order_by("name"))


@sync_to_async
def create_event_position(event_icao_id: int, position_template_id: int):
    """Link a position template to an event ICAO."""
    from core.models import EventPosition, EventICAO, PositionTemplate
    try:
        event_icao = EventICAO.objects.get(pk=event_icao_id)
        position_template = PositionTemplate.objects.get(pk=position_template_id)
        position, created = EventPosition.objects.get_or_create(
            event_icao=event_icao,
            position_template=position_template
        )
        return position, created
    except (EventICAO.DoesNotExist, PositionTemplate.DoesNotExist):
        return None, False


@sync_to_async
def get_event_positions(event_id: int):
    """Get all positions configured for an event."""
    from core.models import EventPosition
    return list(
        EventPosition.objects.filter(event_icao__event_id=event_id)
        .select_related("event_icao", "position_template")
        .order_by("event_icao__icao", "position_template__name")
    )


@sync_to_async
def set_event_status(event_id: int, status: str):
    """Update event status."""
    try:
        event = Event.objects.get(pk=event_id)
        event.status = status
        event.save(update_fields=["status"])
        return True
    except Event.DoesNotExist:
        return False


# ──────────────────────────────────────────────
# Admin booking management helpers
# ──────────────────────────────────────────────

@sync_to_async
def get_all_applications_for_event(event_id: int):
    """Get ALL applications for an event (all statuses), for admin overview."""
    from core.models import BookingApplication
    return list(
        BookingApplication.objects.filter(
            event_position__event_icao__event_id=event_id,
        ).select_related(
            "user", "event_position", "event_position__event_icao",
            "event_position__position_template", "time_block",
        ).order_by(
            "event_position__event_icao__icao",
            "event_position__position_template__name",
            "time_block__block_number",
        )
    )


@sync_to_async
def get_positions_with_pending_apps(event_id: int):
    """Get positions that have at least one PENDING application."""
    from core.models import EventPosition, BookingApplication, ApplicationStatus

    position_ids = (
        BookingApplication.objects.filter(
            event_position__event_icao__event_id=event_id,
            status=ApplicationStatus.PENDING,
        )
        .values_list("event_position_id", flat=True)
        .distinct()
    )
    return list(
        EventPosition.objects.filter(pk__in=position_ids)
        .select_related("event_icao", "position_template")
        .order_by("event_icao__icao", "position_template__name")
    )


@sync_to_async
def get_blocks_with_pending_apps(position_id: int, event_id: int):
    """Get time blocks that still have pending applications for a given position."""
    from core.models import TimeBlock, BookingApplication, ApplicationStatus

    block_ids = (
        BookingApplication.objects.filter(
            event_position_id=position_id,
            status=ApplicationStatus.PENDING,
        )
        .values_list("time_block_id", flat=True)
        .distinct()
    )
    return list(
        TimeBlock.objects.filter(pk__in=block_ids, event_id=event_id)
        .order_by("block_number")
    )


@sync_to_async
def get_applicants_for_position_block(position_id: int, block_id: int):
    """Get pending applicants for a specific position + block."""
    from core.models import BookingApplication, ApplicationStatus
    return list(
        BookingApplication.objects.filter(
            event_position_id=position_id,
            time_block_id=block_id,
            status=ApplicationStatus.PENDING,
        ).select_related("user", "time_block")
    )


@sync_to_async
def select_user_for_position(app_id: int):
    """
    Lock a user into a position+block.

    Side-effects (auto-rejections, NO rejection notification flag):
      1. Same user's OTHER position applications for the SAME block → REJECTED
      2. Other users' applications for the SAME position+block → REJECTED

    Returns (success, app, rejected_same_user_count, rejected_same_pos_count, reason).
    reason is None on success, or a string explaining why selection failed.
    """
    from core.models import BookingApplication, ApplicationStatus

    try:
        app = BookingApplication.objects.select_related(
            "user", "event_position", "event_position__event_icao",
            "event_position__position_template", "time_block",
        ).get(pk=app_id)

        if app.status != ApplicationStatus.PENDING:
            return False, app, 0, 0, "not_pending"

        event_id = app.event_position.event_icao.event_id

        # Check if user is already locked/confirmed for another position in the same block
        already_booked = BookingApplication.objects.filter(
            user=app.user,
            time_block=app.time_block,
            event_position__event_icao__event_id=event_id,
            status__in=[
                ApplicationStatus.LOCKED,
                ApplicationStatus.CONFIRMED,
                ApplicationStatus.FULL_CONFIRMED,
            ],
        ).exclude(pk=app.pk).select_related(
            "event_position__event_icao", "event_position__position_template"
        ).first()

        if already_booked:
            return False, app, 0, 0, f"double_booking:{already_booked.event_position.callsign}"

        # 1. Lock this application and queue the lock DM
        app.status = ApplicationStatus.LOCKED
        app.notification_sent = True
        app.save(update_fields=["status", "notification_sent"])

        # 2. Reject same user's OTHER positions for the SAME block
        rejected_same_user = BookingApplication.objects.filter(
            user=app.user,
            time_block=app.time_block,
            event_position__event_icao__event_id=event_id,
            status=ApplicationStatus.PENDING,
        ).exclude(pk=app.pk).update(status=ApplicationStatus.REJECTED)

        # 3. Reject other users for the SAME position + SAME block
        rejected_same_pos = BookingApplication.objects.filter(
            event_position=app.event_position,
            time_block=app.time_block,
            status=ApplicationStatus.PENDING,
        ).exclude(pk=app.pk).update(status=ApplicationStatus.REJECTED)

        return True, app, rejected_same_user, rejected_same_pos, None

    except BookingApplication.DoesNotExist:
        return False, None, 0, 0, "not_found"


@sync_to_async
def flag_rejections_for_event(event_id: int):
    """Flag all REJECTED applications for rejection DM (notification loop picks them up)."""
    from core.models import BookingApplication, ApplicationStatus
    return BookingApplication.objects.filter(
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.REJECTED,
        rejection_sent=False,
    ).update(rejection_sent=True)


@sync_to_async
def flag_reminders_for_event(event_id: int):
    """Flag confirmed / locked applications for reminder DM."""
    from core.models import BookingApplication, ApplicationStatus
    return BookingApplication.objects.filter(
        event_position__event_icao__event_id=event_id,
        status__in=[
            ApplicationStatus.LOCKED,
            ApplicationStatus.CONFIRMED,
            ApplicationStatus.FULL_CONFIRMED,
        ],
        reminder_sent=False,
    ).update(reminder_sent=True)


@sync_to_async
def close_event_bookings(event_id: int):
    """Close bookings: reject all remaining PENDING apps and set event to LOCKED."""
    from core.models import BookingApplication, ApplicationStatus
    rejected = BookingApplication.objects.filter(
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.PENDING,
    ).update(status=ApplicationStatus.REJECTED)
    Event.objects.filter(pk=event_id).update(status=EventStatus.LOCKED)
    return rejected


def is_admin():
    """Check if user's Discord ID is registered as an admin in Django."""
    async def predicate(ctx: discord.ApplicationContext):
        discord_id = str(ctx.author.id)
        
        @sync_to_async
        def check_admin_profile():
            from core.models import AdminProfile
            return AdminProfile.objects.filter(discord_id=discord_id).exists()
        
        return await check_admin_profile()
    return commands.check(predicate)


# ──────────────────────────────────────────────
# Reserve selection helpers
# ──────────────────────────────────────────────

@sync_to_async
def get_positions_needing_reserve(event_id: int):
    """Get positions that have at least one block without a locked/confirmed user."""
    from core.models import EventPosition, BookingApplication, ApplicationStatus, TimeBlock

    taken_statuses = [
        ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED,
    ]

    all_positions = list(
        EventPosition.objects.filter(
            event_icao__event_id=event_id
        ).select_related("event_icao", "position_template")
    )

    total_blocks = TimeBlock.objects.filter(event_id=event_id).count()
    if total_blocks == 0:
        return []

    needs_reserve = []
    for pos in all_positions:
        filled = BookingApplication.objects.filter(
            event_position=pos,
            status__in=taken_statuses,
        ).count()
        if filled < total_blocks:
            needs_reserve.append(pos)

    return needs_reserve


@sync_to_async
def get_unfilled_blocks_for_position(position_id: int, event_id: int):
    """Get time blocks that don't have a locked/confirmed user for this position."""
    from core.models import BookingApplication, ApplicationStatus, TimeBlock

    taken_statuses = [
        ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED,
    ]

    filled_block_ids = set(
        BookingApplication.objects.filter(
            event_position_id=position_id,
            status__in=taken_statuses,
        ).values_list("time_block_id", flat=True)
    )

    return list(
        TimeBlock.objects.filter(event_id=event_id)
        .exclude(pk__in=filled_block_ids)
        .order_by("block_number")
    )


@sync_to_async
def get_reserve_candidates(event_id: int, position_id: int, block_id: int):
    """Get users eligible for reserve selection.

    Includes users who applied to the event (any status, including rejected)
    with sufficient rating, excluding those already booked for this time block.
    """
    from core.models import EventPosition, BookingApplication, ApplicationStatus, VATSIMUser

    taken_statuses = [
        ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED,
    ]

    # Get the position's min rating
    position = EventPosition.objects.select_related('position_template').get(pk=position_id)
    min_rating = position.position_template.min_rating

    # Get users already booked for this time block (any position in the event)
    booked_user_ids = set(
        BookingApplication.objects.filter(
            event_position__event_icao__event_id=event_id,
            time_block_id=block_id,
            status__in=taken_statuses,
        ).values_list("user_id", flat=True)
    )

    # Get all unique users who applied to this event
    all_applicant_ids = set(
        BookingApplication.objects.filter(
            event_position__event_icao__event_id=event_id,
        ).values_list("user_id", flat=True)
    )

    # Filter out users already booked for this time block
    eligible_ids = all_applicant_ids - booked_user_ids

    # Get VATSIMUser objects with sufficient rating
    return list(
        VATSIMUser.objects.filter(
            pk__in=eligible_ids,
            rating__gte=min_rating,
        ).order_by("-rating", "discord_username")
    )


@sync_to_async
def select_reserve_user(user_cid: int, position_id: int, block_id: int, event_id: int):
    """Select a reserve user for a position+block.

    1. If there's a previous holder, reject their application + add cancellation
    2. Lock the new user (create or update their application)
    3. Reject the new user's other pending apps for the same time block
    4. Queue lock notification

    Returns (success, app, previous_user_info).
    """
    from core.models import (
        BookingApplication, ApplicationStatus, VATSIMUser,
        EventPosition, TimeBlock,
    )

    taken_statuses = [
        ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED,
    ]

    # 1. Handle previous holder (if any)
    previous_app = BookingApplication.objects.filter(
        event_position_id=position_id,
        time_block_id=block_id,
        status__in=taken_statuses,
    ).select_related("user").first()

    previous_user_info = None
    if previous_app:
        prev_user = previous_app.user
        previous_user_info = {
            'username': prev_user.discord_username,
            'cid': prev_user.cid,
        }
        previous_app.status = ApplicationStatus.REJECTED
        previous_app.save(update_fields=["status"])
        prev_user.total_cancellations += 1
        prev_user.save(update_fields=["total_cancellations"])

    # 2. Lock the new user (create or update application)
    user = VATSIMUser.objects.get(pk=user_cid)
    position = EventPosition.objects.get(pk=position_id)
    block = TimeBlock.objects.get(pk=block_id)

    app, created = BookingApplication.objects.get_or_create(
        user=user,
        event_position=position,
        time_block=block,
        defaults={
            "status": ApplicationStatus.LOCKED,
            "notification_sent": True,
        },
    )

    if not created:
        app.status = ApplicationStatus.LOCKED
        app.notification_sent = True
        app.save(update_fields=["status", "notification_sent"])

    # 3. Reject new user's other apps for same time block in same event
    BookingApplication.objects.filter(
        user=user,
        time_block=block,
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.PENDING,
    ).exclude(pk=app.pk).update(status=ApplicationStatus.REJECTED)

    return True, app, previous_user_info


# ══════════════════════════════════════════════
# Views
# ══════════════════════════════════════════════


class BlockDurationModal(discord.ui.Modal):
    """Modal to ask admin for block duration in minutes after importing an event."""
    
    def __init__(self, event_id: int, event_name: str, vatsim_id: int):
        super().__init__(title="Configuração de Blocos de Horário")
        self.event_id = event_id
        self.event_name = event_name
        self.vatsim_id = vatsim_id
        
        self.add_item(
            discord.ui.InputText(
                label="Duração de cada bloco (minutos)",
                placeholder="Ex: 60",
                required=True,
                max_length=3,
            )
        )
    
    async def callback(self, interaction: discord.Interaction):
        try:
            block_duration = int(self.children[0].value)
            
            if block_duration <= 0 or block_duration > 999:
                await interaction.response.send_message(
                    f"❌ Duração inválida. Deve ser entre 1 e 999 minutos.",
                    ephemeral=True,
                )
                return
            
            # Generate time blocks
            total_blocks = await generate_time_blocks_for_event(self.event_id, block_duration)
            
            if total_blocks > 0:
                await interaction.response.send_message(
                    f"✅ Evento configurado com sucesso!\n\n"
                    f"🎉 **{self.event_name}**\n"
                    f"🆔 **VATSIM ID:** {self.vatsim_id}\n"
                    f"⌚ **Duração do bloco:** {block_duration} minutos\n"
                    f"📅 **Blocos criados:** {total_blocks}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"⚠️ Evento atualizado, mas nenhum bloco foi criado.\n"
                    f"Verifique a duração do evento no admin.",
                    ephemeral=True,
                )
        except ValueError:
            await interaction.response.send_message(
                f"❌ Valor inválido. Digite apenas números.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erro ao configurar blocos: {str(e)}",
                ephemeral=True,
            )


class AnnounceEventSelectView(discord.ui.View):
    """Dropdown for admin to select which open event to announce."""

    def __init__(self, events: list[Event], channel: discord.TextChannel):
        super().__init__(timeout=120)
        self.events = {str(e.pk): e for e in events}
        self.channel = channel

        options = [
            discord.SelectOption(
                label=e.name[:100],
                value=str(e.pk),
                description=f"{e.start_time:%d/%m %H:%M}z – {e.get_status_display()}",
            )
            for e in events[:25]
        ]

        select = discord.ui.Select(
            placeholder="Escolha o evento para anunciar...",
            options=options,
            custom_id="announce_event_select",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        # Defer immediately to avoid the 3-second interaction timeout
        await interaction.response.defer(ephemeral=True)

        event_id = interaction.data["values"][0]
        event = await get_event(int(event_id))

        if not event:
            await interaction.followup.send("❌ Evento não encontrado.", ephemeral=True)
            return

        # Fetch available positions and locked applications
        available_positions = await get_available_positions(event.pk)
        locked_applications = await get_locked_applications(event.pk)
        
        # Build embed with available and selected ATCs
        embed = build_event_embed(event, available_positions, locked_applications)
        
        # Create and initialize button view
        view = EventBookingButtonView(event.pk)
        await view.initialize()

        # Mention role in spoiler tags if configured
        announce_role_id = getattr(settings, 'DISCORD_ANNOUNCE_ROLE_ID', None)
        content = f"||<@&{announce_role_id}>||" if announce_role_id else None

        msg = await self.channel.send(content=content, embed=embed, view=view)

        # Save Discord reference
        await update_event_discord_ref(event.pk, str(self.channel.id), str(msg.id))

        await interaction.edit_original_response(
            content=f"✅ Evento **{event.name}** anunciado em {self.channel.mention}!",
            view=None,
        )


class EventBookingButtonView(discord.ui.View):
    """Persistent view with a "Book Now" button on event announcements."""

    def __init__(self, event_id: int):
        super().__init__(timeout=None)  # Persistent
        self.event_id = event_id
        self._button = None

    async def initialize(self):
        """Async initialization to check if event is fully booked."""
        is_full = await is_event_fully_booked(self.event_id)
        
        if is_full:
            button = discord.ui.Button(
                label="✅ Finalizado",
                style=discord.ButtonStyle.gray,
                custom_id=f"book_event_{self.event_id}",
                disabled=True,
            )
        else:
            button = discord.ui.Button(
                label=LABELS["btn_book"],
                style=discord.ButtonStyle.success,
                custom_id=f"book_event_{self.event_id}",
            )
            button.callback = self.on_book
        
        self._button = button
        self.add_item(button)
        return self

    async def on_book(self, interaction: discord.Interaction):
        """When a user clicks 'Book' on an event announcement."""
        from bot.cogs.booking import (
            get_user_by_discord_id, BlockSelectView,
            get_time_blocks, get_positions_for_event,
        )
        from core.vatsim import AsyncVATSIMService
        from core.models import ATCRating
        from bot.cogs.strings import MSGS

        discord_id = str(interaction.user.id)
        discord_name = str(interaction.user)

        # Resolve user
        user = await get_user_by_discord_id(discord_id)
        if not user:
            user, _ = await AsyncVATSIMService.get_or_create_user(discord_id, discord_name)
            if not user:
                await interaction.response.send_message(MSGS["err_no_vatsim"], ephemeral=True)
                return

        event = await get_event(self.event_id)
        if not event or event.status != EventStatus.OPEN:
            await interaction.response.send_message(
                "⚠️ Este evento não está mais aberto para bookings.",
                ephemeral=True,
            )
            return

        blocks = await get_time_blocks(event.pk, user.rating)
        if not blocks:
            await interaction.response.send_message(
                "⚠️ Este evento não possui blocos de horário configurados.",
                ephemeral=True,
            )
            return

        # Check if user has any eligible positions
        positions = await get_positions_for_event(event.pk, user.rating, [])
        if not positions:
            rating_name = ATCRating(user.rating).label
            await interaction.response.send_message(
                MSGS["err_no_positions"].format(rating=rating_name),
                ephemeral=True,
            )
            return

        view = BlockSelectView(event, blocks, user)
        rating_name = ATCRating(user.rating).label
        msg = (
            f"👤 **CID:** {user.cid} • **Rating:** {rating_name}\n\n"
            + MSGS["select_blocks"].format(
                event_name=event.name,
                start=f"{event.start_time:%H:%M}",
                end=f"{event.end_time:%H:%M}",
            )
        )
        await interaction.response.send_message(content=msg, view=view, ephemeral=True)


class SelectionFlowView(discord.ui.View):
    """Multi-step admin view: Position → Block → User selection."""

    def __init__(self, event, positions, bot: discord.Bot):
        super().__init__(timeout=300)
        self.event = event
        self.positions = positions
        self.bot = bot
        self.selected_position = None
        self.blocks: dict = {}

        options = [
            discord.SelectOption(
                label=pos.callsign,
                value=str(pos.pk),
                description=f"Mín: {pos.position_template.get_min_rating_display()}",
            )
            for pos in positions[:25]
        ]
        select = discord.ui.Select(
            placeholder="1️⃣ Selecione a posição...",
            options=options,
            custom_id="admin_pos_select",
        )
        select.callback = self.on_position_select
        self.add_item(select)

    async def on_position_select(self, interaction: discord.Interaction):
        position_id = int(interaction.data["values"][0])
        self.selected_position = next(
            (p for p in self.positions if p.pk == position_id), None
        )
        if not self.selected_position:
            await interaction.response.send_message("❌ Posição não encontrada.", ephemeral=True)
            return

        blocks = await get_blocks_with_pending_apps(position_id, self.event.pk)
        if not blocks:
            await interaction.response.send_message(
                f"⚠️ Nenhuma aplicação pendente para {self.selected_position.callsign}.",
                ephemeral=True,
            )
            return

        self.blocks = {b.pk: b for b in blocks}

        self.clear_items()
        block_options = [
            discord.SelectOption(
                label=f"Bloco {b.block_number}: {b.start_time:%H:%M}–{b.end_time:%H:%M}z",
                value=str(b.pk),
            )
            for b in blocks[:25]
        ]
        block_select = discord.ui.Select(
            placeholder="2️⃣ Selecione o bloco de horário...",
            options=block_options,
            custom_id="admin_block_select",
        )
        block_select.callback = self.on_block_select
        self.add_item(block_select)

        await interaction.response.edit_message(
            content=(
                f"🎯 **Seleção para: {self.event.name}**\n\n"
                f"📍 **Posição:** {self.selected_position.callsign}\n"
                f"Selecione o bloco de horário:"
            ),
            view=self,
        )

    async def on_block_select(self, interaction: discord.Interaction):
        block_id = int(interaction.data["values"][0])
        selected_block = self.blocks.get(block_id)

        applicants = await get_applicants_for_position_block(
            self.selected_position.pk, block_id
        )
        if not applicants:
            await interaction.response.send_message(
                "⚠️ Nenhum aplicante pendente para este bloco.", ephemeral=True
            )
            return

        self.clear_items()
        user_options = [
            discord.SelectOption(
                label=f"{app.user.discord_username} (CID: {app.user.cid})",
                value=str(app.pk),
                description=f"Rating: {app.user.get_rating_display()}",
            )
            for app in applicants[:25]
        ]
        user_select = discord.ui.Select(
            placeholder="3️⃣ Selecione o controlador...",
            options=user_options,
            custom_id="admin_user_select",
        )
        user_select.callback = self.on_user_select
        self.add_item(user_select)

        block_label = (
            f"Bloco {selected_block.block_number}: "
            f"{selected_block.start_time:%H:%M}–{selected_block.end_time:%H:%M}z"
            if selected_block
            else "?"
        )
        await interaction.response.edit_message(
            content=(
                f"🎯 **Seleção para: {self.event.name}**\n\n"
                f"📍 **Posição:** {self.selected_position.callsign}\n"
                f"⏰ **Bloco:** {block_label}\n\n"
                f"Selecione o controlador:"
            ),
            view=self,
        )

    async def on_user_select(self, interaction: discord.Interaction):
        app_id = int(interaction.data["values"][0])
        success, app, rej_user, rej_pos, reason = await select_user_for_position(app_id)

        if not success:
            if reason and reason.startswith("double_booking:"):
                existing_pos = reason.split(":", 1)[1]
                await interaction.response.send_message(
                    f"❌ Este controlador já está selecionado para **{existing_pos}** "
                    f"neste mesmo bloco de horário.\n"
                    f"Não é possível alocar o mesmo controlador em duas posições no mesmo horário.",
                    ephemeral=True,
                )
            else:
                status_msg = (
                    f"(status atual: {app.get_status_display()})" if app else ""
                )
                await interaction.response.send_message(
                    f"❌ Não foi possível selecionar. A aplicação não está mais pendente. {status_msg}",
                    ephemeral=True,
                )
            return

        # Refresh announcement embed
        await update_announcement_message(self.bot, self.event.pk)

        result_msg = (
            f"✅ **Seleção confirmada!**\n\n"
            f"👤 **Controlador:** {app.user.discord_username} (CID: {app.user.cid})\n"
            f"📍 **Posição:** {app.event_position.callsign}\n"
            f"⏰ **Bloco:** {app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z\n\n"
            f"📊 **Auto-rejeições:**\n"
            f"  • Mesmo usuário, outras posições (mesmo bloco): {rej_user}\n"
            f"  • Outros usuários, mesma posição+bloco: {rej_pos}\n\n"
            f"🔔 Notificação de seleção será enviada automaticamente.\n"
            f"💡 Use `/selecionar` novamente para selecionar mais posições."
        )
        self.clear_items()
        await interaction.response.edit_message(content=result_msg, view=None)


class ReserveFlowView(discord.ui.View):
    """Multi-step admin view for reserve selection: Position → Block → User.
    
    Used by /selecionarreserva to fill unfilled blocks from the pool of
    all event applicants (including previously rejected users).
    """

    def __init__(self, event, positions, bot: discord.Bot):
        super().__init__(timeout=300)
        self.event = event
        self.positions = positions
        self.bot = bot
        self.selected_position = None
        self.selected_block = None
        self.blocks = {}

        options = [
            discord.SelectOption(
                label=pos.callsign,
                value=str(pos.pk),
                description=f"Mín: {pos.position_template.get_min_rating_display()}",
            )
            for pos in positions[:25]
        ]
        select = discord.ui.Select(
            placeholder="1️⃣ Selecione a posição...",
            options=options,
            custom_id="reserve_pos_select",
        )
        select.callback = self.on_position_select
        self.add_item(select)

    async def on_position_select(self, interaction: discord.Interaction):
        position_id = int(interaction.data["values"][0])
        self.selected_position = next(
            (p for p in self.positions if p.pk == position_id), None
        )
        if not self.selected_position:
            await interaction.response.send_message("❌ Posição não encontrada.", ephemeral=True)
            return

        blocks = await get_unfilled_blocks_for_position(position_id, self.event.pk)
        if not blocks:
            await interaction.response.send_message(
                f"⚠️ Todos os blocos de {self.selected_position.callsign} estão preenchidos.",
                ephemeral=True,
            )
            return

        self.blocks = {b.pk: b for b in blocks}
        self.clear_items()
        block_options = [
            discord.SelectOption(
                label=f"Bloco {b.block_number}: {b.start_time:%H:%M}–{b.end_time:%H:%M}z",
                value=str(b.pk),
            )
            for b in blocks[:25]
        ]
        block_select = discord.ui.Select(
            placeholder="2️⃣ Selecione o bloco sem controlador...",
            options=block_options,
            custom_id="reserve_block_select",
        )
        block_select.callback = self.on_block_select
        self.add_item(block_select)

        await interaction.response.edit_message(
            content=(
                f"🔄 **Seleção de Reserva – {self.event.name}**\n\n"
                f"📍 **Posição:** {self.selected_position.callsign}\n"
                f"Selecione o bloco que precisa de controlador:"
            ),
            view=self,
        )

    async def on_block_select(self, interaction: discord.Interaction):
        block_id = int(interaction.data["values"][0])
        self.selected_block = self.blocks.get(block_id)

        candidates = await get_reserve_candidates(
            self.event.pk, self.selected_position.pk, block_id
        )
        if not candidates:
            await interaction.response.send_message(
                "⚠️ Nenhum candidato elegível para este bloco.\n"
                "Todos os aplicantes já estão alocados neste horário ou não possuem rating suficiente.",
                ephemeral=True,
            )
            return

        self.clear_items()
        user_options = [
            discord.SelectOption(
                label=f"{user.discord_username} (CID: {user.cid})",
                value=str(user.cid),
                description=f"Rating: {user.get_rating_display()}",
            )
            for user in candidates[:25]
        ]
        user_select = discord.ui.Select(
            placeholder="3️⃣ Selecione o controlador reserva...",
            options=user_options,
            custom_id="reserve_user_select",
        )
        user_select.callback = self.on_user_select
        self.add_item(user_select)

        block_label = (
            f"Bloco {self.selected_block.block_number}: "
            f"{self.selected_block.start_time:%H:%M}–{self.selected_block.end_time:%H:%M}z"
            if self.selected_block else "?"
        )
        await interaction.response.edit_message(
            content=(
                f"🔄 **Seleção de Reserva – {self.event.name}**\n\n"
                f"📍 **Posição:** {self.selected_position.callsign}\n"
                f"⏰ **Bloco:** {block_label}\n\n"
                f"Selecione o controlador reserva:"
            ),
            view=self,
        )

    async def on_user_select(self, interaction: discord.Interaction):
        user_cid = int(interaction.data["values"][0])
        block_id = self.selected_block.pk

        success, app, prev_user = await select_reserve_user(
            user_cid, self.selected_position.pk, block_id, self.event.pk
        )

        if not success:
            await interaction.response.send_message(
                "❌ Não foi possível realizar a seleção.",
                ephemeral=True,
            )
            return

        # Refresh announcement embed
        await update_announcement_message(self.bot, self.event.pk)

        block_label = (
            f"{self.selected_block.start_time:%H:%M}–{self.selected_block.end_time:%H:%M}z"
            if self.selected_block else "?"
        )
        result_msg = (
            f"✅ **Reserva confirmada!**\n\n"
            f"👤 **Novo controlador:** {app.user.discord_username} (CID: {app.user.cid})\n"
            f"📍 **Posição:** {self.selected_position.callsign}\n"
            f"⏰ **Bloco:** {block_label}\n"
        )

        if prev_user:
            result_msg += (
                f"\n🔄 **Controlador substituído:** {prev_user['username']} (CID: {prev_user['cid']})\n"
                f"↳ +1 cancelamento adicionado ao perfil\n"
            )

        result_msg += (
            f"\n🔔 Notificação de seleção será enviada automaticamente.\n"
            f"💡 Use `/selecionarreserva` novamente para selecionar mais reservas."
        )

        self.clear_items()
        await interaction.response.edit_message(content=result_msg, view=None)


# ══════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════


class AdminCog(commands.Cog):
    """Admin-only commands for managing events via Discord."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @discord.slash_command(name="importar", description="[Admin] Importar um evento específico do VATSIM")
    @is_admin()
    async def importar(
        self, 
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM (ex: 18010)", required=True),
    ):
        """Import a specific event from VATSIM by its ID."""
        # Don't defer yet - we might need to send a modal
        
        try:
            logger.info(f"Importando evento {event_id}...")
            was_created, was_updated = await import_single_event(event_id)
            
            if not was_created and not was_updated:
                await ctx.respond(
                    f"❌ Evento não encontrado!\n"
                    f"**ID:** {event_id}\n\n"
                    f"Verifique se o ID está correto em: https://my.vatsim.net/events",
                    ephemeral=True,
                )
                return
            
            # Fetch the event
            event = await get_event_by_vatsim_id(event_id)
            if not event:
                await ctx.respond(
                    f"⚠️ Evento importado, mas não foi possível encontrá-lo no banco de dados.",
                    ephemeral=True,
                )
                return
            
            # Check if event needs block configuration
            has_blocks = await event_has_time_blocks(event.pk)
            logger.info(f"Evento {event_id} - has_blocks: {has_blocks}")
            
            if not has_blocks:
                # Event needs block configuration
                logger.info(f"Tentando abrir modal para evento {event_id}...")
                try:
                    modal = BlockDurationModal(
                        event_id=event.pk,
                        event_name=event.name,
                        vatsim_id=event_id,
                    )
                    await ctx.send_modal(modal)
                    logger.info(f"Modal enviado para evento {event_id}")
                except Exception as modal_error:
                    logger.error(f"Erro ao enviar modal: {modal_error}", exc_info=True)
                    # Fallback: inform user to use /configurar_blocos command
                    await ctx.respond(
                        f"✅ Evento importado com sucesso!\n"
                        f"**ID:** {event_id}\n"
                        f"**Nome:** {event.name}\n\n"
                        f"⚠️ Não foi possível abrir o modal de configuração.\n"
                        f"Use o comando `/configurar_blocos event_id:{event_id} duracao:60` para configurar os blocos.\n\n"
                        f"**Dica:** Se estiver usando Discord Web, tente pelo app desktop.",
                        ephemeral=True,
                    )
            else:
                # Event already has blocks configured
                if was_created:
                    status_msg = "Novo evento criado e blocos já configurados"
                else:
                    status_msg = "Dados atualizados (blocos já configurados)"
                
                await ctx.respond(
                    f"✅ Evento processado com sucesso!\n"
                    f"**ID:** {event_id}\n"
                    f"**Nome:** {event.name}\n"
                    f"**Status:** {status_msg}",
                    ephemeral=True,
                )
                
        except Exception as e:
            logger.error(f"Erro ao importar evento {event_id}: {e}", exc_info=True)
            await ctx.respond(
                f"❌ Erro ao importar evento {event_id}:\n{str(e)}",
                ephemeral=True,
            )

    @discord.slash_command(name="anunciar", description="[Admin] Anunciar um evento aberto no canal")
    @is_admin()
    async def anunciar(
        self,
        ctx: discord.ApplicationContext,
        canal: discord.Option(
            discord.TextChannel,
            description="Canal onde o evento será anunciado",
            required=False,
        ) = None,
    ):
        """Announce an open event in a channel."""
        target_channel = canal or ctx.channel

        events = await get_open_events_list()
        if not events:
            await ctx.respond("📭 Não há eventos abertos para anunciar.", ephemeral=True)
            return

        view = AnnounceEventSelectView(events, target_channel)
        await ctx.respond(
            "Selecione o evento que deseja anunciar:",
            view=view,
            ephemeral=True,
        )

    @discord.slash_command(name="status_evento", description="[Admin] Ver status de um evento")
    @is_admin()
    async def status_evento(self, ctx: discord.ApplicationContext):
        """Quick overview of event booking status."""
        await ctx.defer(ephemeral=True)

        events = await get_open_events_list()
        if not events:
            await ctx.respond("📭 Nenhum evento aberto.", ephemeral=True)
            return

        lines = []
        for event in events:
            @sync_to_async
            def count_apps(ev):
                from core.models import BookingApplication
                total = BookingApplication.objects.filter(
                    event_position__event_icao__event=ev,
                ).count()
                locked = BookingApplication.objects.filter(
                    event_position__event_icao__event=ev,
                    status__in=["locked", "confirmed", "full_confirmed"],
                ).count()
                return total, locked

            total, locked = await count_apps(event)
            lines.append(
                f"**{event.name}**\n"
                f"  📊 Aplicações: {total} | Travadas: {locked}\n"
                f"  ⏰ {event.start_time:%d/%m %H:%M}z – {event.end_time:%H:%M}z\n"
            )

        await ctx.respond("\n".join(lines) or "Sem dados.", ephemeral=True)

    @discord.slash_command(name="configurar_blocos", description="[Admin] Configurar duração dos blocos de um evento")
    @is_admin()
    async def configurar_blocos(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
        duracao: discord.Option(int, description="Duração de cada bloco em minutos (ex: 60)", required=True),
    ):
        """Configure time blocks for an event (alternative when modal doesn't work)."""
        await ctx.defer(ephemeral=True)
        
        try:
            # Get event
            event = await get_event_by_vatsim_id(event_id)
            if not event:
                await ctx.respond(
                    f"❌ Evento {event_id} não encontrado no banco de dados.\n"
                    f"Importe-o primeiro com `/importar event_id:{event_id}`",
                    ephemeral=True,
                )
                return
            
            if duracao <= 0 or duracao > 999:
                await ctx.respond(
                    f"❌ Duração inválida. Deve ser entre 1 e 999 minutos.",
                    ephemeral=True,
                )
                return
            
            # Generate time blocks
            total_blocks = await generate_time_blocks_for_event(event.pk, duracao)
            
            if total_blocks > 0:
                await ctx.respond(
                    f"✅ Blocos configurados com sucesso!\n\n"
                    f"🎉 **{event.name}**\n"
                    f"🆔 **VATSIM ID:** {event_id}\n"
                    f"⏰ **Duração do bloco:** {duracao} minutos\n"
                    f"📅 **Blocos criados:** {total_blocks}",
                    ephemeral=True,
                )
            else:
                await ctx.respond(
                    f"⚠️ Evento atualizado, mas nenhum bloco foi criado.\n"
                    f"Verifique a duração do evento no admin.",
                    ephemeral=True,
                )
        except Exception as e:
            logger.error(f"Erro ao configurar blocos: {e}", exc_info=True)
            await ctx.respond(
                f"❌ Erro ao configurar blocos: {str(e)}",
                ephemeral=True,
            )

    @discord.slash_command(name="adicionar_icao", description="[Admin] Adicionar ICAOs a um evento")
    @is_admin()
    async def adicionar_icao(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
        icaos: discord.Option(str, description="ICAOs separados por vírgula (ex: SBBR,SBGR,SBSP)", required=True),
    ):
        """Add ICAOs to an event."""
        await ctx.defer(ephemeral=True)
        
        try:
            event = await get_event_by_vatsim_id(event_id)
            if not event:
                await ctx.respond(
                    f"❌ Evento {event_id} não encontrado.\n"
                    f"Importe-o primeiro com `/importar event_id:{event_id}`",
                    ephemeral=True,
                )
                return
            
            # Parse ICAOs
            icao_list = [icao.strip().upper() for icao in icaos.split(",") if icao.strip()]
            
            if not icao_list:
                await ctx.respond("❌ Nenhum ICAO válido fornecido.", ephemeral=True)
                return
            
            # Create ICAOs
            created = []
            existing = []
            
            for icao in icao_list:
                icao_obj, was_created = await create_event_icao(event.pk, icao)
                if icao_obj:
                    if was_created:
                        created.append(icao)
                    else:
                        existing.append(icao)
            
            response = f"✅ ICAOs processados para **{event.name}**\n\n"
            if created:
                response += f"✨ **Criados:** {', '.join(created)}\n"
            if existing:
                response += f"♻️ **Já existiam:** {', '.join(existing)}\n"
            
            response += f"\n💡 **Próximo passo:** Use `/adicionar_posicao event_id:{event_id}` para adicionar posições aos ICAOs."
            
            await ctx.respond(response, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Erro ao adicionar ICAOs: {e}", exc_info=True)
            await ctx.respond(f"❌ Erro: {str(e)}", ephemeral=True)

    @discord.slash_command(name="adicionar_posicao", description="[Admin] Adicionar posições aos ICAOs de um evento")
    @is_admin()
    async def adicionar_posicao(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Add positions to event ICAOs through an interactive interface."""
        await ctx.defer(ephemeral=True)
        
        try:
            event = await get_event_by_vatsim_id(event_id)
            if not event:
                await ctx.respond(
                    f"❌ Evento {event_id} não encontrado.",
                    ephemeral=True,
                )
                return
            
            # Get ICAOs for this event
            icaos = await get_event_icaos(event.pk)
            if not icaos:
                await ctx.respond(
                    f"❌ Nenhum ICAO configurado para este evento.\n"
                    f"Use `/adicionar_icao event_id:{event_id} icaos:SBBR,SBGR` primeiro.",
                    ephemeral=True,
                )
                return
            
            # Get position templates
            templates = await get_position_templates()
            if not templates:
                await ctx.respond(
                    "❌ Nenhum template de posição disponível.\n"
                    "Configure-os no Django Admin primeiro.",
                    ephemeral=True,
                )
                return
            
            # Show selection UI
            view = AddPositionView(event, icaos, templates)
            await ctx.respond(
                f"🎯 **Adicionar posições para: {event.name}**\n\n"
                f"Selecione o ICAO e depois as posições que deseja adicionar:",
                view=view,
                ephemeral=True,
            )
            
        except Exception as e:
            logger.error(f"Erro ao adicionar posições: {e}", exc_info=True)
            await ctx.respond(f"❌ Erro: {str(e)}", ephemeral=True)

    @discord.slash_command(name="abrir_bookings", description="[Admin] Abrir evento para receber bookings")
    @is_admin()
    async def abrir_bookings(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Open an event for bookings (set status to OPEN)."""
        await ctx.defer(ephemeral=True)
        
        try:
            event = await get_event_by_vatsim_id(event_id)
            if not event:
                await ctx.respond(
                    f"❌ Evento {event_id} não encontrado.",
                    ephemeral=True,
                )
                return
            
            # Check if event has blocks
            has_blocks = await event_has_time_blocks(event.pk)
            if not has_blocks:
                await ctx.respond(
                    f"⚠️ Este evento não tem blocos de horário configurados.\n"
                    f"Configure com `/configurar_blocos event_id:{event_id} duracao:60` primeiro.",
                    ephemeral=True,
                )
                return
            
            # Check if event has positions
            positions = await get_event_positions(event.pk)
            if not positions:
                await ctx.respond(
                    f"⚠️ Este evento não tem posições configuradas.\n"
                    f"Adicione com `/adicionar_icao` e `/adicionar_posicao` primeiro.",
                    ephemeral=True,
                )
                return
            
            # Set status to OPEN
            success = await set_event_status(event.pk, EventStatus.OPEN)
            
            if success:
                await ctx.respond(
                    f"✅ **Evento aberto para bookings!**\n\n"
                    f"📢 **{event.name}**\n"
                    f"🆔 **VATSIM ID:** {event_id}\n"
                    f"📍 **Posições configuradas:** {len(positions)}\n"
                    f"⏰ **Blocos de horário:** Configurados\n\n"
                    f"💡 **Próximo passo:** Use `/anunciar` para anunciar o evento no canal público.",
                    ephemeral=True,
                )
            else:
                await ctx.respond("❌ Erro ao atualizar status do evento.", ephemeral=True)
            
        except Exception as e:
            logger.error(f"Erro ao abrir bookings: {e}", exc_info=True)
            await ctx.respond(f"❌ Erro: {str(e)}", ephemeral=True)

    # ──────────────────────────────────────────
    # Booking management commands
    # ──────────────────────────────────────────

    @discord.slash_command(
        name="aplicacoes",
        description="[Admin] Ver todas as aplicações de um evento",
    )
    @is_admin()
    async def aplicacoes(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """View all applications for an event, grouped by position + block."""
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        all_apps = await get_all_applications_for_event(event.pk)
        if not all_apps:
            await ctx.respond(f"📭 Nenhuma aplicação para **{event.name}**.", ephemeral=True)
            return

        # Filter to only show relevant statuses (exclude rejected/cancelled)
        shown_statuses = {"pending", "locked", "confirmed", "full_confirmed"}
        apps = [a for a in all_apps if a.status in shown_statuses]

        from collections import defaultdict

        by_position = defaultdict(lambda: defaultdict(list))
        for app in apps:
            callsign = app.event_position.callsign
            block_label = (
                f"Bloco {app.time_block.block_number} "
                f"({app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z)"
            )
            status_emoji = {
                "pending": "🟡",
                "locked": "🔒",
                "confirmed": "✅",
                "full_confirmed": "✅✅",
            }.get(app.status, "❓")
            by_position[callsign][block_label].append(
                f"{status_emoji} {app.user.discord_username} ({app.user.get_rating_display()})"
            )

        lines = [f"📋 **Aplicações – {event.name}**\n"]
        for callsign in sorted(by_position.keys()):
            lines.append(f"\n🏢 **{callsign}**")
            for block_label in sorted(by_position[callsign].keys()):
                users = by_position[callsign][block_label]
                lines.append(f"  {block_label}:")
                for u in users:
                    lines.append(f"    {u}")

        unique_users = len({app.user.cid for app in apps})
        pending = sum(1 for a in apps if a.status == "pending")
        locked = sum(1 for a in apps if a.status == "locked")
        confirmed = sum(1 for a in apps if a.status == "confirmed")
        full_confirmed = sum(1 for a in apps if a.status == "full_confirmed")
        rejected = sum(1 for a in all_apps if a.status == "rejected")

        lines.append(f"\n📊 **Total exibido:** {len(apps)} aplicações de {unique_users} usuários")
        lines.append(f"🟡 Pendentes: {pending} | 🔒 Selecionados: {locked} | ✅ Confirmados: {confirmed} | ✅✅ Confirmação Final: {full_confirmed}")
        if rejected > 0:
            lines.append(f"*(❌ {rejected} rejeitados — não exibidos)*")

        response = "\n".join(lines)

        # Discord 2 000-char limit — split if needed
        if len(response) <= 2000:
            await ctx.respond(response, ephemeral=True)
        else:
            chunks, current = [], ""
            for line in lines:
                if len(current) + len(line) + 1 > 1900:
                    chunks.append(current)
                    current = line
                else:
                    current += ("\n" + line) if current else line
            if current:
                chunks.append(current)
            await ctx.respond(chunks[0], ephemeral=True)
            for chunk in chunks[1:]:
                await ctx.followup.send(chunk, ephemeral=True)

    @discord.slash_command(
        name="selecionar",
        description="[Admin] Selecionar controladores para posições de um evento",
    )
    @is_admin()
    async def selecionar(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Interactive flow to select users for positions."""
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        positions = await get_positions_with_pending_apps(event.pk)
        if not positions:
            await ctx.respond(
                f"⚠️ Nenhuma aplicação pendente para **{event.name}**.\n"
                f"Todas as posições já foram preenchidas ou não há aplicações.",
                ephemeral=True,
            )
            return

        view = SelectionFlowView(event, positions, self.bot)
        await ctx.respond(
            f"🎯 **Seleção de Controladores – {event.name}**\n\n"
            f"Selecione a posição para começar:",
            view=view,
            ephemeral=True,
        )

    @discord.slash_command(
        name="rejeitar",
        description="[Admin] Enviar notificação de rejeição aos não selecionados",
    )
    @is_admin()
    async def rejeitar(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Flag rejected applications so the notification loop sends rejection DMs."""
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        count = await flag_rejections_for_event(event.pk)
        if count > 0:
            await ctx.respond(
                f"✅ **Rejeições enfileiradas para envio!**\n\n"
                f"📢 **Evento:** {event.name}\n"
                f"📬 **Notificações a enviar:** {count}\n\n"
                f"As mensagens de rejeição serão enviadas automaticamente nos próximos segundos.",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                f"ℹ️ Nenhuma rejeição pendente de envio para **{event.name}**.\n"
                f"Todas as notificações já foram enviadas ou não há usuários rejeitados.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="lembrete",
        description="[Admin] Enviar lembrete de confirmação final",
    )
    @is_admin()
    async def lembrete(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Flag confirmed users so the notification loop sends reminder DMs."""
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        count = await flag_reminders_for_event(event.pk)
        if count > 0:
            await ctx.respond(
                f"✅ **Lembretes enfileirados para envio!**\n\n"
                f"📢 **Evento:** {event.name}\n"
                f"📬 **Lembretes a enviar:** {count}\n\n"
                f"Os lembretes serão enviados automaticamente nos próximos segundos.",
                ephemeral=True,
            )
        else:
            await ctx.respond(
                f"ℹ️ Nenhum lembrete pendente para **{event.name}**.\n"
                f"Todos os lembretes já foram enviados ou não há usuários confirmados.",
                ephemeral=True,
            )

    @discord.slash_command(
        name="fechar",
        description="[Admin] Fechar todas as bookings de um evento",
    )
    @is_admin()
    async def fechar(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Close all bookings: reject remaining pending apps, lock event."""
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        rejected = await close_event_bookings(event.pk)
        await update_announcement_message(self.bot, event.pk)

        await ctx.respond(
            f"🔒 **Bookings fechadas!**\n\n"
            f"📢 **Evento:** {event.name}\n"
            f"❌ **Aplicações pendentes rejeitadas:** {rejected}\n"
            f"📊 **Status do evento:** Posições Travadas\n\n"
            f"💡 Use `/rejeitar event_id:{event_id}` para enviar notificações de rejeição.",
            ephemeral=True,
        )

    @discord.slash_command(
        name="selecionarreserva",
        description="[Admin] Selecionar controlador reserva para uma posição",
    )
    @is_admin()
    async def selecionarreserva(
        self,
        ctx: discord.ApplicationContext,
        event_id: discord.Option(int, description="ID do evento VATSIM", required=True),
    ):
        """Select a reserve controller for an unfilled position slot.

        Shows positions with unfilled blocks and allows selecting from the pool
        of all event applicants (including previously rejected users), as long as
        the user is not already booked for the same time block on another position.
        """
        await ctx.defer(ephemeral=True)

        event = await get_event_by_vatsim_id(event_id)
        if not event:
            await ctx.respond(f"❌ Evento {event_id} não encontrado.", ephemeral=True)
            return

        positions = await get_positions_needing_reserve(event.pk)
        if not positions:
            await ctx.respond(
                f"⚠️ Todas as posições de **{event.name}** estão preenchidas.\n"
                f"Não há blocos disponíveis para reserva.",
                ephemeral=True,
            )
            return

        view = ReserveFlowView(event, positions, self.bot)
        await ctx.respond(
            f"🔄 **Seleção de Reserva – {event.name}**\n\n"
            f"Selecione a posição que precisa de controlador:",
            view=view,
            ephemeral=True,
        )


class AddPositionView(discord.ui.View):
    """Interactive view to add positions to ICAOs."""
    
    def __init__(self, event, icaos, templates):
        super().__init__(timeout=300)
        self.event = event
        self.icaos = icaos
        self.templates = templates
        self.selected_icao = None
        
        # ICAO selector
        icao_options = [
            discord.SelectOption(
                label=icao.icao,
                value=str(icao.pk),
                description=f"Adicionar posições para {icao.icao}"
            )
            for icao in icaos[:25]
        ]
        
        icao_select = discord.ui.Select(
            placeholder="1️⃣ Escolha o ICAO...",
            options=icao_options,
            custom_id="icao_select",
        )
        icao_select.callback = self.on_icao_select
        self.add_item(icao_select)
    
    async def on_icao_select(self, interaction: discord.Interaction):
        """When ICAO is selected, show position options."""
        icao_id = int(interaction.data["values"][0])
        self.selected_icao = next((i for i in self.icaos if i.pk == icao_id), None)
        
        if not self.selected_icao:
            await interaction.response.send_message("❌ ICAO não encontrado.", ephemeral=True)
            return
        
        # Clear existing items and add position selector
        self.clear_items()
        
        # Add ICAO selector back
        icao_options = [
            discord.SelectOption(
                label=icao.icao,
                value=str(icao.pk),
                description=f"Adicionar posições para {icao.icao}",
                default=(icao.pk == icao_id)
            )
            for icao in self.icaos[:25]
        ]
        
        icao_select = discord.ui.Select(
            placeholder="1️⃣ ICAO selecionado...",
            options=icao_options,
            custom_id="icao_select",
        )
        icao_select.callback = self.on_icao_select
        self.add_item(icao_select)
        
        # Add position multi-selector
        position_options = [
            discord.SelectOption(
                label=f"{template.name} (Mín: {template.get_min_rating_display()})",
                value=str(template.pk),
                description=template.description[:100] if template.description else f"Rating: {template.get_min_rating_display()}"
            )
            for template in self.templates[:25]
        ]
        
        position_select = discord.ui.Select(
            placeholder="2️⃣ Escolha as posições (múltiplas)...",
            options=position_options,
            min_values=1,
            max_values=min(len(position_options), 25),
            custom_id="position_select",
        )
        position_select.callback = self.on_position_select
        self.add_item(position_select)
        
        await interaction.response.edit_message(
            content=f"🎯 **ICAO selecionado:** {self.selected_icao.icao}\n\n"
                    f"Agora selecione as posições que deseja adicionar:",
            view=self
        )
    
    async def on_position_select(self, interaction: discord.Interaction):
        """When positions are selected, create them."""
        if not self.selected_icao:
            await interaction.response.send_message("❌ Selecione um ICAO primeiro.", ephemeral=True)
            return
        
        position_ids = [int(pid) for pid in interaction.data["values"]]
        
        created = []
        existing = []
        
        for template_id in position_ids:
            template = next((t for t in self.templates if t.pk == template_id), None)
            if template:
                position, was_created = await create_event_position(self.selected_icao.pk, template_id)
                callsign = f"{self.selected_icao.icao}_{template.name}"
                if position:
                    if was_created:
                        created.append(callsign)
                    else:
                        existing.append(callsign)
        
        response = f"✅ **Posições processadas para {self.selected_icao.icao}**\n\n"
        if created:
            response += f"✨ **Criadas:** {', '.join(created)}\n"
        if existing:
            response += f"♻️ **Já existiam:** {', '.join(existing)}\n"
        
        response += f"\n💡 Continue adicionando posições ou use `/abrir_bookings event_id:{self.event.vatsim_id}` quando terminar."
        
        await interaction.response.send_message(response, ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(AdminCog(bot))
