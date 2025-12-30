import streamlit as st
import datetime
import time
import math
import urllib.parse
from datetime import date
from services import SupabaseService
from views.componentes import reset_form_state


# --- MAPA DE STATUS GLOBAL ---
def get_status_config(status):
    mapa = {
        "Aguardando Aprovação": {"icon": "🟡", "cor": "orange"},
        "Aguardando Pagamento": {"icon": "💸", "cor": "red"},  # Destaque vermelho/financeiro
        "Reserva Confirmada": {"icon": "🔵", "cor": "blue"},
        "Itens Retirados": {"icon": "🚚", "cor": "violet"},
        "Finalizado": {"icon": "✅", "cor": "green"},
        "Cancelado": {"icon": "🔴", "cor": "grey"},
        "Reprovado": {"icon": "🚫", "cor": "grey"}
    }
    return mapa.get(status, {"icon": "⚪", "cor": "grey"})


# --- DIALOG PARA EXIBIR O LINK ---
@st.dialog("🔗 Link de Aprovação do Cliente")
def dialog_compartilhar_link(orcamento):
    uuid_str = orcamento.get('link_uuid')

    if not uuid_str:
        st.warning("Este orçamento antigo não possui link gerado. Por favor, edite e salve-o novamente para gerar.")
        return

    base_url = st.secrets.get("BASE_URL", "")
    if not base_url and "general" in st.secrets:
        base_url = st.secrets["general"].get("BASE_URL", "http://localhost:8501")
    if not base_url: base_url = "http://localhost:8501"

    link_final = f"{base_url}/?proposta_id={uuid_str}"

    st.write(f"Envie este link para **{orcamento['cliente']}**:")
    st.code(link_final, language="text")

    primeiro_nome = orcamento['cliente'].split()[0]
    msg_zap = f"Olá {primeiro_nome}! 🎈\nSegue o link do seu orçamento para aprovação e pagamento do sinal:\n\n{link_final}"

    dados_form = orcamento.get('dados_form', {})
    telefone = dados_form.get('in_telefone', '')
    nums = "".join([c for c in telefone if c.isdigit()])

    if nums:
        link_zap_btn = f"https://api.whatsapp.com/send?phone=55{nums}&text={urllib.parse.quote(msg_zap)}"
        st.link_button("🚀 Enviar no WhatsApp", link_zap_btn, type="primary", use_container_width=True)
    else:
        st.info("Cadastre o telefone do cliente para habilitar o botão de envio direto.")

    st.markdown("---")
    st.caption("Ao acessar este link, o cliente verá as fotos, totais e poderá pagar o sinal via Pix.")


