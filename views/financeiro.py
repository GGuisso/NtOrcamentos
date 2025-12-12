import streamlit as st
import pandas as pd
import time
from datetime import date
from services import GoogleSheetsService

def render_financeiro(acervo_dict):
    st.header("💰 Controle Financeiro")
    tab_lanc, tab_dash = st.tabs(["📝 Novo Lançamento", "📊 Extrato & Dashboard"])

    with tab_lanc:
        st.subheader("Registrar Movimentação")
        tipo_mov = st.radio("O que você deseja lançar?", ["Receita (Entrada)", "Despesa (Saída)"], horizontal=True)

        c1, c2 = st.columns(2)
        f_data = c1.date_input("Data do Pagamento/Gasto", value=date.today())

        if tipo_mov == "Receita (Entrada)":
            f_cat = c2.selectbox("Categoria", ["Sinal de Reserva", "Restante Pagamento", "Receita Extra", "Outros"])
            st.markdown("##### 🔗 Vínculo com Orçamento")
            orcamentos_ativos = [o for o in st.session_state['db_orcamentos'] if
                                 o['status'] in ['Aprovado', 'Aguardando', 'Reserva Confirmada']]
            opcoes_orc = ["Sem Vínculo"] + [f"#{o['id']} - {o['cliente']} ({o['data_evento']})" for o in
                                            orcamentos_ativos]
            orc_selecionado = st.selectbox("Este valor refere-se a qual festa?", opcoes_orc)
            f_tipo = "Receita"
            desc_placeholder = "Ex: Sinal do cliente X"
            if orc_selecionado != "Sem Vínculo":
                desc_placeholder = f"Entrada ref. {orc_selecionado}"
        else:
            f_cat = c2.selectbox("Categoria", ["Compra de Acervo", "Consumo (Balões, Descartáveis)",
                                               "Fixo (Luz, Aluguel, Internet)",
                                               "Serviço (Frete, Mão de obra, Higienização)"])
            f_tipo = "Despesa"
            desc_placeholder = "Ex: Conta de Luz, Compra Shopee"

        desc_input = st.text_input("Descrição",
                                   value=desc_placeholder if 'orc_selecionado' in locals() and orc_selecionado != "Sem Vínculo" else "",
                                   placeholder="Descreva o lançamento")

        c3, c4, c5 = st.columns(3)
        val = c3.number_input("Valor (R$)", min_value=0.0, step=10.0)
        quem = c4.text_input("Quem Realizou?", value="NT Festas")
        forma = c5.selectbox("Forma Pagto", ["Pix", "Cartão Crédito", "Dinheiro", "Boleto", "Débito"])

        update_stock = False
        is_new_item = False
        item_nome = None
        qtd_compra = 0
        custo_locacao = 0.0
        loja_compra = ""
        link_compra = ""

        if f_tipo == "Despesa" and f_cat == "Compra de Acervo":
            st.markdown("---")
            st.info("📦 **Atualização de Estoque:** Preencha abaixo para cadastrar o item comprado.")
            modo_item = st.radio("Este item já existe no sistema?",
                                 ["Sim, aumentar estoque", "Não, é um item novo"], horizontal=True)

            if modo_item == "Sim, aumentar estoque":
                c_i1, c_i2 = st.columns([2, 1])
                item_nome = c_i1.selectbox("Selecione o Item", list(acervo_dict.keys()))
                qtd_compra = c_i2.number_input("Qtd Comprada", min_value=1, value=1)
            else:
                is_new_item = True
                c_n1, c_n2 = st.columns([2, 1])
                item_nome = c_n1.text_input("Nome do Novo Item")
                qtd_compra = c_n2.number_input("Qtd Comprada", min_value=1, value=1)
                custo_locacao = st.number_input("Preço de Aluguel Sugerido (R$)", min_value=0.0, value=30.0)

            c_l1, c_l2 = st.columns(2)
            loja_compra = c_l1.text_input("Loja/Fornecedor")
            link_compra = c_l2.text_input("Link do Produto (Opcional)")
            update_stock = True

        submitted = st.button("💾 Confirmar Lançamento", type="primary")

        if submitted:
            if val <= 0:
                st.error("O valor deve ser maior que zero.")
            elif update_stock and is_new_item and not item_nome:
                st.error("Preencha o nome do novo item.")
            else:
                novo_id = int(time.time())
                descricao_final = desc_input
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
                with st.spinner("Salvando..."):
                    GoogleSheetsService.registrar_transacao(transacao, dados_estoque)
                    st.cache_data.clear()
                    st.success("Lançamento salvo!")
                    time.sleep(1)
                    st.rerun()

    with tab_dash:
        st.subheader("Extrato")
        df_fin = GoogleSheetsService.get_dataframe("Financeiro")
        if not df_fin.empty:
            df_fin['Valor'] = pd.to_numeric(df_fin['Valor'], errors='coerce').fillna(0.0)
            receitas = df_fin[df_fin['Tipo'] == 'Receita']['Valor'].sum()
            despesas = df_fin[df_fin['Tipo'] == 'Despesa']['Valor'].sum()
            lucro = receitas - despesas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Receitas", f"R$ {receitas:.2f}")
            m2.metric("Total Despesas", f"R$ {despesas:.2f}")
            m3.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta_color="normal")
            st.dataframe(df_fin, width='stretch')
        else:
            st.info("Nenhum lançamento encontrado.")