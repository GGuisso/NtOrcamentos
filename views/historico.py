import streamlit as st
import datetime
import time
from datetime import date
from functools import partial
from services import SupabaseService
from views.componentes import reset_form_state


@st.dialog("Gerenciar Status")
def dialog_gerenciar_status(orcamento):
    st.write(f"Gerenciar Pedido: **{orcamento['cliente']}**")
    st.caption(f"Status Atual: {orcamento['status']}")

    # Lista Oficial de Status (Fluxo Limpo)
    lista_status = [
        "Aguardando Aprovação",
        "Reserva Confirmada",
        "Itens Retirados",
        "Finalizado",
        "Cancelado",
        "Reprovado"
    ]

    try:
        idx_atual = lista_status.index(orcamento['status'])
    except ValueError:
        idx_atual = 0

    novo_status = st.selectbox("Novo Status", lista_status, index=idx_atual)

    total = orcamento.get('total', 0)
    sinal_estimado = total * 0.30
    restante_estimado = total * 0.70

    financeiro_payload = None

    # --- LÓGICA FINANCEIRA ---
    if novo_status == "Reserva Confirmada" and orcamento['status'] != "Reserva Confirmada":
        st.info("💰 Gerar lançamento de SINAL (30%)")
        val_sinal = st.number_input("Valor Recebido (R$)", value=sinal_estimado)
        data_pagto = st.date_input("Data Pagto", value=date.today())
        forma = st.selectbox("Forma", ["Pix", "Cartão", "Dinheiro"])

        if st.button("Confirmar Reserva & Lançar Sinal"):
            financeiro_payload = {
                "id": int(time.time()), "data": str(data_pagto), "tipo": "Receita",
                "categoria": "Sinal de Reserva", "descricao": f"Sinal - {orcamento['cliente']} (#{orcamento['id']})",
                "valor": val_sinal, "quem": "Sistema", "forma_pagto": forma, "status": "Recebido"
            }

    elif novo_status == "Itens Retirados" and orcamento['status'] != "Itens Retirados":
        st.info("🚚 O cliente está levando os itens? Hora de cobrar o restante!")
        val_rest = st.number_input("Valor Restante (R$)", value=restante_estimado)
        data_pagto = st.date_input("Data Pagto", value=date.today())
        forma = st.selectbox("Forma", ["Pix", "Cartão", "Dinheiro", "Já Pago Anteriormente"])

        if st.button("Confirmar Saída & Lançar Restante"):
            if forma == "Já Pago Anteriormente":
                financeiro_payload = "SKIP"
            else:
                financeiro_payload = {
                    "id": int(time.time()), "data": str(data_pagto), "tipo": "Receita",
                    "categoria": "Restante Pagamento",
                    "descricao": f"Quitação (Retirada) - {orcamento['cliente']} (#{orcamento['id']})",
                    "valor": val_rest, "quem": "Sistema", "forma_pagto": forma, "status": "Recebido"
                }

    elif novo_status == "Finalizado":
        st.success("✅ O pedido será arquivado como concluído.")
        st.write("Verifique se houve quebras ou avarias antes de finalizar.")
        if st.button("Finalizar Pedido"):
            financeiro_payload = "SKIP"

    elif novo_status == "Cancelado":
        st.warning("⚠️ Cancelamento")
        houve_reembolso = st.checkbox("Houve reembolso?")
        if houve_reembolso:
            val_dev = st.number_input("Valor Devolvido", min_value=0.0)
            if st.button("Confirmar Cancelamento com Estorno"):
                financeiro_payload = {
                    "id": int(time.time()), "data": str(date.today()), "tipo": "Despesa",
                    "categoria": "Reembolso", "descricao": f"Estorno - {orcamento['cliente']}",
                    "valor": val_dev, "quem": "Sistema", "forma_pagto": "Pix", "status": "Pago"
                }
        else:
            if st.button("Cancelar Sem Estorno"):
                financeiro_payload = "SKIP"

    else:
        if st.button("Atualizar Status"):
            financeiro_payload = "SKIP"

    # --- EXECUÇÃO ---
    if financeiro_payload:
        if financeiro_payload != "SKIP":
            with st.spinner("Lançando no Financeiro..."):
                SupabaseService.registrar_transacao(financeiro_payload)

        with st.spinner("Atualizando Status..."):
            orcamento['status'] = novo_status
            SupabaseService.upsert_orcamento(orcamento)

            st.session_state['db_orcamentos'] = [
                orcamento if o['id'] == orcamento['id'] else o
                for o in st.session_state['db_orcamentos']
            ]
            st.rerun()