@st.dialog("Gerenciar Status")
def dialog_gerenciar_status(orcamento):
    st.write(f"Gerenciar Pedido: **{orcamento['cliente']}**")
    st.caption(f"Status Atual: {orcamento['status']}")

    lista_status = [
        "Aguardando Aprovação",
        "Aguardando Pagamento",
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
            st.session_state['db_orcamentos'] = SupabaseService.carregar_orcamentos()
            st.rerun()


def carregar_orcamento_para_edicao(oid, dados):
    st.session_state['edit_id'] = oid
    # Limpa e carrega dados
    reset_form_state()
    for k, v in dados.items():
        if k == 'in_data':
            if isinstance(v, str):
                try:
                    v = datetime.datetime.strptime(v[:10], '%Y-%m-%d').date()
                except:
                    pass
        if k == 'in_nascimento' and v is not None:
            if isinstance(v, str):
                try:
                    v = datetime.datetime.strptime(v[:10], '%Y-%m-%d').date()
                except:
                    v = None

        # Recupera horários
        if k in ['in_hora_ret_i', 'in_hora_ret_f', 'in_hora_dev_i', 'in_hora_dev_f']:
            if isinstance(v, str):
                try:
                    v = datetime.datetime.strptime(v, '%H:%M:%S').time()
                except:
                    pass

        st.session_state[k] = v
    st.session_state['navegacao_atual'] = "📝 Novo Orçamento"


def render_historico():
    st.header("📂 Histórico de Pedidos")

    # --- ESTADO DA PAGINAÇÃO E FILTROS ---
    if 'hist_page' not in st.session_state:
        st.session_state['hist_page'] = 1

    # Resetar página se trocar de filtro
    def _reset_page():
        st.session_state['hist_page'] = 1

    # --- FILTROS NO TOPO ---
    c_f1, c_f2 = st.columns([2, 2])
    busca = c_f1.text_input("🔍 Buscar Cliente ou ID", on_change=_reset_page)

    opcoes_filtro = ["Aguardando Aprovação", "Aguardando Pagamento", "Reserva Confirmada", "Itens Retirados",
                     "Finalizado", "Cancelado", "Reprovado"]
    filtro_st = c_f2.multiselect("Filtrar por Status", opcoes_filtro, on_change=_reset_page)

    # --- CARREGAMENTO DE DADOS (Paginado) ---
    ITENS_POR_PAGINA = 10
    pagina_atual = st.session_state['hist_page']

    with st.spinner("Carregando lista..."):
        # Chama o novo serviço paginado
        lista_orcamentos, total_items = SupabaseService.listar_orcamentos_paginado(
            page=pagina_atual,
            page_size=ITENS_POR_PAGINA,
            busca=busca,
            status_filtro=filtro_st
        )

    # --- RENDERIZAÇÃO DA LISTA ---
    if not lista_orcamentos:
        st.info("Nenhum orçamento encontrado com estes filtros.")
    else:
        st.caption(f"Exibindo {len(lista_orcamentos)} de {total_items} registros encontrados.")

        for orc in lista_orcamentos:
            with st.container(border=True):
                status = orc.get('status', 'Aguardando Aprovação')
                config = get_status_config(status)

                c1, c2, c3, c4 = st.columns([3, 2, 2, 2])

                c1.markdown(f"**#{orc['id']} - {orc['cliente']}**")
                c1.caption(f"📅 {orc['data_evento']} | 🎨 {orc.get('tema', '-')}")

                c2.write(f"R$ {orc.get('total', 0):.2f}")
                c3.markdown(f":{config['cor']}[{config['icon']} **{status}**]")

                bts = c4.columns([1, 1, 1])

                # Lógica de botões (Mantida)
                pode_editar = (status in ["Aguardando Aprovação", "Aguardando Pagamento", "Rascunho"])

                if bts[0].button("✏️" if pode_editar else "👁️", key=f"e_{orc['id']}", help="Ver/Editar"):
                    carregar_orcamento_para_edicao(orc['id'], orc['dados_form'])
                    st.rerun()

                if bts[1].button("🔗", key=f"lk_{orc['id']}", help="Link Cliente"):
                    dialog_compartilhar_link(orc)

                if bts[2].button("🔄", key=f"st_{orc['id']}", help="Mudar Status"):
                    dialog_gerenciar_status(orc)

        # --- CONTROLES DE PAGINAÇÃO (RODAPÉ) ---
        total_paginas = math.ceil(total_items / ITENS_POR_PAGINA)

        if total_paginas > 1:
            st.markdown("---")
            c_p1, c_p2, c_p3 = st.columns([1, 2, 1])

            with c_p1:
                if pagina_atual > 1:
                    if st.button("⬅️ Anterior", use_container_width=True):
                        st.session_state['hist_page'] -= 1
                        st.rerun()

            with c_p2:
                st.markdown(
                    f"<div style='text-align: center'>Página <b>{pagina_atual}</b> de <b>{total_paginas}</b></div>",
                    unsafe_allow_html=True)

            with c_p3:
                if pagina_atual < total_paginas:
                    if st.button("Próxima ➡️", use_container_width=True):
                        st.session_state['hist_page'] += 1
                        st.rerun()