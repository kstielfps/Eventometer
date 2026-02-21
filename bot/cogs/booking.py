"""
Booking cog – handles the user-facing booking flow via Discord components.

Flow:
1. User runs /eventos → identifies via VATSIM API
2. User selects event from dropdown
3. User selects time blocks (multi-select)
4. User selects position (filtered by rating)
5. Application saved + summary shown
"""

import asyncio
import logging
from typing import Optional

import discord
from discord.ext import commands
from asgiref.sync import sync_to_async

from core.models import (
    Event, EventPosition, TimeBlock, BookingApplication,
    VATSIMUser, EventStatus, ApplicationStatus, ATCRating,
)
from core.vatsim import AsyncVATSIMService
from bot.cogs.strings import MSGS, LABELS, build_event_embed, build_summary_embed

logger = logging.getLogger("bot.booking")


# ══════════════════════════════════════════════
# Helper DB queries (sync → async)
# ══════════════════════════════════════════════

@sync_to_async
def get_open_events():
    return list(
        Event.objects.filter(status=EventStatus.OPEN)
        .prefetch_related("icaos", "icaos__positions", "icaos__positions__position_template", "time_blocks")
    )


@sync_to_async
def get_event_by_id(event_id: int):
    try:
        return Event.objects.prefetch_related(
            "icaos", "icaos__positions", "icaos__positions__position_template", "time_blocks"
        ).get(pk=event_id)
    except Event.DoesNotExist:
        return None


@sync_to_async
def get_positions_for_event(event_id: int, min_rating: int, selected_block_ids: list[int]):
    """Get positions accessible by the user's rating that have at least one available block."""
    # Statuses that mean the slot is taken
    taken_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    # Get all positions matching rating
    all_positions = list(
        EventPosition.objects.filter(
            event_icao__event_id=event_id,
            position_template__min_rating__lte=min_rating,
        ).select_related("event_icao", "position_template")
    )
    
    if not all_positions or not selected_block_ids:
        return all_positions
    
    # Get (position_id, block_id) pairs that are taken
    taken_pairs = set(
        BookingApplication.objects.filter(
            event_position__in=all_positions,
            time_block_id__in=selected_block_ids,
            status__in=taken_statuses,
        ).values_list("event_position_id", "time_block_id")
    )
    
    # Filter: keep only positions that have at least 1 available block
    available_positions = []
    for position in all_positions:
        has_available_block = any(
            (position.pk, block_id) not in taken_pairs
            for block_id in selected_block_ids
        )
        if has_available_block:
            available_positions.append(position)
    
    return available_positions


@sync_to_async
def get_time_blocks(event_id: int, min_rating: int):
    """Get time blocks that have at least one available position for the user's rating."""
    # Statuses that mean the slot is taken
    taken_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    # Get all blocks
    all_blocks = list(TimeBlock.objects.filter(event_id=event_id).order_by("block_number"))
    
    # Get all positions matching rating
    accessible_positions = list(
        EventPosition.objects.filter(
            event_icao__event_id=event_id,
            position_template__min_rating__lte=min_rating,
        ).values_list("pk", flat=True)
    )
    
    if not accessible_positions:
        return []
    
    # Get (position_id, block_id) pairs that are taken
    taken_pairs = set(
        BookingApplication.objects.filter(
            event_position_id__in=accessible_positions,
            time_block__event_id=event_id,
            status__in=taken_statuses,
        ).values_list("event_position_id", "time_block_id")
    )
    
    # Filter: keep only blocks that have at least 1 available position
    available_blocks = []
    for block in all_blocks:
        has_available_position = any(
            (pos_id, block.pk) not in taken_pairs
            for pos_id in accessible_positions
        )
        if has_available_position:
            available_blocks.append(block)
    
    return available_blocks


@sync_to_async
def get_all_time_blocks(event_id: int):
    """Get all time blocks for an event (no filtering)."""
    return list(TimeBlock.objects.filter(event_id=event_id).order_by("block_number"))


