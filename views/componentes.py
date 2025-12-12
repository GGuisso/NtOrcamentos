import streamlit as st
from datetime import date
from services import GoogleSheetsService

def init_session_state():
    if 'db_orcamentos' not in st.session_state:
        st.session_state['db_orcamentos'] = GoogleSheetsService.carregar_orcamentos()
    if 'edit_id' not in st.session_state: st.session_state['edit_id'] = None
    if 'navegacao_atual' not in st.session_state: st.session_state['navegacao_atual'] = "📝 Novo Orçamento"
    if 'feedback_msg' not in st.session_state: st.session_state['feedback_msg'] = None
    keys_end = ["in_cli_rua", "in_cli_bairro", "in_cli_cidade", "in_cli_num",
                "in_evt_rua", "in_evt_bairro", "in_evt_cidade", "in_evt_num",
                "in_evt_cep", "in_cli_cep"]
    for k in keys_end:
        if k not in st.session_state: st.session_state[k] = ""

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
    with st.sidebar:
        st.title("NT Festas")
        st.markdown("---")
        if st.button("🔄 Atualizar Estoque/Temas"):
            st.cache_data.clear()
            st.rerun()
        st.header("⚙️ Custos Operacionais")
        st.number_input("Custo KM", value=st.session_state.get('cfg_km', 2.00), step=0.10, key='cfg_km')
        st.number_input("Valor Hora Técnica", value=st.session_state.get('cfg_hora', 50.00), step=5.00, key='cfg_hora')
        st.number_input("Taxa Higienização", value=st.session_state.get('cfg_taxa', 20.00), key='cfg_taxa')