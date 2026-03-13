"""
PT-BR strings and embed builders for the Eventometer bot.
All user-facing text lives here for easy maintenance.
"""

import discord
from datetime import datetime


# ══════════════════════════════════════════════
# Mensagens de texto
# ══════════════════════════════════════════════

MSGS = {
    # ── Erros ──
    "err_no_vatsim": (
        "❌ Não foi possível encontrar sua conta VATSIM vinculada ao Discord.\n"
        "Certifique-se de que seu Discord está vinculado em https://my.vatsim.net"
    ),
    "err_no_events": "📭 Não há eventos abertos para booking no momento.",
    "err_generic": "❌ Ocorreu um erro. Tente novamente mais tarde.",
    "err_no_positions": (
        "⚠️ Não há posições disponíveis para o seu rating (**{rating}**).\n"
        "Posições requerem um rating mais alto."
    ),
    "err_already_applied": "⚠️ Você já aplicou para esta posição neste bloco.",

    # ── Booking Flow ──
    "welcome": (
        "👋 Bem-vindo ao sistema de booking ATC!\n"
        "Sua conta VATSIM foi identificada:\n\n"
        "**CID:** {cid}\n"
        "**Rating:** {rating}\n\n"
        "Selecione um evento abaixo para aplicar:"
    ),
    "select_event": "📋 Selecione o evento:",
    "select_blocks": (
        "⏰ Selecione os blocos de horário em que você está **disponível**.\n"
        "Você pode selecionar múltiplos blocos.\n\n"
        "**Evento:** {event_name}\n"
        "**Horário:** {start} – {end} UTC"
    ),
    "select_position": (
        "🎯 Selecione as posições que deseja aplicar (pode selecionar mais de uma):\n\n"
        "Apenas posições compatíveis com seu rating (**{rating}**) são mostradas."
    ),

    # ── Confirmações ──
    "application_summary": (
        "✅ **Aplicação Registrada!**\n\n"
        "**Evento:** {event_name}\n"
        "**Posições:** {position}\n"
        "**Blocos:** {blocks}\n\n"
        "Você receberá uma mensagem caso seja selecionado para alguma posição.\n"
        "Use `/revogar` para cancelar todas as suas aplicações neste evento."
    ),
    "application_revoked": (
        "🗑️ Suas aplicações para o evento **{event_name}** foram revogadas com sucesso.\n"
        "Total de aplicações removidas: **{count}**"
    ),

    # ── Notificações Admin → Usuário ──
    "locked_notification": (
        "🎉 **Parabéns!** Você foi selecionado para uma posição!\n\n"
        "**Evento:** {event_name}\n"
        "**Posição:** {position}\n"
        "**Horário:** {time}\n\n"
        "Clique no botão abaixo para **confirmar** sua participação."
    ),
    "reminder_notification": (
        "🔔 **Lembrete de Evento!**\n\n"
        "Você está confirmado para controlar:\n\n"
        "**Evento:** {event_name}\n"
        "**Posição:** {position}\n"
        "**ICAO:** {icao}\n"
        "**Horário:** {time}\n\n"
        "Confirme sua presença clicando no botão abaixo."
    ),
    "rejection_notification": (
        "📋 Obrigado por sua aplicação para o evento **{event_name}**!\n\n"
        "Infelizmente, neste momento, todas as posições já foram preenchidas.\n"
        "Agradecemos o seu interesse e esperamos contar com você em próximos eventos! 💙"
    ),
    "confirmed": "✅ Sua participação foi **confirmada**! Nos vemos no evento!",
    "full_confirmed": "✅ **Confirmação final** registrada! Nos vemos no evento! 🎮",

    # ── No-Show ──
    "noshow_admin_alert": (
        "⚠️ **ALERTA DE NO-SHOW!**\n\n"
        "O controlador **{username}** (CID: {cid}) revogou sua participação confirmada:\n\n"
        "**Evento:** {event_name}\n"
        "**Posições afetadas:**\n{positions}\n\n"
        "As vagas estão agora disponíveis para seleção via `/selecionarreserva`."
    ),
    "noshow_revoked": (
        "⚠️ **Aplicações revogadas com No-Show registrado**\n\n"
        "**Evento:** {event_name}\n"
        "**Posições com No-Show:** {noshow_count}\n"
        "**Aplicações pendentes/travadas canceladas:** {pending_count}\n\n"
        "Os administradores foram notificados.\n"
        "Você recebeu **{noshow_count} no-show(s)** no seu registro."
    ),
}


# ══════════════════════════════════════════════
# Labels de componentes
# ══════════════════════════════════════════════