# --- FUNÇÃO DE CARREGAMENTO CORRIGIDA ---
def carregar_orcamento_para_edicao(oid, dados):
    st.session_state['edit_id'] = oid

    for k, v in dados.items():
        # 1. Converte Data do Evento (se for string)
        if k == 'in_data':
            if isinstance(v, str):
                try:
                    v = datetime.datetime.strptime(v, '%Y-%m-%d').date()
                except:
                    pass

        # 2. Converte Data de Nascimento (AQUI ESTAVA O ERRO)
        # O banco manda string "1992-03-26", o date_input precisa de object date
        if k == 'in_nascimento' and v is not None:
            if isinstance(v, str):
                try:
                    v = datetime.datetime.strptime(v, '%Y-%m-%d').date()
                except:
                    v = None

        st.session_state[k] = v

    # Define a navegação para a tela de formulário
    # O st.rerun() foi removido daqui para evitar o aviso "no-op" dentro do callback.
    # O main.py detectará a mudança em 'navegacao_atual' e renderizará a tela correta.
    st.session_state['navegacao_atual'] = "📝 Novo Orçamento"


def render_historico():
    st.header("📂 Histórico de Pedidos")
    db = st.session_state.get('db_orcamentos', [])

    if not db:
        st.info("Nenhum orçamento encontrado.")
        return

    c_f1, c_f2 = st.columns(2)
    busca = c_f1.text_input("🔍 Buscar Cliente ou ID")

    opcoes_filtro = ["Aguardando Aprovação", "Reserva Confirmada", "Itens Retirados", "Finalizado", "Cancelado",
                     "Reprovado"]
    filtro_st = c_f2.multiselect("Filtrar por Status", opcoes_filtro)

    lista = sorted(db, key=lambda x: str(x['id']), reverse=True)
    if busca:
        lista = [x for x in lista if busca.lower() in x['cliente'].lower() or str(x['id']) in busca]
    if filtro_st:
        lista = [x for x in lista if x.get('status') in filtro_st]

    for orc in lista:
        with st.container():
            status = orc.get('status', 'Aguardando Aprovação')

            mapa_cores = {
                "Aguardando Aprovação": "🟡",
                "Reserva Confirmada": "🔵",
                "Itens Retirados": "🟣",
                "Finalizado": "🟢",
                "Cancelado": "🔴",
                "Reprovado": "⚫"
            }
            cor = mapa_cores.get(status, "⚪")

            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

            c1.markdown(f"**#{orc['id']} - {orc['cliente']}**")
            c1.caption(f"📅 {orc['data_evento']} | 🎨 {orc.get('tema', '-')}")

            c2.write(f"R$ {orc.get('total', 0):.2f}")
            c3.markdown(f"{cor} **{status}**")

            bts = c4.columns([1, 1, 1])

            pode_editar = (status == "Aguardando Aprovação")

            bts[0].button(
                "✏️" if pode_editar else "👁️",
                key=f"e_{orc['id']}",
                on_click=carregar_orcamento_para_edicao,
                args=(orc['id'], orc['dados_form']),
                help="Ver detalhes ou Editar"
            )

            if bts[1].button("🔄", key=f"st_{orc['id']}", help="Mudar Status"):
                dialog_gerenciar_status(orc)

            st.markdown("---")