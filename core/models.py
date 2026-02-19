from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator


# ──────────────────────────────────────────────
# ATC Rating choices (VATSIM standard)
# ──────────────────────────────────────────────
class ATCRating(models.IntegerChoices):
    OBS = 1, "OBS"
    S1 = 2, "S1"
    S2 = 3, "S2"
    S3 = 4, "S3"
    C1 = 5, "C1"
    C2 = 6, "C2"
    C3 = 7, "C3"
    I1 = 8, "I1"
    I2 = 9, "I2"
    I3 = 10, "I3"
    SUP = 11, "SUP"
    ADM = 12, "ADM"


RATING_STAT_KEYS = ["s1", "s2", "s3", "c1", "c2", "c3", "i1", "i2", "i3", "sup", "adm"]

STAT_KEY_TO_RATING = {
    "s1": ATCRating.S1,
    "s2": ATCRating.S2,
    "s3": ATCRating.S3,
    "c1": ATCRating.C1,
    "c2": ATCRating.C2,
    "c3": ATCRating.C3,
    "i1": ATCRating.I1,
    "i2": ATCRating.I2,
    "i3": ATCRating.I3,
    "sup": ATCRating.SUP,
    "adm": ATCRating.ADM,
}


def rating_from_stats(stats: dict) -> int:
    """
    Determine the highest ATC rating from VATSIM stats.
    A rating is considered achieved if the user has > 1 hour on it.
    Returns the ATCRating integer value (highest found) or OBS (1).
    """
    highest = ATCRating.OBS
    for key in RATING_STAT_KEYS:
        hours = stats.get(key, 0)
        if hours and float(hours) > 1:
            candidate = STAT_KEY_TO_RATING[key]
            if candidate > highest:
                highest = candidate
    return highest


# ──────────────────────────────────────────────
# Event status choices
# ──────────────────────────────────────────────
class EventStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    OPEN = "open", "Aberto para Bookings"
    REVIEW = "review", "Em Revisão"
    LOCKED = "locked", "Posições Travadas"
    ARCHIVED = "archived", "Arquivado"


# ──────────────────────────────────────────────
# Application status choices
# ──────────────────────────────────────────────
class ApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pendente"
    LOCKED = "locked", "Selecionado (Aguardando Confirmação)"
    CONFIRMED = "confirmed", "Confirmado"
    FULL_CONFIRMED = "full_confirmed", "Confirmação Final"
    REJECTED = "rejected", "Não Selecionado"
    CANCELLED = "cancelled", "Cancelado pelo Usuário"
    NO_SHOW = "no_show", "No Show"


# ══════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════


class AdminProfile(models.Model):
    """
    Profile for Django users who can use admin Discord commands.
    Links a Django User (staff/admin) to their Discord ID.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="admin_profile",
        verbose_name="Usuário Django",
    )
    discord_id = models.CharField(
        max_length=20, unique=True, db_index=True,
        verbose_name="Discord ID",
        help_text="Discord User ID para autorizar comandos admin no bot",
    )
    
    class Meta:
        verbose_name = "Perfil de Admin do Bot"
        verbose_name_plural = "Perfis de Admin do Bot"
    
    def __str__(self):
        return f"{self.user.username} ({self.discord_id})"


class VATSIMUser(models.Model):
    """A VATSIM member that has interacted with the bot."""

    cid = models.IntegerField(primary_key=True, verbose_name="CID")
    discord_user_id = models.CharField(
        max_length=20, unique=True, db_index=True,
        verbose_name="Discord User ID",
    )
    discord_username = models.CharField(max_length=255, blank=True, default="")
    rating = models.IntegerField(
        choices=ATCRating.choices,
        default=ATCRating.OBS,
        verbose_name="Rating ATC",
    )
    stats_json = models.JSONField(
        blank=True, null=True,
        verbose_name="Estatísticas VATSIM (JSON)",
        help_text="Raw stats from the VATSIM API",
    )

    # ── Participation tracking ──
    total_applications = models.IntegerField(default=0, verbose_name="Total de Aplicações")
    total_participations = models.IntegerField(default=0, verbose_name="Participações")
    total_no_shows = models.IntegerField(default=0, verbose_name="No Shows")
    total_cancellations = models.IntegerField(default=0, verbose_name="Cancelamentos")

    admin_notes = models.TextField(blank=True, default="", verbose_name="Notas do Admin")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Membro VATSIM"
        verbose_name_plural = "Membros VATSIM"
        ordering = ["-total_participations"]

    def __str__(self):
        return f"{self.discord_username} (CID: {self.cid}) – {self.get_rating_display()}"


class Event(models.Model):
    """An event imported from the VATSIM API."""

    vatsim_id = models.IntegerField(unique=True, null=True, blank=True, verbose_name="VATSIM Event ID")
    name = models.CharField(max_length=500, verbose_name="Nome do Evento")
    link = models.URLField(max_length=500, blank=True, default="", verbose_name="Link")
    banner_url = models.URLField(max_length=500, blank=True, default="", verbose_name="Banner URL")
    start_time = models.DateTimeField(verbose_name="Início")
    end_time = models.DateTimeField(verbose_name="Fim")
    short_description = models.TextField(blank=True, default="", verbose_name="Descrição Curta")
    description = models.TextField(blank=True, default="", verbose_name="Descrição Completa")

    # Organisers / metadata stored as JSON
    organisers_json = models.JSONField(blank=True, null=True, verbose_name="Organizadores (JSON)")
    airports_json = models.JSONField(blank=True, null=True, verbose_name="Aeroportos (JSON)")
    routes_json = models.JSONField(blank=True, null=True, verbose_name="Rotas (JSON)")

    # ── Booking configuration ──
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.DRAFT,
        verbose_name="Status",
    )
    block_duration_minutes = models.IntegerField(
        default=60,
        validators=[MinValueValidator(15)],
        verbose_name="Duração do Bloco (minutos)",
        help_text="Tamanho de cada bloco de horário (ex: 30, 60, 120)",
    )

    # Discord message reference
    discord_channel_id = models.CharField(max_length=20, blank=True, default="")
    discord_message_id = models.CharField(max_length=20, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"
        ordering = ["-start_time"]

    def __str__(self):
        return f"{self.name} ({self.start_time:%d/%m/%Y %H:%Mz})"

    @property
    def duration_minutes(self):
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)

    @property
    def total_blocks(self):
        if self.block_duration_minutes <= 0:
            return 0
        return self.duration_minutes // self.block_duration_minutes


class EventICAO(models.Model):
    """An ICAO location assigned to an event (e.g. SBBR, SBSP)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="icaos")
    icao = models.CharField(max_length=4, verbose_name="Código ICAO")

    class Meta:
        verbose_name = "ICAO do Evento"
        verbose_name_plural = "ICAOs do Evento"
        unique_together = ("event", "icao")
        ordering = ["icao"]

    def __str__(self):
        return f"{self.icao} – {self.event.name}"