LABELS = {
    "btn_book": "📋 Aplicar para Posição",
    "btn_confirm": "✅ Confirmar Participação",
    "btn_cancel_confirm": "❌ Cancelar Participação",
    "btn_final_confirm": "✅ Confirmação Final",
    "btn_cancel_final": "❌ Cancelar Confirmação",
    "btn_revoke": "🗑️ Revogar Aplicações",
    "select_event_placeholder": "Escolha um evento...",
    "select_blocks_placeholder": "Selecione os blocos de horário...",
    "select_position_placeholder": "Selecione as posições...",
}


# ══════════════════════════════════════════════
# Embed Builders
# ══════════════════════════════════════════════


def build_event_embed(event, available_positions=None, locked_applications=None) -> discord.Embed:
    """Build a rich embed for an event announcement with available and selected positions.
    
    Args:
        event: Event object
        available_positions: Dict of {position_id: position_obj} for available positions
        locked_applications: List of locked/confirmed applications to show selected ATCs
    """
    # Main title with bigger format
    embed = discord.Embed(
        title=f"🔴 **RESERVA ATC - {event.name}**",
        description=event.short_description or event.description[:300],
        color=discord.Color.yellow(),
        url=event.link or None,
    )

    # Time info
    embed.add_field(
        name="📅 Data",
        value=f"{event.start_time:%d/%m/%Y}",
        inline=True,
    )
    embed.add_field(
        name="⏰ Horário",
        value=f"{event.start_time:%H:%M}z – {event.end_time:%H:%M}z",
        inline=True,
    )

    # Available Positions section (top) - positions with no confirmed slots
    if available_positions is None:
        # Fallback to fetching all positions
        available_positions = {}
        icaos = event.icaos.all()
        if icaos:
            icao_text = ""
            for icao_obj in icaos:
                positions = icao_obj.positions.all()
                pos_names = ", ".join(p.position_template.name for p in positions)
                icao_text += f"**{icao_obj.icao}**: {pos_names or 'Sem posições'}\n"
            embed.add_field(name="🏢 Posições Disponíveis", value=icao_text or "Nenhuma posição disponível", inline=False)
    else:
        # Use the filtered available positions
        if available_positions:
            icao_dict = {}
            for pos in available_positions.values():
                icao = pos.event_icao.icao
                if icao not in icao_dict:
                    icao_dict[icao] = []
                icao_dict[icao].append(pos.position_template.name)
            
            icao_text = ""
            for icao in sorted(icao_dict.keys()):
                pos_names = ", ".join(sorted(set(icao_dict[icao])))
                icao_text += f"**{icao}**: {pos_names}\n"
            embed.add_field(name="🏢 Posições Disponíveis", value=icao_text or "Nenhuma posição disponível", inline=False)
        else:
            embed.add_field(name="🏢 Posições Disponíveis", value="Nenhuma posição disponível no momento", inline=False)

    # Block info
    blocks = event.time_blocks.all()
    if blocks:
        block_text = "\n".join(
            f"Bloco {b.block_number}: {b.start_time:%H:%M}–{b.end_time:%H:%M}z"
            for b in blocks
        )
        embed.add_field(name="⏱️ Blocos de Horário", value=block_text, inline=False)

    # Selected ATCs section (bottom) - confirmed/locked applications
    if locked_applications:
        selected_text = ""
        for app in locked_applications:
            user_name = app.user.discord_username or f"CID {app.user.cid}"
            position_call = app.event_position.callsign
            time_frame = f"{app.time_block.start_time:%H:%M}–{app.time_block.end_time:%H:%M}z"
            selected_text += f"**{position_call}** ({app.event_position.event_icao.icao}): @{user_name}\n"
            selected_text += f"  ╰ {time_frame}\n"
        
        if selected_text:
            embed.add_field(name="✅ ATC Selecionados", value=selected_text.strip(), inline=False)

    if event.banner_url:
        embed.set_image(url=event.banner_url)

    embed.set_footer(text="Eventometer • Sistema de Booking ATC")
    return embed


def build_user_info_embed(user) -> discord.Embed:
    """Small embed showing user info after identification."""
    from core.models import ATCRating

    embed = discord.Embed(
        title="👤 Conta Identificada",
        color=discord.Color.green(),
    )
    embed.add_field(name="CID", value=str(user.cid), inline=True)
    embed.add_field(name="Rating", value=user.get_rating_display(), inline=True)
    embed.add_field(name="Participações", value=str(user.total_participations), inline=True)
    return embed


def build_summary_embed(user, event, position_callsigns: list[str], block_labels: list[str]) -> discord.Embed:
    """Build a summary embed after booking application."""
    embed = discord.Embed(
        title="📋 Resumo da Aplicação",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Evento", value=event.name, inline=False)
    embed.add_field(name="Posições", value="\n".join(position_callsigns), inline=True)
    embed.add_field(name="Blocos", value="\n".join(block_labels), inline=True)
    embed.add_field(name="CID", value=str(user.cid), inline=True)
    embed.set_footer(text="Use /revogar para cancelar suas aplicações")
    return embed