@sync_to_async
def create_applications(user: VATSIMUser, positions: list[EventPosition], block_ids: list[int]):
    """Create booking applications for multiple positions across multiple blocks.
    
    Only creates applications for (position, block) combinations that don't already
    have locked/confirmed applications.
    """
    # Statuses that mean the slot is taken
    taken_statuses = [
        ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED,
        ApplicationStatus.FULL_CONFIRMED,
    ]
    
    # Get all (position_id, block_id) pairs that are already taken
    taken_pairs = set(
        BookingApplication.objects.filter(
            event_position__in=positions,
            time_block_id__in=block_ids,
            status__in=taken_statuses,
        ).values_list("event_position_id", "time_block_id")
    )
    
    created = 0
    for position in positions:
        for block_id in block_ids:
            # Skip if this combination is already taken by a confirmed user
            if (position.pk, block_id) in taken_pairs:
                continue
                
            _, was_created = BookingApplication.objects.get_or_create(
                user=user,
                event_position=position,
                time_block_id=block_id,
                defaults={"status": ApplicationStatus.PENDING},
            )
            if was_created:
                created += 1

    # Update user stats
    user.total_applications += created
    user.save(update_fields=["total_applications"])

    return created


@sync_to_async
def revoke_applications(user_cid: int, event_id: int):
    """Revoke all pending applications for a user on an event."""
    apps = BookingApplication.objects.filter(
        user_id=user_cid,
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.PENDING,
    )
    count = apps.count()
    apps.delete()
    return count


@sync_to_async
def get_events_with_user_apps(user_cid: int):
    """Get events where user has active (non-terminated) applications."""
    active_statuses = [
        ApplicationStatus.PENDING, ApplicationStatus.LOCKED,
        ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED,
    ]
    event_ids = set(
        BookingApplication.objects.filter(
            user_id=user_cid,
            status__in=active_statuses,
        ).values_list(
            "event_position__event_icao__event_id", flat=True
        ).distinct()
    )
    return list(
        Event.objects.filter(pk__in=event_ids)
        .prefetch_related("icaos", "time_blocks")
        .order_by("-start_time")
    )


@sync_to_async
def revoke_all_applications(user_cid: int, event_id: int):
    """Revoke all applications for a user on an event.

    - PENDING apps: deleted
    - LOCKED apps: set to CANCELLED
    - CONFIRMED/FULL_CONFIRMED apps: set to NO_SHOW

    Returns dict with counts and details.
    """
    result = {
        'pending_deleted': 0,
        'locked_cancelled': 0,
        'noshow_count': 0,
        'noshow_details': [],
    }

    # Handle PENDING apps - delete them
    pending = BookingApplication.objects.filter(
        user_id=user_cid,
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.PENDING,
    )
    result['pending_deleted'] = pending.count()
    pending.delete()

    # Handle LOCKED apps - cancel them
    locked = BookingApplication.objects.filter(
        user_id=user_cid,
        event_position__event_icao__event_id=event_id,
        status=ApplicationStatus.LOCKED,
    )
    result['locked_cancelled'] = locked.count()
    locked.update(status=ApplicationStatus.CANCELLED)

    # Handle CONFIRMED/FULL_CONFIRMED apps - mark as NO_SHOW
    confirmed_apps = list(
        BookingApplication.objects.filter(
            user_id=user_cid,
            event_position__event_icao__event_id=event_id,
            status__in=[ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED],
        ).select_related(
            'event_position__event_icao',
            'event_position__position_template',
            'time_block',
        )
    )

    for app in confirmed_apps:
        result['noshow_details'].append({
            'position': app.event_position.callsign,
            'block': (
                f"Bloco {app.time_block.block_number}: "
                f"{app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z"
            ),
        })

    result['noshow_count'] = len(confirmed_apps)
    BookingApplication.objects.filter(
        pk__in=[a.pk for a in confirmed_apps]
    ).update(status=ApplicationStatus.NO_SHOW)

    # Update user stats
    total_cancelled = result['pending_deleted'] + result['locked_cancelled']
    user = VATSIMUser.objects.get(pk=user_cid)
    if total_cancelled > 0:
        user.total_cancellations += total_cancelled
    if result['noshow_count'] > 0:
        user.total_no_shows += result['noshow_count']
    if total_cancelled > 0 or result['noshow_count'] > 0:
        user.save(update_fields=['total_cancellations', 'total_no_shows'])

    return result


