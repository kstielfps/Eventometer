from datetime import timedelta, datetime

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html

from core.models import (
    AdminProfile,
    VATSIMUser,
    Event,
    EventICAO,
    EventPosition,
    PositionTemplate,
    TimeBlock,
    BookingApplication,
    EventStatus,
    ApplicationStatus,
)
from core.vatsim import VATSIMService


# ══════════════════════════════════════════════
# Inlines
# ══════════════════════════════════════════════


class EventPositionInline(admin.TabularInline):
    model = EventPosition
    extra = 1
    fields = ["position_template", "callsign_display"]
    readonly_fields = ["callsign_display"]
    autocomplete_fields = ["position_template"]
    
    def callsign_display(self, obj):
        if obj and obj.pk:
            return obj.callsign
        return "—"
    callsign_display.short_description = "Callsign Completo"


class EventICAOInline(admin.TabularInline):
    model = EventICAO
    extra = 1
    fields = ["icao", "position_count", "change_link"]
    readonly_fields = ["position_count", "change_link"]
    show_change_link = False  # We'll use custom change_link instead
    
    def position_count(self, obj):
        if obj and obj.pk:
            count = obj.positions.count()
            return f"{count} posição(ões)" if count > 0 else "Nenhuma posição"
        return "—"
    position_count.short_description = "Posições"
    
    def change_link(self, obj):
        if obj and obj.pk:
            from django.urls import reverse
            from django.utils.html import format_html
            url = reverse("admin:core_eventicao_change", args=[obj.pk])
            return format_html(
                '<a href="{}" class="button" style="padding: 5px 10px;">➕ Adicionar/Editar Posições</a>',
                url
            )
        return "Salve primeiro"
    change_link.short_description = "Gerenciar Posições"


class TimeBlockInline(admin.TabularInline):
    model = TimeBlock
    extra = 0
    readonly_fields = ("block_number", "start_time", "end_time")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class BookingApplicationInline(admin.TabularInline):
    model = BookingApplication
    extra = 0
    readonly_fields = ("user", "event_position", "time_block", "created_at")
    fields = ("user", "event_position", "time_block", "status", "notification_sent", "reminder_sent", "created_at")


class AdminProfileInline(admin.StackedInline):
    model = AdminProfile
    can_delete = False
    verbose_name = "Perfil de Admin do Bot"
    verbose_name_plural = "Perfil de Admin do Bot"
    fields = ("discord_id",)
    help_text = "Configure o Discord ID para permitir que este usuário use comandos admin no bot."


# ══════════════════════════════════════════════
# Model Admins
# ══════════════════════════════════════════════


@admin.register(PositionTemplate)
class PositionTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "min_rating_display", "description")
    search_fields = ("name",)

    def min_rating_display(self, obj):
        return obj.get_min_rating_display()
    min_rating_display.short_description = "Rating Mínimo"


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "discord_id")
    search_fields = ("user__username", "discord_id")
    autocomplete_fields = ["user"]
    fieldsets = (
        (None, {
            "fields": ("user", "discord_id"),
            "description": "Configure qual Discord ID pode usar comandos admin do bot. "
                          "O usuário Django associado deve ter permissão is_staff ou is_superuser.",
        }),
    )


