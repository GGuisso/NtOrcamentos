# ARQUIVO: views/calendario.py
import streamlit as st
import datetime
from datetime import date

# Tenta importar a biblioteca
try:
    from streamlit_calendar import calendar
except ImportError:
    st.error("Biblioteca 'streamlit-calendar' não encontrada.")
    st.info("Por favor, instale rodando no terminal: pip install streamlit-calendar")
    st.stop()


def render_calendario():
    st.header("📅 Agenda de Eventos")

    db = st.session_state.get('db_orcamentos', [])

    if not db:
        st.info("Nenhuma reserva encontrada.")
        return

    # 1. Transformar os Orçamentos em "Eventos"
    events = []

    # Mapa de Cores Equalizado com o Histórico
    color_map = {
        "Aguardando Aprovação": "#F1C40F",  # Amarelo
        "Aguardando Pagamento": "#E67E22",  # Laranja (Novo)
        "Reserva Confirmada": "#3498DB",    # Azul
        "Itens Retirados": "#9B59B6",       # Roxo
        "Finalizado": "#2ECC71",            # Verde
        "Cancelado": "#E74C3C",             # Vermelho
        "Reprovado": "#95A5A6"              # Cinza
    }

    for orc in db:
        status = orc.get('status', 'Aguardando Aprovação')

        # Se quiser esconder cancelados do calendário, mantenha essa linha:
        if status == 'Cancelado': continue

        try:
            data_str = orc.get('data_evento')
            if not data_str: continue

            titulo = f"{orc['cliente']} - {orc.get('tema', '?')}"

            # Define a cor baseada no status, ou cinza se não achar
            cor_evento = color_map.get(status, "#808080")

            events.append({
                "title": titulo,
                "start": data_str,
                "backgroundColor": cor_evento,
                "borderColor": cor_evento,
                "extendedProps": {
                    "id": orc['id'],
                    "valor": orc.get('total', 0),
                    "status": status
                }
            })
        except Exception as e:
            continue

    # 2. Configurações do Calendário
    calendar_options = {
        "headerToolbar": {
            "left": "today prev,next",
            "center": "title",
            "right": "dayGridMonth,listWeek"
        },
        "initialView": "dayGridMonth",
        "locale": "pt-br",
        "navLinks": True,
        "selectable": True,
        "editable": False,
        "height": 600,
        "contentHeight": "auto",
        "aspectRatio": 2,
    }

    # 3. Renderiza o Calendário
    state = calendar(
        events=events,
        options=calendar_options,
        custom_css="""
        .fc-event-title {
            font-weight: bold;
            font-size: 0.85em;
            white-space: normal;
        }
        .fc-toolbar-title {
            font-size: 1.2em !important;
        }
        """,
        key="my_calendar"
    )

    # 4. Detalhes ao Clicar
    if state.get("eventClick"):
        event_data = state["eventClick"]["event"]
        props = event_data["extendedProps"]

        st.divider()
        st.markdown(f"### 🔎 Detalhes da Seleção")

        c1, c2, c3 = st.columns(3)
        c1.metric("Cliente", event_data["title"].split(' - ')[0])
        c2.metric("Status", props["status"])
        c3.metric("Valor Total", f"R$ {props['valor']:.2f}")

        # Botão para ir direto editar (opcional, apenas informativo)
        st.info(f"Para gerenciar este pedido, vá em **Histórico** e busque pelo ID **#{props['id']}**.")

    st.markdown("---")
    # Legenda atualizada com as novas cores
    st.caption("Legenda: 🟡 Aprovação | 🟠 Pagamento | 🔵 Confirmado | 🟣 Retirado | 🟢 Finalizado")