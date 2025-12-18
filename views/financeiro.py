import streamlit as st
import pandas as pd
import plotly.express as px
import time
from datetime import date, timedelta, datetime
from services import SupabaseService


def render_financeiro(acervo_dict):
    st.header("💰 Controle Financeiro Inteligente")

    st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """, unsafe_allow_html=True)

    tab_lanc, tab_dash = st.tabs(["📝 Novo Lançamento", "📊 Dashboard Gerencial"])

    with tab_lanc:
        st.subheader("Registrar Movimentação")

        with st.container(border=True):
            tipo_mov = st.radio("Tipo:", ["Receita (Entrada)", "Despesa (Saída)"], horizontal=True,
                                label_visibility="collapsed")

            c1, c2 = st.columns(2)
            f_data = c1.date_input("Data", value=date.today())

            if tipo_mov == "Receita (Entrada)":
                f_cat = c2.selectbox("Categoria", ["Sinal de Reserva", "Restante Pagamento", "Receita Extra", "Outros"])

                orcamentos_ativos = [o for o in st.session_state.get('db_orcamentos', []) if
                                     o.get('status') not in ['Cancelado', 'Reprovado', 'Finalizado']]
                opcoes_orc = ["Sem Vínculo"] + [f"#{o['id']} - {o['cliente']} ({o['data_evento']})" for o in
                                                orcamentos_ativos]
                orc_selecionado = st.selectbox("Vincular à Festa:", opcoes_orc)

                f_tipo = "Receita"
                desc_placeholder = f"Entrada ref. {orc_selecionado}" if orc_selecionado != "Sem Vínculo" else "Ex: Adiantamento"
            else:
                f_cat = c2.selectbox("Categoria", ["Compra de Acervo (Investimento)", "Consumo (Descartáveis/Balões)",
                                                   "Fixo (Aluguel/Luz/Internet)", "Serviço (Frete/Mão de Obra)",
                                                   "Outros"])
                f_tipo = "Despesa"
                desc_placeholder = "Ex: Conta de Luz, Compra na Shopee..."
                orc_selecionado = "Sem Vínculo"

            desc_input = st.text_input("Descrição", value="", placeholder=desc_placeholder)

            c3, c4, c5 = st.columns(3)
            val = c3.number_input("Valor (R$)", min_value=0.0, step=10.0)
            quem = c4.text_input("Responsável/Pagante", value="NT Festas")
            forma = c5.selectbox("Forma Pagto", ["Pix", "Cartão Crédito", "Dinheiro", "Boleto", "Débito"])

            update_stock = False
            is_new_item = False
            item_nome = None
            qtd_compra = 0
            custo_locacao = 0.0
            loja_compra = ""
            link_compra = ""

            if f_tipo == "Despesa" and "Acervo" in f_cat:
                st.info("📦 **Entrada de Estoque Detectada**")
                modo_item = st.radio("Item:", ["Aumentar estoque existente", "Cadastrar item novo"], horizontal=True)

                if modo_item == "Aumentar estoque existente":
                    c_i1, c_i2 = st.columns([2, 1])
                    item_nome = c_i1.selectbox("Item", list(acervo_dict.keys()))
                    qtd_compra = c_i2.number_input("Qtd", min_value=1, value=1)
                else:
                    is_new_item = True
                    c_n1, c_n2 = st.columns([2, 1])
                    item_nome = c_n1.text_input("Nome do Novo Item")
                    qtd_compra = c_n2.number_input("Qtd", min_value=1, value=1)
                    custo_locacao = st.number_input("Preço Aluguel Sugerido (R$)", min_value=0.0, value=30.0)

                c_l1, c_l2 = st.columns(2)
                loja_compra = c_l1.text_input("Fornecedor")
                link_compra = c_l2.text_input("Link (Opcional)")
                update_stock = True

            if st.button("💾 Confirmar Lançamento", type="primary", use_container_width=True):
                if val <= 0:
                    st.error("Valor inválido.")
                elif update_stock and is_new_item and not item_nome:
                    st.error("Nome do item obrigatório.")
                else:
                    novo_id = int(time.time())
                    descricao_final = desc_input if desc_input else (
                        f"{f_cat} - {orc_selecionado}" if orc_selecionado != "Sem Vínculo" else f_cat)

                    transacao = {
                        "id": novo_id, "data": str(f_data), "tipo": f_tipo, "categoria": f_cat,
                        "descricao": descricao_final, "valor": val, "quem": quem, "forma_pagto": forma,
                        "status": "Pago" if f_tipo == "Despesa" else "Recebido",
                        "loja": loja_compra, "link": link_compra
                    }

                    dados_estoque = None
                    if update_stock:
                        dados_estoque = {
                            "item": item_nome, "qtd": qtd_compra,
                            "custo": val / qtd_compra if qtd_compra > 0 else val,
                            "loja": loja_compra, "link": link_compra,
                            "is_new": is_new_item,
                            "preco_locacao": custo_locacao
                        }

                    with st.spinner("Registrando..."):
                        SupabaseService.registrar_transacao(transacao, dados_estoque)
                        st.cache_data.clear()
                        st.success("Lançamento realizado!")
                        time.sleep(1)
                        st.rerun()

    with tab_dash:
        c_filter1, c_filter2 = st.columns([3, 1])
        with c_filter1:
            periodo = st.date_input(
                "📅 Período de Análise",
                value=(date.today().replace(day=1), date.today()),
                format="DD/MM/YYYY"
            )

        df_fin = SupabaseService.get_dataframe("Financeiro")

        if df_fin.empty:
            st.info("Nenhum dado financeiro encontrado.")
            return

        df_fin['Valor'] = pd.to_numeric(df_fin['Valor'], errors='coerce').fillna(0.0)
        df_fin['Data'] = pd.to_datetime(df_fin['Data']).dt.date

        if isinstance(periodo, tuple) and len(periodo) == 2:
            start_date, end_date = periodo
            df_filtered = df_fin[(df_fin['Data'] >= start_date) & (df_fin['Data'] <= end_date)]
        else:
            df_filtered = df_fin

        receitas = df_filtered[df_filtered['Tipo'] == 'Receita']['Valor'].sum()
        despesas = df_filtered[df_filtered['Tipo'] == 'Despesa']['Valor'].sum()
        lucro = receitas - despesas
        margem = (lucro / receitas * 100) if receitas > 0 else 0

        orcamentos = st.session_state.get('db_orcamentos', [])
        a_receber = 0.0

        for orc in orcamentos:
            try:
                data_evento = datetime.strptime(str(orc['data_evento']), '%Y-%m-%d').date()
                if data_evento >= date.today() and orc.get('status') == 'Reserva Confirmada':
                    total = float(orc.get('total', 0))
                    a_receber += (total * 0.70)
            except:
                pass

        st.markdown("### 📊 Visão Geral")
        col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

        col_kpi1.metric("Receita (Realizada)", f"R$ {receitas:,.2f}", delta="Entradas")
        col_kpi2.metric("Despesas", f"R$ {despesas:,.2f}", delta="-Saídas", delta_color="inverse")
        col_kpi3.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta=f"{margem:.1f}% Margem")
        col_kpi4.metric("A Receber (Previsto)", f"R$ {a_receber:,.2f}",
                        help="Soma dos 70% restantes de reservas confirmadas futuras.")

        st.markdown("---")

        if not df_filtered.empty:
            df_chart = df_filtered.copy()
            df_chart['Mês'] = pd.to_datetime(df_chart['Data']).dt.strftime('%m/%Y')

            df_grouped = df_chart.groupby(['Mês', 'Tipo'])['Valor'].sum().reset_index()

            fig_flow = px.bar(
                df_grouped,
                x="Mês",
                y="Valor",
                color="Tipo",
                barmode="group",
                title="Evolução do Fluxo de Caixa",
                color_discrete_map={"Receita": "#2ECC71", "Despesa": "#E74C3C"},
                height=350
            )
            # AJUSTE DE WARNING: use_container_width -> True (Plotly aceita, mas se quiser garantir pode usar width do container)
            st.plotly_chart(fig_flow, use_container_width=True)

            c_g1, c_g2 = st.columns(2)

            with c_g1:
                df_desp = df_filtered[df_filtered['Tipo'] == 'Despesa']
                if not df_desp.empty:
                    fig_pie = px.pie(
                        df_desp,
                        values='Valor',
                        names='Categoria',
                        title='Onde estou gastando?',
                        hole=0.4,
                        color_discrete_sequence=px.colors.qualitative.Pastel
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("Sem despesas no período.")

            with c_g2:
                fig_pay = px.pie(
                    df_filtered,
                    values='Valor',
                    names='Forma Pagto',
                    title='Métodos de Pagamento (Entradas e Saídas)',
                    hole=0.4
                )
                st.plotly_chart(fig_pay, use_container_width=True)

        with st.expander("🔎 Ver Extrato Detalhado"):
            df_display = df_filtered.copy()
            df_display = df_display[['Data', 'Descrição', 'Categoria', 'Valor', 'Tipo', 'Forma Pagto', 'Quem']]
            df_display = df_display.sort_values(by='Data', ascending=False)

            # AJUSTE DE WARNING: use_container_width -> width="stretch"
            st.dataframe(
                df_display,
                width="stretch",
                column_config={
                    "Valor": st.column_config.NumberColumn("Valor", format="R$ %.2f"),
                    "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")
                },
                hide_index=True
            )