@admin.register(VATSIMUser)
class VATSIMUserAdmin(admin.ModelAdmin):
    list_display = (
        "cid", "discord_username", "rating_display",
        "total_applications", "total_participations",
        "total_no_shows", "total_cancellations",
    )
    list_filter = ("rating",)
    search_fields = ("cid", "discord_username", "discord_user_id")
    readonly_fields = ("cid", "discord_user_id", "stats_json", "created_at", "updated_at")
    fieldsets = (
        ("Identificação", {
            "fields": ("cid", "discord_user_id", "discord_username", "rating", "stats_json"),
        }),
        ("Estatísticas de Participação", {
            "fields": (
                "total_applications", "total_participations",
                "total_no_shows", "total_cancellations",
            ),
        }),
        ("Admin", {
            "fields": ("admin_notes", "created_at", "updated_at"),
        }),
    )

    def rating_display(self, obj):
        return obj.get_rating_display()
    rating_display.short_description = "Rating"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "vatsim_id", "start_time", "end_time", "status", "total_blocks_display", "banner_preview")
    list_filter = ("status",)
    search_fields = ("name", "vatsim_id")
    readonly_fields = ("banner_preview_large", "matrix_link", "created_at", "updated_at")
    inlines = [EventICAOInline, TimeBlockInline]
    actions = ["generate_time_blocks", "open_for_bookings"]
    change_list_template = "admin/core/event/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "import-vatsim/",
                self.admin_site.admin_view(self.import_vatsim_preview),
                name="core_event_import_vatsim",
            ),
            path(
                "import-vatsim/confirm/",
                self.admin_site.admin_view(self.import_vatsim_confirm),
                name="core_event_import_vatsim_confirm",
            ),
            path(
                "<int:event_id>/matrix/",
                self.admin_site.admin_view(self.booking_matrix_view),
                name="core_event_matrix",
            ),
            path(
                "<int:event_id>/matrix/select/<int:position_id>/<int:user_id>/",
                self.admin_site.admin_view(self.select_applicant_for_position),
                name="core_event_select_applicant",
            ),
            path(
                "<int:event_id>/send-final-confirmations/",
                self.admin_site.admin_view(self.send_final_confirmations),
                name="core_event_send_final_confirmations",
            ),
        ]
        return custom_urls + urls

    def import_vatsim_preview(self, request):
        """Show a preview of VATSIM events with date filtering so admin can pick which to import."""
        events_data = VATSIMService.fetch_latest_events()

        # Parse dates for display & filtering
        date_from = request.GET.get("date_from", "")
        date_to = request.GET.get("date_to", "")

        parsed_events = []
        already_imported_ids = set(
            Event.objects.values_list("vatsim_id", flat=True)
        )

        for ev in events_data:
            vatsim_id = ev.get("id")
            start_str = ev.get("start_time", "")
            end_str = ev.get("end_time", "")

            try:
                start_time = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                end_time = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            # Apply date filter
            if date_from:
                try:
                    df = datetime.fromisoformat(date_from)
                    if start_time.date() < df.date():
                        continue
                except ValueError:
                    pass
            if date_to:
                try:
                    dt = datetime.fromisoformat(date_to)
                    if start_time.date() > dt.date():
                        continue
                except ValueError:
                    pass

            organisers = ev.get("organisers", [])
            org_text = ", ".join(
                f"{o.get('division', '?')}" for o in organisers
            ) if organisers else "—"

            airports = ev.get("airports", [])
            airport_text = ", ".join(a.get("icao", "") for a in airports) if airports else "—"

            parsed_events.append({
                "vatsim_id": vatsim_id,
                "name": ev.get("name", ""),
                "start_time": start_time,
                "end_time": end_time,
                "organisers": org_text,
                "airports": airport_text,
                "banner": ev.get("banner", ""),
                "already_imported": vatsim_id in already_imported_ids,
            })

        # Sort by start time
        parsed_events.sort(key=lambda e: e["start_time"])

        context = {
            **self.admin_site.each_context(request),
            "title": "Importar Eventos do VATSIM",
            "events": parsed_events,
            "date_from": date_from,
            "date_to": date_to,
            "total_count": len(parsed_events),
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/core/event/import_preview.html", context)

    def import_vatsim_confirm(self, request):
        """Import only the selected events."""
        if request.method != "POST":
            return HttpResponseRedirect(reverse("admin:core_event_import_vatsim"))

        selected_ids = request.POST.getlist("selected_events")
        if not selected_ids:
            self.message_user(request, "Nenhum evento selecionado.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:core_event_import_vatsim"))

        vatsim_ids = [int(vid) for vid in selected_ids]
        created, updated = VATSIMService.import_events_to_db(vatsim_ids=vatsim_ids)
        self.message_user(
            request,
            f"Importação concluída: {created} novo(s), {updated} atualizado(s).",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:core_event_changelist"))

    def booking_matrix_view(self, request, event_id):
        """Display a matrix view of positions × time blocks with booking status."""
        try:
            event = Event.objects.prefetch_related(
                "time_blocks",
                "icaos__positions__position_template",
                "icaos__positions__applications__user",
            ).get(pk=event_id)
        except Event.DoesNotExist:
            self.message_user(request, "Evento não encontrado.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:core_event_changelist"))

        # Get all positions and blocks
        positions = EventPosition.objects.filter(
            event_icao__event=event
        ).select_related("event_icao", "position_template").order_by("event_icao__icao", "position_template__name")

        blocks = event.time_blocks.all().order_by("block_number")

        # Build matrix: {position_id: {block_id: [applications]}}
        matrix = {}
        for position in positions:
            matrix[position.pk] = {}
            for block in blocks:
                apps = BookingApplication.objects.filter(
                    event_position=position,
                    time_block=block,
                ).select_related("user").order_by("-status", "created_at")
                matrix[position.pk][block.pk] = list(apps)

        # Build display data
        matrix_data = []
        for position in positions:
            # Get all applicants for this position
            all_apps = BookingApplication.objects.filter(
                event_position=position
            ).select_related("user", "time_block").order_by("user__discord_username", "time_block__block_number")
            
            # Group by user and count blocks
            from collections import defaultdict
            user_blocks = defaultdict(lambda: {"blocks": [], "statuses": [], "apps": []})
            for app in all_apps:
                user_blocks[app.user]["blocks"].append(app.time_block)
                user_blocks[app.user]["statuses"].append(app.get_status_display())
                user_blocks[app.user]["apps"].append(app)
            
            # Sort by number of blocks (descending)
            applicants = []
            for user, data in user_blocks.items():
                # Check if user has any locked/confirmed applications
                locked_count = sum(1 for app in data["apps"] if app.status in [ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED])
                rejected_count = sum(1 for app in data["apps"] if app.status == ApplicationStatus.REJECTED)
                
                applicants.append({
                    "user": user,
                    "block_count": len(data["blocks"]),
                    "blocks": data["blocks"],
                    "statuses": data["statuses"],
                    "locked_count": locked_count,
                    "rejected_count": rejected_count,
                    "is_selected": locked_count > 0,
                })
            applicants.sort(key=lambda x: (x["is_selected"], x["block_count"]), reverse=True)
            
            row = {
                "position": position,
                "applicants": applicants,
                "cells": []
            }
            for block in blocks:
                apps = matrix[position.pk][block.pk]
                
                # Determine cell status
                if not apps:
                    status = "empty"
                    display = "—"
                    css_class = "status-empty"
                else:
                    locked = [a for a in apps if a.status in [ApplicationStatus.LOCKED, ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED]]
                    pending = [a for a in apps if a.status == ApplicationStatus.PENDING]
                    
                    if locked:
                        status = "locked"
                        app = locked[0]
                        display = f"{app.user.discord_username} ({app.get_status_display()})"
                        css_class = "status-locked"
                    elif pending:
                        status = "pending"
                        display = f"{len(pending)} aplicações"
                        css_class = "status-pending"
                    else:
                        status = "rejected"
                        display = f"{len(apps)} rejeitadas"
                        css_class = "status-rejected"
                
                row["cells"].append({
                    "status": status,
                    "display": display,
                    "css_class": css_class,
                    "applications": apps,
                    "position_id": position.pk,
                    "block_id": block.pk,
                })
            
            matrix_data.append(row)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Matriz de Bookings: {event.name}",
            "event": event,
            "blocks": blocks,
            "matrix_data": matrix_data,
            "opts": self.model._meta,
        }
        return TemplateResponse(request, "admin/core/event/booking_matrix.html", context)

    def select_applicant_for_position(self, request, event_id, position_id, user_id):
        """
        Select a specific applicant for all their applied blocks in a position.
        - Mark their applications as LOCKED (selected, waiting confirmation)
        - Mark all OTHER applications for those blocks as REJECTED
        - Queue notifications to be sent
        """
        from django.db.models import Q
        
        try:
            event = Event.objects.get(pk=event_id)
            position = EventPosition.objects.get(pk=position_id)
            from core.models import VATSIMUser
            user = VATSIMUser.objects.get(pk=user_id)
        except (Event.DoesNotExist, EventPosition.DoesNotExist, VATSIMUser.DoesNotExist):
            self.message_user(request, "Evento, posição ou usuário não encontrado.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:core_event_matrix", args=[event_id]))
        
        # Get all applications from this user for this position
        user_apps = BookingApplication.objects.filter(
            event_position=position,
            user=user,
        ).select_related("time_block")
        
        if not user_apps.exists():
            self.message_user(request, "Nenhuma aplicação encontrada para este usuário nesta posição.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:core_event_matrix", args=[event_id]))
        
        # Get the block IDs
        block_ids = [app.time_block_id for app in user_apps]
        
        # Update user's applications to LOCKED and queue notification
        updated_count = user_apps.update(
            status=ApplicationStatus.LOCKED,
            notification_sent=True,  # Queue for notification sending
        )
        
        # Update all OTHER applications for these blocks in THIS position to REJECTED and queue rejection notification
        rejected_count = BookingApplication.objects.filter(
            event_position=position,
            time_block_id__in=block_ids,
        ).exclude(user=user).update(
            status=ApplicationStatus.REJECTED,
            rejection_sent=True,  # Queue for rejection notification
        )
        
        # Update THIS user's applications for OTHER positions in the same blocks to REJECTED
        # (User can only control one position per block)
        other_positions_rejected = BookingApplication.objects.filter(
            user=user,
            time_block_id__in=block_ids,
            event_position__event_icao__event=event,
        ).exclude(event_position=position).update(
            status=ApplicationStatus.REJECTED,
            rejection_sent=True,  # Queue for rejection notification
        )
        
        total_rejected = rejected_count + other_positions_rejected
        
        self.message_user(
            request,
            f"✅ {user.discord_username} selecionado para {updated_count} bloco(s). "
            f"{rejected_count} aplicação(ões) de outros usuários rejeitadas. "
            f"{other_positions_rejected} aplicação(ões) do mesmo usuário em outras posições rejeitadas. "
            f"As notificações serão enviadas automaticamente pelo bot.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:core_event_matrix", args=[event_id]))

    def send_final_confirmations(self, request, event_id):
        """
        Send final confirmation notifications to all CONFIRMED users in this event.
        Updates their status to FULL_CONFIRMED and queues reminder notification.
        """
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            self.message_user(request, "Evento não encontrado.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:core_event_changelist"))
        
        # Get all CONFIRMED applications for this event
        confirmed_apps = BookingApplication.objects.filter(
            event_position__event_icao__event=event,
            status=ApplicationStatus.CONFIRMED,
        )
        
        count = confirmed_apps.count()
        if count == 0:
            self.message_user(request, "Nenhuma aplicação confirmada encontrada para este evento.", messages.WARNING)
            return HttpResponseRedirect(reverse("admin:core_event_matrix", args=[event_id]))
        
        # Update to FULL_CONFIRMED and queue reminder notification
        confirmed_apps.update(
            status=ApplicationStatus.FULL_CONFIRMED,
            reminder_sent=True,  # Queue for reminder/final confirmation sending
        )
        
        self.message_user(
            request,
            f"✅ Confirmação final enviada para {count} usuário(s). As notificações serão enviadas automaticamente pelo bot.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(reverse("admin:core_event_matrix", args=[event_id]))

    fieldsets = (
        ("Evento VATSIM", {
            "fields": (
                "vatsim_id", "name", "link", "banner_url", "banner_preview_large",
                "start_time", "end_time",
                "short_description", "description",
            ),
        }),
        ("Dados Importados (JSON)", {
            "classes": ("collapse",),
            "fields": ("organisers_json", "airports_json", "routes_json"),
        }),
        ("Configuração de Booking", {
            "fields": ("status", "block_duration_minutes", "matrix_link"),
        }),
        ("Discord", {
            "classes": ("collapse",),
            "fields": ("discord_channel_id", "discord_message_id"),
        }),
        ("Metadados", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    def total_blocks_display(self, obj):
        return obj.total_blocks
    total_blocks_display.short_description = "Blocos"

    def banner_preview(self, obj):
        if obj.banner_url:
            return format_html('<img src="{}" style="max-height:40px;" />', obj.banner_url)
        return "–"
    banner_preview.short_description = "Banner"

    def banner_preview_large(self, obj):
        if obj.banner_url:
            return format_html('<img src="{}" style="max-width:600px; border-radius:8px;" />', obj.banner_url)
        return "Sem banner"
    banner_preview_large.short_description = "Preview do Banner"

    def matrix_link(self, obj):
        if obj.pk:
            from django.urls import reverse
            url = reverse("admin:core_event_matrix", args=[obj.pk])
            return format_html(
                '<a class="button" href="{}" style="padding: 10px 15px; background: #417690; color: white; text-decoration: none; border-radius: 4px; display: inline-block;">'
                '📊 Ver Matriz de Bookings'
                '</a>',
                url
            )
        return "Salve o evento primeiro"
    matrix_link.short_description = "Matriz de Posições × Blocos"

    # ── Custom Actions ──

    @admin.action(description="⏱ Gerar Blocos de Horário")
    def generate_time_blocks(self, request, queryset):
        total_created = 0
        for event in queryset:
            if event.total_blocks <= 0:
                self.message_user(
                    request,
                    f"Evento '{event.name}': duração/bloco inválido.",
                    messages.WARNING,
                )
                continue

            # Clear old blocks for this event
            TimeBlock.objects.filter(event=event).delete()

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

        self.message_user(
            request,
            f"{total_created} blocos de horário gerados com sucesso.",
            messages.SUCCESS,
        )

    @admin.action(description="✅ Abrir para Bookings")
    def open_for_bookings(self, request, queryset):
        count = 0
        for event in queryset:
            if not event.time_blocks.exists():
                self.message_user(
                    request,
                    f"Evento '{event.name}' não possui blocos de horário. Gere-os antes.",
                    messages.WARNING,
                )
                continue
            if not EventICAO.objects.filter(event=event).exists():
                self.message_user(
                    request,
                    f"Evento '{event.name}' não possui ICAOs configurados.",
                    messages.WARNING,
                )
                continue

            event.status = EventStatus.OPEN
            event.save(update_fields=["status"])
            count += 1

        if count:
            self.message_user(
                request,
                f"{count} evento(s) aberto(s) para bookings.",
                messages.SUCCESS,
            )


@admin.register(EventICAO)
class EventICAOAdmin(admin.ModelAdmin):
    list_display = ("icao", "event", "position_count_display")
    list_filter = ("event",)
    search_fields = ("icao",)
    inlines = [EventPositionInline]
    
    def position_count_display(self, obj):
        count = obj.positions.count()
        return f"{count} posição(ões)"
    position_count_display.short_description = "Total de Posições"


@admin.register(EventPosition)
class EventPositionAdmin(admin.ModelAdmin):
    list_display = ("callsign_display", "event_display", "min_rating_display")
    list_filter = ("event_icao__event", "position_template")
    search_fields = ("event_icao__icao", "position_template__name")

    def callsign_display(self, obj):
        return obj.callsign
    callsign_display.short_description = "Callsign"

    def event_display(self, obj):
        return obj.event.name
    event_display.short_description = "Evento"

    def min_rating_display(self, obj):
        return obj.position_template.get_min_rating_display()
    min_rating_display.short_description = "Rating Mínimo"


@admin.register(TimeBlock)
class TimeBlockAdmin(admin.ModelAdmin):
    list_display = ("event", "block_number", "start_time", "end_time")
    list_filter = ("event",)


@admin.register(BookingApplication)
class BookingApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "user_display", "position_display", "block_display",
        "status", "notification_sent", "reminder_sent", "dm_failure_display",
    )
    list_filter = (
        "status",
        "dm_failure_notified",
        "event_position__event_icao__event",
        "event_position__event_icao__icao",
        "event_position__position_template",
    )
    search_fields = (
        "user__discord_username", "user__cid",
        "event_position__event_icao__icao",
    )
    list_editable = ("status",)
    readonly_fields = ("created_at", "updated_at", "dm_failure_display_detail")
    actions = [
        "lock_selected", "send_notifications",
        "send_reminders", "send_rejections",
        "mark_no_show",
    ]
    
    fieldsets = (
        ("Aplicação", {
            "fields": ("user", "event_position", "time_block", "status"),
        }),
        ("Notificações", {
            "fields": (
                "notification_sent", "reminder_sent", "rejection_sent",
                "dm_failure_display_detail",
            ),
        }),
        ("Metadados", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )

    def user_display(self, obj):
        return f"{obj.user.discord_username} ({obj.user.cid})"
    user_display.short_description = "Membro"

    def position_display(self, obj):
        return obj.event_position.callsign
    position_display.short_description = "Posição"

    def block_display(self, obj):
        return str(obj.time_block)
    block_display.short_description = "Bloco"
    
    def dm_failure_display(self, obj):
        """Display DM failure status in list view."""
        if obj.dm_failure_count == 0:
            return "✅ OK"
        elif obj.dm_failure_count < 2:
            return f"⚠️ {obj.dm_failure_count} falha(s)"
        elif obj.fallback_channel_id:
            return "📢 Canal Fallback"
        else:
            return f"❌ {obj.dm_failure_count} falha(s)"
    dm_failure_display.short_description = "Status DM"
    
    def dm_failure_display_detail(self, obj):
        """Display detailed DM failure information in detail view."""
        from django.utils.safestring import mark_safe
        if obj.dm_failure_count == 0:
            return mark_safe('<span style="color: green;">✅ Nenhuma falha de comunicação</span>')
        
        if obj.fallback_channel_id:
            html = (
                f'<div style="padding: 10px; background: #d1ecf1; border-left: 4px solid #0c5460; border-radius: 4px;">'
                f'<strong style="color: #0c5460;">📢 Canal de fallback criado</strong><br>'
                f'<small>ID do Canal: {obj.fallback_channel_id}</small><br>'
                f'<small style="color: #666;">Um canal Discord foi criado para notificar o usuário</small>'
                f'</div>'
            )
        else:
            color = "orange" if obj.dm_failure_count < 2 else "red"
            status = "Canal fallback será criado" if obj.dm_failure_count >= 2 else "Tentando novamente"
            
            html = (
                f'<div style="padding: 10px; background: #fff3cd; border-left: 4px solid {color}; border-radius: 4px;">'
                f'<strong style="color: {color};">⚠️ {obj.dm_failure_count} tentativa(s) de DM falharam</strong><br>'
                f'<small>Status: {status}</small><br>'
                f'<small style="color: #666;">Usuário provavelmente bloqueou DMs do bot</small>'
                f'</div>'
            )
        from django.utils.safestring import mark_safe
        return mark_safe(html)
    dm_failure_display_detail.short_description = "Status de Comunicação"

    # ── Custom Actions ──

    @admin.action(description="🔒 Travar Selecionados (Lock)")
    def lock_selected(self, request, queryset):
        """
        Lock selected applications.
        Validates that the same user is not locked in another position for the same block,
        and that the position+block is not already locked by another user.
        """
        locked_count = 0
        for app in queryset.filter(status=ApplicationStatus.PENDING):
            # Check: position+block already locked?
            existing_lock = BookingApplication.objects.filter(
                event_position=app.event_position,
                time_block=app.time_block,
                status__in=[
                    ApplicationStatus.LOCKED,
                    ApplicationStatus.CONFIRMED,
                    ApplicationStatus.FULL_CONFIRMED,
                ],
            ).exclude(pk=app.pk).exists()

            if existing_lock:
                self.message_user(
                    request,
                    f"Posição {app.event_position.callsign} no bloco "
                    f"{app.time_block.block_number} já está travada.",
                    messages.WARNING,
                )
                continue

            # Check: user already locked in another position for this block?
            user_locked = BookingApplication.objects.filter(
                user=app.user,
                time_block=app.time_block,
                status__in=[
                    ApplicationStatus.LOCKED,
                    ApplicationStatus.CONFIRMED,
                    ApplicationStatus.FULL_CONFIRMED,
                ],
            ).exclude(pk=app.pk).exists()

            if user_locked:
                self.message_user(
                    request,
                    f"{app.user.discord_username} já está travado em outra posição "
                    f"no bloco {app.time_block.block_number}.",
                    messages.WARNING,
                )
                continue

            app.status = ApplicationStatus.LOCKED
            app.save(update_fields=["status", "updated_at"])
            locked_count += 1

        if locked_count:
            self.message_user(
                request,
                f"{locked_count} aplicação(ões) travada(s) com sucesso.",
                messages.SUCCESS,
            )

    @admin.action(description="📨 Enviar Notificações de Seleção")
    def send_notifications(self, request, queryset):
        """Mark locked applications as 'notification_sent'. Bot will pick these up."""
        count = queryset.filter(
            status=ApplicationStatus.LOCKED,
            notification_sent=False,
        ).update(notification_sent=True)
        self.message_user(
            request,
            f"{count} notificação(ões) marcada(s) para envio.",
            messages.SUCCESS,
        )

    @admin.action(description="🔔 Enviar Lembretes")
    def send_reminders(self, request, queryset):
        count = queryset.filter(
            status__in=[ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED],
            reminder_sent=False,
        ).update(reminder_sent=True)
        self.message_user(
            request,
            f"{count} lembrete(s) marcado(s) para envio.",
            messages.SUCCESS,
        )

    @admin.action(description="❌ Enviar Rejeições")
    def send_rejections(self, request, queryset):
        count = queryset.filter(
            status=ApplicationStatus.REJECTED,
            rejection_sent=False,
        ).update(rejection_sent=True)
        self.message_user(
            request,
            f"{count} rejeição(ões) marcada(s) para envio.",
            messages.SUCCESS,
        )

    @admin.action(description="🚫 Marcar como No Show")
    def mark_no_show(self, request, queryset):
        count = 0
        for app in queryset.filter(
            status__in=[ApplicationStatus.CONFIRMED, ApplicationStatus.FULL_CONFIRMED]
        ):
            app.status = ApplicationStatus.NO_SHOW
            app.save(update_fields=["status", "updated_at"])
            # Update user stats
            app.user.total_no_shows += 1
            app.user.save(update_fields=["total_no_shows"])
            count += 1
        self.message_user(request, f"{count} marcado(s) como No Show.", messages.WARNING)


# ══════════════════════════════════════════════
# Customize Django User Admin to include AdminProfile inline
# ══════════════════════════════════════════════

class CustomUserAdmin(UserAdmin):
    """Extended UserAdmin with AdminProfile inline for bot admin Discord ID."""
    inlines = [AdminProfileInline]


# Unregister the default UserAdmin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
