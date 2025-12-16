import streamlit as st
from datetime import date
from services import SupabaseService


def init_session_state():
    if 'db_orcamentos' not in st.session_state:
        st.session_state['db_orcamentos'] = SupabaseService.carregar_orcamentos()
    if 'edit_id' not in st.session_state: st.session_state['edit_id'] = None
    if 'navegacao_atual' not in st.session_state: st.session_state['navegacao_atual'] = "📝 Novo Orçamento"
    if 'feedback_msg' not in st.session_state: st.session_state['feedback_msg'] = None

    # --- NOVO: Inicializa tenant_id na sessão ---
    if 'tenant_id' not in st.session_state: st.session_state['tenant_id'] = None

    keys_end = ["in_cli_rua", "in_cli_bairro", "in_cli_cidade", "in_cli_num",
                "in_evt_rua", "in_evt_bairro", "in_evt_cidade", "in_evt_num",
                "in_evt_cep", "in_cli_cep", "in_email", "in_nascimento"]

    for k in keys_end:
        if k not in st.session_state: st.session_state[k] = ""

    # Garante que nascimento comece como None
    if st.session_state['in_nascimento'] == "":
        st.session_state['in_nascimento'] = None

    # Custos Padrão
    if 'cfg_km' not in st.session_state: st.session_state['cfg_km'] = 2.00
    if 'cfg_hora' not in st.session_state: st.session_state['cfg_hora'] = 50.00
    if 'cfg_taxa' not in st.session_state: st.session_state['cfg_taxa'] = 20.00


def reset_form_state():
    keys_to_delete = [k for k in st.session_state.keys() if k.startswith("in_")]
    for k in keys_to_delete:
        del st.session_state[k]
    st.session_state['in_data'] = date.today()
    init_session_state()


def handle_feedback():
    if st.session_state.get('feedback_msg'):
        tipo, msg = st.session_state['feedback_msg']
        if tipo == "success":
            st.toast(msg, icon="✅")
            if any(x in msg for x in ["criado", "atualizado", "copiados"]): st.balloons()
        else:
            st.error(msg)
        st.session_state['feedback_msg'] = None


def render_sidebar():
    # A barra lateral agora é renderizada no main.py,
    # mas mantemos a função vazia ou para componentes globais se precisar
    pass