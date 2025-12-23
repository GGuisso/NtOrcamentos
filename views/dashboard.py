import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
from services import SupabaseService
import urllib.parse


# --- HELPER VISUAL (Igual ao Histórico) ---
def get_status_config(status):
    mapa = {
        "Aguardando Aprovação": {"icon": "🟡", "cor": "orange"},
        "Aguardando Pagamento": {"icon": "💸", "cor": "red"},  # Destaque
        "Reserva Confirmada": {"icon": "🔵", "cor": "blue"},
        "Itens Retirados": {"icon": "🚚", "cor": "violet"},
        "Finalizado": {"icon": "✅", "cor": "green"},
        "Cancelado": {"icon": "🔴", "cor": "grey"},
        "Reprovado": {"icon": "🚫", "cor": "grey"}
    }
    return mapa.get(status, {"icon": "⚪", "cor": "grey"})


def render_dashboard():
    st.header("📊 Visão Geral - NT Festas")

    # 1. Carrega Dados (com Cache)
    orcamentos = st.session_state.get('db_orcamentos', [])

    if not orcamentos:
        with st.spinner("Atualizando indicadores..."):
            orcamentos = SupabaseService.carregar_orcamentos()
            st.session_state['db_orcamentos'] = orcamentos

    if not orcamentos:
        st.info("Nenhum dado encontrado para gerar indicadores.")
        return

    # 2. Prepara o DataFrame
    df = pd.DataFrame(orcamentos)

    # Tratamento de datas
    df['data_evento'] = pd.to_datetime(df['data_evento']).dt.date
    if 'data_registro' not in df.columns:
        df['data_registro'] = date.today()
    else:
        df['data_registro'] = pd.to_datetime(df['data_registro']).dt.date

    hoje = date.today()

    # --- CÁLCULO DOS KPIs ---
    status_fechado = ['Reserva Confirmada', 'Itens Retirados', 'Finalizado', 'Aguardando Pagamento']
    df_fechado = df[df['status'].isin(status_fechado)]

    # Faturamento Mês
    fat_mes = df_fechado[
        (df_fechado['data_evento'].apply(lambda x: x.month) == hoje.month) &
        (df_fechado['data_evento'].apply(lambda x: x.year) == hoje.year)
        ]['total'].sum()

    # Pipeline
    df_pendente = df[df['status'] == 'Aguardando Aprovação']
    pipeline_valor = df_pendente['total'].sum()
    qtd_pendente = len(df_pendente)

    # Próximos 7 dias
    data_limite = hoje + timedelta(days=7)
    df_prox = df_fechado[(df_fechado['data_evento'] >= hoje) & (df_fechado['data_evento'] <= data_limite)]
    qtd_prox = len(df_prox)

    ticket_medio = df_fechado['total'].mean() if not df_fechado.empty else 0

    # --- CARDS ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Faturamento (Mês)", f"R$ {fat_mes:.2f}")
    c2.metric("A Receber (Potencial)", f"R$ {pipeline_valor:.2f}", f"{qtd_pendente} abertos", delta_color="off")
    c3.metric("Festas na Semana", qtd_prox)
    c4.metric("Ticket Médio", f"R$ {ticket_medio:.0f}")

    st.markdown("---")

    # --- SEÇÃO 2: AGENDA E ALERTAS ---
    col_agenda, col_alertas = st.columns([3, 2])

    with col_agenda:
        st.subheader("📅 Próximos Eventos (7 Dias)")

        if df_prox.empty:
            st.info("Nenhuma festa agendada para os próximos dias.")
        else:
            df_prox_sorted = df_prox.sort_values(by='data_evento')

            for _, row in df_prox_sorted.iterrows():
                # Pega a configuração visual correta
                conf = get_status_config(row['status'])

                with st.container(border=True):
                    dc1, dc2, dc3 = st.columns([1, 3, 2])

                    # Data
                    dia_semana = row['data_evento'].strftime('%a')
                    mapa_dias = {'Mon': 'Seg', 'Tue': 'Ter', 'Wed': 'Qua', 'Thu': 'Qui', 'Fri': 'Sex', 'Sat': 'Sáb',
                                 'Sun': 'Dom'}
                    dia_pt = mapa_dias.get(dia_semana, dia_semana)

                    dc1.markdown(f"### {row['data_evento'].day}/{row['data_evento'].month}")
                    dc1.caption(dia_pt)

                    # Cliente
                    dc2.markdown(f"**{row['cliente']}**")
                    dc2.caption(f"Tema: {row.get('tema', '-')}")

                    # Status e Logística (CORRIGIDO AQUI)
                    dados_form = row.get('dados_form', {})
                    logistica = dados_form.get('in_entrega', 'Pegue e Monte')
                    icon_log = "🚛" if logistica != "Pegue e Monte" else "📦"

                    # Usa a cor e ícone oficiais
                    dc3.markdown(f":{conf['cor']}[{conf['icon']} **{row['status']}**]")
                    dc3.caption(f"{icon_log} {logistica}")

    with col_alertas:
        st.subheader("⚠️ Atenção")

        df_abertos = df[df['status'] == 'Aguardando Aprovação'].copy()
        alertas_gerados = 0

        if not df_abertos.empty:
            for _, row in df_abertos.iterrows():
                data_criacao = row.get('data_registro', hoje)
                if pd.isna(data_criacao): data_criacao = hoje

                dias_atras = (hoje - data_criacao).days

                if dias_atras > 2:
                    alertas_gerados += 1
                    cor_alerta = "red" if dias_atras > 5 else "orange"

                    with st.expander(f"{row['cliente']} (R$ {row['total']:.0f})", expanded=False):
                        st.markdown(f":{cor_alerta}[Criado há {dias_atras} dias]")

                        primeiro_nome = row['cliente'].split()[0]
                        msg = f"Olá {primeiro_nome}, tudo bem? 🎈\nEstou passando para saber se você conseguiu ver o orçamento? Gostaria de confirmar para segurar sua data!"

                        tel = row.get('dados_form', {}).get('in_telefone', '')
                        nums = "".join([c for c in tel if c.isdigit()])

                        if nums:
                            link_zap = f"https://api.whatsapp.com/send?phone=55{nums}&text={urllib.parse.quote(msg)}"
                            st.link_button("📲 Cobrar no WhatsApp", link_zap, use_container_width=True)
                        else:
                            st.caption("Sem telefone.")

        if alertas_gerados == 0:
            st.success("Nenhuma pendência urgente.")