class PositionTemplate(models.Model):
    """
    Pre-created position types available system-wide (APP, TWR, GND, CTR, DEL, etc.).
    Created once in Django Admin and reused across events.
    """

    name = models.CharField(max_length=10, unique=True, verbose_name="Posição")
    min_rating = models.IntegerField(
        choices=ATCRating.choices,
        default=ATCRating.S1,
        verbose_name="Rating Mínimo",
        help_text="Rating mínimo necessário para controlar esta posição",
    )
    description = models.CharField(max_length=100, blank=True, default="", verbose_name="Descrição")

    class Meta:
        verbose_name = "Template de Posição"
        verbose_name_plural = "Templates de Posição"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (Mín: {self.get_min_rating_display()})"


class EventPosition(models.Model):
    """
    A specific position for an ICAO at an event.
    Example: SBBR_APP, SBBR_TWR, SBSP_GND
    """

    event_icao = models.ForeignKey(
        EventICAO, on_delete=models.CASCADE, related_name="positions",
        verbose_name="ICAO do Evento",
    )
    position_template = models.ForeignKey(
        PositionTemplate, on_delete=models.CASCADE,
        verbose_name="Posição",
    )

    class Meta:
        verbose_name = "Posição do Evento"
        verbose_name_plural = "Posições do Evento"
        unique_together = ("event_icao", "position_template")
        ordering = ["event_icao__icao", "position_template__name"]

    def __str__(self):
        return f"{self.event_icao.icao}_{self.position_template.name}"

    @property
    def callsign(self):
        return f"{self.event_icao.icao}_{self.position_template.name}"

    @property
    def min_rating(self):
        return self.position_template.min_rating

    @property
    def event(self):
        return self.event_icao.event


class TimeBlock(models.Model):
    """
    A time slot for an event, auto-generated from event duration and block size.
    Example: Block 1 = 22:00–23:00, Block 2 = 23:00–00:00
    """

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="time_blocks")
    block_number = models.IntegerField(verbose_name="Número do Bloco")
    start_time = models.DateTimeField(verbose_name="Início do Bloco")
    end_time = models.DateTimeField(verbose_name="Fim do Bloco")

    class Meta:
        verbose_name = "Bloco de Horário"
        verbose_name_plural = "Blocos de Horário"
        unique_together = ("event", "block_number")
        ordering = ["event", "block_number"]

    def __str__(self):
        return f"Bloco {self.block_number}: {self.start_time:%H:%M}–{self.end_time:%H:%M}z"


class BookingApplication(models.Model):
    """
    A user's application for a specific position at a specific time block.
    """

    user = models.ForeignKey(
        VATSIMUser, on_delete=models.CASCADE, related_name="applications",
        verbose_name="Membro",
    )
    event_position = models.ForeignKey(
        EventPosition, on_delete=models.CASCADE, related_name="applications",
        verbose_name="Posição",
    )
    time_block = models.ForeignKey(
        TimeBlock, on_delete=models.CASCADE, related_name="applications",
        verbose_name="Bloco de Horário",
    )

    status = models.CharField(
        max_length=20,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.PENDING,
        verbose_name="Status",
    )

    # Notification tracking
    notification_sent = models.BooleanField(default=False, verbose_name="Notificação Enviada")
    reminder_sent = models.BooleanField(default=False, verbose_name="Lembrete Enviado")
    rejection_sent = models.BooleanField(default=False, verbose_name="Rejeição Enviada")
    
    # DM failure tracking
    dm_failure_count = models.IntegerField(default=0, verbose_name="Tentativas de DM Falhadas")
    dm_failure_notified = models.BooleanField(default=False, verbose_name="Admin Notificado sobre Falha de DM")
    fallback_channel_id = models.CharField(max_length=30, blank=True, null=True, verbose_name="ID do Canal de Fallback")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Aplicação de Booking"
        verbose_name_plural = "Aplicações de Booking"
        # A user can only apply once per position per time block
        unique_together = ("user", "event_position", "time_block")
        ordering = ["time_block__block_number", "event_position"]

    def __str__(self):
        return (
            f"{self.user.discord_username} → "
            f"{self.event_position.callsign} "
            f"(Bloco {self.time_block.block_number}) – "
            f"{self.get_status_display()}"
        )