@sync_to_async
def get_user_by_discord_id(discord_id: str) -> Optional[VATSIMUser]:
    try:
        return VATSIMUser.objects.get(discord_user_id=discord_id)
    except VATSIMUser.DoesNotExist:
        return None


# ══════════════════════════════════════════════
# Views (Discord UI Components)
# ══════════════════════════════════════════════


class EventSelectView(discord.ui.View):
    """Step 1: Dropdown to select an event."""

    def __init__(self, events: list[Event], user: VATSIMUser):
        super().__init__(timeout=300)
        self.user = user
        self.events = {str(e.pk): e for e in events}

        options = []
        for event in events[:25]:  # Discord limit: 25 options
            label = event.name[:100]
            desc = f"{event.start_time:%d/%m %H:%M}z – {event.end_time:%H:%M}z"
            options.append(discord.SelectOption(
                label=label,
                value=str(event.pk),
                description=desc[:100],
            ))

        select = discord.ui.Select(
            placeholder=LABELS["select_event_placeholder"],
            options=options,
            custom_id="event_select",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        event_id = interaction.data["values"][0]
        event = self.events.get(event_id)
        if not event:
            await interaction.response.send_message(MSGS["err_generic"], ephemeral=True)
            return

        # Move to block selection
        blocks = await get_time_blocks(event.pk, self.user.rating)
        if not blocks:
            await interaction.response.send_message(
                "⚠️ Este evento não possui blocos de horário configurados.",
                ephemeral=True,
            )
            return

        view = BlockSelectView(event, blocks, self.user)
        msg = MSGS["select_blocks"].format(
            event_name=event.name,
            start=f"{event.start_time:%H:%M}",
            end=f"{event.end_time:%H:%M}",
        )
        await interaction.response.edit_message(content=msg, view=view, embed=None)


class BlockSelectView(discord.ui.View):
    """Step 2: Multi-select dropdown for time blocks."""

    def __init__(self, event: Event, blocks: list[TimeBlock], user: VATSIMUser):
        super().__init__(timeout=300)
        self.event = event
        self.blocks = {str(b.pk): b for b in blocks}
        self.user = user

        options = []
        for block in blocks[:25]:
            options.append(discord.SelectOption(
                label=f"Bloco {block.block_number}: {block.start_time:%H:%M}–{block.end_time:%H:%M}z",
                value=str(block.pk),
            ))

        select = discord.ui.Select(
            placeholder=LABELS["select_blocks_placeholder"],
            options=options,
            min_values=1,
            max_values=len(options),
            custom_id="block_select",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        selected_block_ids = interaction.data["values"]
        selected_blocks = [self.blocks[bid] for bid in selected_block_ids if bid in self.blocks]

        if not selected_blocks:
            await interaction.response.send_message(MSGS["err_generic"], ephemeral=True)
            return

        # Get positions filtered by user rating and available blocks
        positions = await get_positions_for_event(
            self.event.pk, self.user.rating, [int(bid) for bid in selected_block_ids]
        )
        if not positions:
            rating_name = ATCRating(self.user.rating).label
            await interaction.response.edit_message(
                content=MSGS["err_no_positions"].format(rating=rating_name),
                view=None,
            )
            return

        view = PositionSelectView(self.event, positions, selected_block_ids, self.user)
        rating_name = ATCRating(self.user.rating).label
        msg = MSGS["select_position"].format(rating=rating_name)
        await interaction.response.edit_message(content=msg, view=view)


class PositionSelectView(discord.ui.View):
    """Step 3: Select position to apply for."""

    def __init__(
        self,
        event: Event,
        positions: list[EventPosition],
        selected_block_ids: list[str],
        user: VATSIMUser,
    ):
        super().__init__(timeout=300)
        self.event = event
        self.positions = {str(p.pk): p for p in positions}
        self.selected_block_ids = [int(bid) for bid in selected_block_ids]
        self.user = user

        options = []
        for pos in positions[:25]:
            min_rating_name = ATCRating(pos.min_rating).label
            options.append(discord.SelectOption(
                label=pos.callsign,
                value=str(pos.pk),
                description=f"Mínimo: {min_rating_name}",
            ))

        select = discord.ui.Select(
            placeholder=LABELS["select_position_placeholder"],
            options=options,
            min_values=1,
            max_values=len(options),
            custom_id="position_select",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        selected_ids = interaction.data["values"]
        selected_positions = [self.positions[pid] for pid in selected_ids if pid in self.positions]
        if not selected_positions:
            await interaction.response.send_message(MSGS["err_generic"], ephemeral=True)
            return

        # Create applications for all selected positions
        created = await create_applications(self.user, selected_positions, self.selected_block_ids)

        if created == 0:
            await interaction.response.edit_message(
                content=MSGS["err_already_applied"],
                view=None,
            )
            return

        # Build summary
        blocks = await get_all_time_blocks(self.event.pk)
        block_map = {b.pk: b for b in blocks}
        block_labels = [
            f"Bloco {block_map[bid].block_number}: "
            f"{block_map[bid].start_time:%H:%M}–{block_map[bid].end_time:%H:%M}z"
            for bid in self.selected_block_ids
            if bid in block_map
        ]

        position_labels = [p.callsign for p in selected_positions]
        embed = build_summary_embed(self.user, self.event, position_labels, block_labels)
        msg = MSGS["application_summary"].format(
            event_name=self.event.name,
            position=", ".join(position_labels),
            blocks=", ".join(block_labels),
        )
        await interaction.response.edit_message(content=msg, embed=embed, view=None)


class ConfirmView(discord.ui.View):
    """View with a Confirm button sent via DM after admin locks a position."""

    def __init__(self, application_id: int, is_reminder: bool = False):
        super().__init__(timeout=None)  # Persistent view
        self.application_id = application_id

        label = LABELS["btn_final_confirm"] if is_reminder else LABELS["btn_confirm"]
        custom_id = f"confirm_{application_id}"

        button = discord.ui.Button(
            label=label,
            style=discord.ButtonStyle.success,
            custom_id=custom_id,
        )
        button.callback = self.on_confirm
        self.add_item(button)

    async def on_confirm(self, interaction: discord.Interaction):
        from core.models import BookingApplication, ApplicationStatus

        @sync_to_async
        def update_status():
            try:
                app = BookingApplication.objects.get(pk=self.application_id)
            except BookingApplication.DoesNotExist:
                return None, None, None

            fallback_channel_id = app.fallback_channel_id
            event_id = app.event_position.event_icao.event_id

            if app.status == ApplicationStatus.LOCKED:
                app.status = ApplicationStatus.CONFIRMED
                app.fallback_channel_id = None  # Clear fallback channel ID
                app.save(update_fields=["status", "fallback_channel_id", "updated_at"])
                return "confirmed", fallback_channel_id, event_id
            elif app.status == ApplicationStatus.CONFIRMED:
                app.status = ApplicationStatus.FULL_CONFIRMED
                app.fallback_channel_id = None  # Clear fallback channel ID
                app.save(update_fields=["status", "fallback_channel_id", "updated_at"])
                return "full_confirmed", fallback_channel_id, event_id
            return "already", fallback_channel_id, event_id

        result, fallback_channel_id, event_id = await update_status()

        if result == "confirmed":
            await interaction.response.edit_message(content=MSGS["confirmed"], view=None)
        elif result == "full_confirmed":
            await interaction.response.edit_message(content=MSGS["full_confirmed"], view=None)
        elif result == "already":
            await interaction.response.edit_message(
                content="✅ Já registrado anteriormente.",
                view=None,
            )
        else:
            await interaction.response.edit_message(content=MSGS["err_generic"], view=None)
        
        # Update the announcement message if result was successful
        if result in ["confirmed", "full_confirmed"] and event_id:
            try:
                from bot.cogs.admin_cmds import update_announcement_message
                # Get the bot context - interaction.client is the bot
                await update_announcement_message(interaction.client, event_id)
            except Exception as e:
                logger.warning(f"Failed to update announcement message: {e}")
        
        # Delete the fallback channel if this confirmation was in one
        if fallback_channel_id and interaction.channel:
            try:
                if str(interaction.channel.id) == fallback_channel_id:
                    await interaction.channel.send("✅ Confirmação recebida! Este canal será deletado em 5 segundos...")
                    await asyncio.sleep(5)
                    await interaction.channel.delete(reason="Confirmação recebida via canal de fallback")
            except Exception as e:
                import logging
                logger = logging.getLogger("bot.booking")
                logger.error(f"Failed to delete fallback channel: {e}")


# ══════════════════════════════════════════════
# Cog
# ══════════════════════════════════════════════


class BookingCog(commands.Cog):
    """Handles the booking flow for ATC positions."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot

    @discord.slash_command(name="eventos", description="Ver eventos abertos e aplicar para posições ATC")
    async def eventos(self, ctx: discord.ApplicationContext):
        """Main entry point: identify user and show open events."""
        await ctx.defer(ephemeral=True)

        discord_id = str(ctx.author.id)
        discord_name = str(ctx.author)

        # Always resolve via VATSIM API to keep rating up-to-date
        user, created = await AsyncVATSIMService.get_or_create_user(
            discord_id, discord_name,
        )
        if not user:
            await ctx.respond(MSGS["err_no_vatsim"], ephemeral=True)
            return

        # Get open events
        events = await get_open_events()
        if not events:
            await ctx.respond(MSGS["err_no_events"], ephemeral=True)
            return

        # Show event selection
        rating_name = ATCRating(user.rating).label
        msg = MSGS["welcome"].format(cid=user.cid, rating=rating_name)
        view = EventSelectView(events, user)

        await ctx.respond(content=msg, view=view, ephemeral=True)

    @discord.slash_command(name="revogar", description="Revogar todas as suas aplicações de um evento")
    async def revogar(self, ctx: discord.ApplicationContext):
        """Let users revoke all their applications for an event (including confirmed)."""
        await ctx.defer(ephemeral=True)

        discord_id = str(ctx.author.id)
        user = await get_user_by_discord_id(discord_id)

        if not user:
            await ctx.respond(MSGS["err_no_vatsim"], ephemeral=True)
            return

        events = await get_events_with_user_apps(user.cid)
        if not events:
            await ctx.respond("ℹ️ Você não possui aplicações ativas em nenhum evento.", ephemeral=True)
            return

        view = RevokeEventSelectView(events, user)
        await ctx.respond(
            content="Selecione o evento do qual deseja revogar suas aplicações:",
            view=view,
            ephemeral=True,
        )


class NoShowAcknowledgeView(discord.ui.View):
    """View with an acknowledge button for no-show alerts sent to admins."""

    def __init__(self):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="✅ OK",
            style=discord.ButtonStyle.secondary,
            custom_id="noshow_ack",
        )
        button.callback = self.on_ack
        self.add_item(button)

    async def on_ack(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content="✅ Alerta reconhecido. Mensagem será deletada em 5 segundos...",
            view=None,
        )
        await asyncio.sleep(5)
        try:
            await interaction.message.delete()
        except Exception:
            pass


class RevokeEventSelectView(discord.ui.View):
    """Dropdown to select which event to revoke applications from."""

    def __init__(self, events: list[Event], user: VATSIMUser):
        super().__init__(timeout=120)
        self.user = user
        self.events = {str(e.pk): e for e in events}

        options = [
            discord.SelectOption(
                label=e.name[:100],
                value=str(e.pk),
                description=f"{e.start_time:%d/%m %H:%M}z",
            )
            for e in events[:25]
        ]

        select = discord.ui.Select(
            placeholder="Escolha o evento...",
            options=options,
            custom_id="revoke_event_select",
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        event_id = int(interaction.data["values"][0])
        event = self.events.get(str(event_id))
        event_name = event.name if event else "Desconhecido"

        result = await revoke_all_applications(self.user.cid, event_id)

        total = result['pending_deleted'] + result['locked_cancelled'] + result['noshow_count']

        if total == 0:
            await interaction.response.edit_message(
                content="ℹ️ Você não possui aplicações ativas neste evento.",
                view=None,
            )
            return

        if result['noshow_count'] > 0:
            # No-show case: build message and alert admins
            msg = MSGS["noshow_revoked"].format(
                event_name=event_name,
                noshow_count=result['noshow_count'],
                pending_count=result['pending_deleted'] + result['locked_cancelled'],
            )
            await interaction.response.edit_message(content=msg, view=None)

            # Send no-show alerts to all admins
            await self._send_noshow_alerts(
                interaction.client, event, self.user, result['noshow_details']
            )

            # Update announcement message (position is now available)
            try:
                from bot.cogs.admin_cmds import update_announcement_message
                await update_announcement_message(interaction.client, event_id)
            except Exception as e:
                logger.error(f"Failed to update announcement after no-show: {e}")
        else:
            # Regular revocation (only pending/locked)
            msg = MSGS["application_revoked"].format(
                event_name=event_name,
                count=total,
            )
            await interaction.response.edit_message(content=msg, view=None)

    async def _send_noshow_alerts(self, bot, event, user, noshow_details):
        """Send no-show alert DMs to all admins. Falls back to event channel."""
        from bot.cogs.notifications import get_admin_discord_ids

        admin_ids = await get_admin_discord_ids()

        positions_text = "\n".join(
            f"📍 **{d['position']}** – {d['block']}" for d in noshow_details
        )

        msg = MSGS["noshow_admin_alert"].format(
            username=user.discord_username,
            cid=user.cid,
            event_name=event.name if event else "Desconhecido",
            positions=positions_text,
        )

        for admin_id in admin_ids:
            try:
                admin_user = await bot.fetch_user(int(admin_id))
                if admin_user:
                    view = NoShowAcknowledgeView()
                    await admin_user.send(content=msg, view=view)
            except discord.Forbidden:
                # DM failed, fall back to event announcement channel
                await self._send_noshow_to_fallback(bot, event, admin_id, msg)
            except Exception as e:
                logger.error(f"Failed to send no-show alert to admin {admin_id}: {e}")

    async def _send_noshow_to_fallback(self, bot, event, admin_id, msg):
        """Send no-show alert to the event channel when admin DM fails."""
        try:
            if not event or not event.discord_channel_id:
                return
            channel = bot.get_channel(int(event.discord_channel_id))
            if not channel:
                return
            guild = channel.guild
            admin_member = guild.get_member(int(admin_id))
            mention = admin_member.mention if admin_member else f"<@{admin_id}>"
            view = NoShowAcknowledgeView()
            await channel.send(content=f"{mention}\n\n{msg}", view=view)
        except Exception as e:
            logger.error(f"Failed to send no-show to fallback channel: {e}")


def setup(bot: discord.Bot):
    bot.add_cog(BookingCog(bot))
