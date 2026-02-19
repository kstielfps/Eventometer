"""
VATSIM API service layer.
Handles all communication with external VATSIM APIs.
"""

import logging
from datetime import datetime
from typing import Optional

import httpx
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

# Timeout for all VATSIM API calls
TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class VATSIMService:
    """Synchronous VATSIM API client for use in Django views/admin."""

    # ──────────────────────────────────────────
    # Events
    # ──────────────────────────────────────────

    @staticmethod
    def fetch_latest_events() -> list[dict]:
        """
        Fetch latest events from https://my.vatsim.net/api/v2/events/latest
        Returns the 'data' list from the response.
        """
        url = settings.VATSIM_EVENTS_URL
        try:
            response = httpx.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar eventos VATSIM: {e}")
            return []

    @staticmethod
    def fetch_event_by_id(event_id: int) -> dict | None:
        """
        Fetch a specific event by ID from https://my.vatsim.net/api/v2/events/view/:eventId
        Returns the event data dict or None if not found.
        """
        url = f"https://my.vatsim.net/api/v2/events/view/{event_id}"
        try:
            response = httpx.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
            return data.get("data")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Evento {event_id} não encontrado no VATSIM.")
                return None
            logger.error(f"Erro ao buscar evento {event_id}: {e}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar evento {event_id}: {e}")
            return None

    @staticmethod
    def import_event_by_id(event_id: int) -> tuple[bool, bool]:
        """
        Fetch and import a specific event by its VATSIM ID.
        Returns (was_created, was_updated).
        """
        from core.models import Event

        ev = VATSIMService.fetch_event_by_id(event_id)
        if not ev:
            return False, False

        vatsim_id = ev.get("id")
        if not vatsim_id:
            return False, False

        start_str = ev.get("start_time", "")
        end_str = ev.get("end_time", "")

        try:
            start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            logger.warning(f"Datas inválidas para evento {vatsim_id}.")
            return False, False

        defaults = {
            "name": ev.get("name", "")[:500],
            "link": ev.get("link", "")[:500],
            "banner_url": ev.get("banner", "")[:500],
            "start_time": start_time,
            "end_time": end_time,
            "short_description": ev.get("short_description", ""),
            "description": ev.get("description", ""),
            "organisers_json": ev.get("organisers"),
            "airports_json": ev.get("airports"),
            "routes_json": ev.get("routes"),
        }

        event, was_created = Event.objects.update_or_create(
            vatsim_id=vatsim_id,
            defaults=defaults,
        )

        return was_created, not was_created

    @staticmethod
    def import_events_to_db(vatsim_ids: list[int] | None = None) -> tuple[int, int]:
        """
        Fetch events and create/update Event records in the database.
        If vatsim_ids is provided, only import events matching those IDs.
        Returns (created_count, updated_count).
        """
        from core.models import Event  # avoid circular import

        events_data = VATSIMService.fetch_latest_events()
        created = 0
        updated = 0

        for ev in events_data:
            vatsim_id = ev.get("id")
            if not vatsim_id:
                continue

            # Skip events not in the selected list (if filtering)
            if vatsim_ids is not None and vatsim_id not in vatsim_ids:
                continue

            start_str = ev.get("start_time", "")
            end_str = ev.get("end_time", "")

            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                logger.warning(f"Datas inválidas para evento {vatsim_id}, pulando.")
                continue

            defaults = {
                "name": ev.get("name", "")[:500],
                "link": ev.get("link", "")[:500],
                "banner_url": ev.get("banner", "")[:500],
                "start_time": start_time,
                "end_time": end_time,
                "short_description": ev.get("short_description", ""),
                "description": ev.get("description", ""),
                "organisers_json": ev.get("organisers"),
                "airports_json": ev.get("airports"),
                "routes_json": ev.get("routes"),
            }

            _, was_created = Event.objects.update_or_create(
                vatsim_id=vatsim_id,
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated

    # ──────────────────────────────────────────
    # Members
    # ──────────────────────────────────────────

    @staticmethod
    def resolve_discord_id(discord_user_id: str) -> Optional[dict]:
        """
        Look up a VATSIM member by Discord user ID.
        GET https://api.vatsim.net/v2/members/discord/:discord_user_id
        Returns {"id": "...", "user_id": "..."} or None.
        """
        url = f"{settings.VATSIM_API_BASE}/members/discord/{discord_user_id}"
        headers = {}
        if settings.VATSIM_API_KEY:
            headers["Authorization"] = f"Token {settings.VATSIM_API_KEY}"

        try:
            response = httpx.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erro ao resolver Discord ID {discord_user_id}: {e}")
            return None

    @staticmethod
    def get_member_stats(cid: int) -> Optional[dict]:
        """
        Fetch ATC stats for a member.
        GET https://api.vatsim.net/v2/members/:cid/stats
        Returns the full stats dict or None.
        """
        url = f"{settings.VATSIM_API_BASE}/members/{cid}/stats"
        headers = {}
        if settings.VATSIM_API_KEY:
            headers["Authorization"] = f"Token {settings.VATSIM_API_KEY}"

        try:
            response = httpx.get(url, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Erro ao buscar stats do CID {cid}: {e}")
            return None

    @staticmethod
    def get_or_create_user(discord_user_id: str, discord_username: str = ""):
        """
        Full flow: resolve Discord ID → fetch stats → create/update VATSIMUser.
        Returns (VATSIMUser, created: bool) or (None, False) on failure.
        """
        from core.models import VATSIMUser, rating_from_stats

        # Step 1: Resolve Discord ID to CID
        member_data = VATSIMService.resolve_discord_id(discord_user_id)
        if not member_data or "user_id" not in member_data:
            logger.warning(f"Não foi possível resolver Discord ID {discord_user_id}")
            return None, False

        cid = int(member_data["user_id"])

        # Step 2: Fetch stats
        stats = VATSIMService.get_member_stats(cid)
        rating = rating_from_stats(stats) if stats else 1  # OBS fallback

        # Step 3: Create or update
        user, created = VATSIMUser.objects.update_or_create(
            cid=cid,
            defaults={
                "discord_user_id": discord_user_id,
                "discord_username": discord_username,
                "rating": rating,
                "stats_json": stats,
            },
        )

        return user, created


class AsyncVATSIMService:
    """
    Async version for use inside the Discord bot (which runs on asyncio).
    Uses httpx.AsyncClient for non-blocking HTTP calls.
    """

    @staticmethod
    async def resolve_discord_id(discord_user_id: str) -> Optional[dict]:
        url = f"{settings.VATSIM_API_BASE}/members/discord/{discord_user_id}"
        headers = {}
        if settings.VATSIM_API_KEY:
            headers["Authorization"] = f"Token {settings.VATSIM_API_KEY}"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"[async] Erro ao resolver Discord ID {discord_user_id}: {e}")
            return None

    @staticmethod
    async def get_member_stats(cid: int) -> Optional[dict]:
        url = f"{settings.VATSIM_API_BASE}/members/{cid}/stats"
        headers = {}
        if settings.VATSIM_API_KEY:
            headers["Authorization"] = f"Token {settings.VATSIM_API_KEY}"

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"[async] Erro ao buscar stats do CID {cid}: {e}")
            return None

    @staticmethod
    async def get_or_create_user(discord_user_id: str, discord_username: str = ""):
        """Async version of the full user resolution flow."""
        from asgiref.sync import sync_to_async
        from core.models import VATSIMUser, rating_from_stats

        member_data = await AsyncVATSIMService.resolve_discord_id(discord_user_id)
        if not member_data or "user_id" not in member_data:
            return None, False

        cid = int(member_data["user_id"])
        stats = await AsyncVATSIMService.get_member_stats(cid)
        rating = rating_from_stats(stats) if stats else 1

        user, created = await sync_to_async(VATSIMUser.objects.update_or_create)(
            cid=cid,
            defaults={
                "discord_user_id": discord_user_id,
                "discord_username": discord_username,
                "rating": rating,
                "stats_json": stats,
            },
        )

        return user, created
