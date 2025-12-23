import streamlit as st
import datetime
from datetime import date
from services import SupabaseService  # Import obrigatório para carregar configs


def init_session_state():
    """Inicializa variáveis de estado globais se não existirem."""

    # --- DADOS DO SISTEMA ---
    if 'db_orcamentos' not in st.session_state:
        # Iniciamos vazio para ser rápido. O Dashboard ou Histórico carregam se precisarem.
        st.session_state['db_orcamentos'] = []

    # --- CONTROLE DE NAVEGAÇÃO ---
    if 'navegacao_atual' not in st.session_state:
        st.session_state['navegacao_atual'] = "📊 Dashboard"  # <--- MUDANÇA PRINCIPAL

    if 'edit_id' not in st.session_state:
        st.session_state['edit_id'] = None

    if 'tenant_id' not in st.session_state:
        st.session_state['tenant_id'] = None

    # --- FORMULÁRIO (INPUTS) ---
    # É importante declarar TODOS os campos aqui para evitar KeyError
    campos_padrao = {
        # Cliente
        'in_nome': '', 'in_cpf': '', 'in_telefone': '', 'in_email': '',
        'in_nascimento': None,
        # Endereços
        'in_cli_cep': '', 'in_cli_rua': '', 'in_cli_num': '', 'in_cli_bairro': '', 'in_cli_cidade': '',
        'chk_mesmo_end': False,
        'in_evt_cep': '', 'in_evt_rua': '', 'in_evt_num': '', 'in_evt_bairro': '', 'in_evt_cidade': '',
        # Evento
        'in_data': None,
        'in_categoria': None, 'in_tema': None, 'in_kit': None,
        # Itens
        'in_itens_pers': [], 'in_itens_add': [], 'in_check_obs': False, 'in_obs': '',
        # Logística e Custos
        'in_entrega': 'Pegue e Monte', 'in_dist': 0.0, 'in_horas': 0.0,
        'in_check_balao': False, 'in_tipo_balao': None, 'in_metros': 2.5,
        'in_desc_perc': 0.0,
        # Novos campos de Data/Hora (Logística)
        'in_hora_retirada': None, 'in_hora_devolucao': None,
        'in_data_retirada': None, 'in_data_devolucao': None,
        'in_hora_ret_i': None, 'in_hora_ret_f': None,
        'in_hora_dev_i': None, 'in_hora_dev_f': None
    }

    for k, v in campos_padrao.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # --- CONFIGURAÇÕES GLOBAIS (CUSTOS - VINDO DO BANCO) ---
    if 'cfg_km' not in st.session_state:
        # Valores padrão caso não consiga carregar
        def_km, def_hora, def_taxa = 2.00, 50.00, 20.00

        # Tenta pegar do banco se usuário estiver logado
        usuario = st.session_state.get('usuario_logado')
        tenant = usuario['tenant_id'] if usuario else None

        if tenant:
            try:
                configs = SupabaseService.carregar_configuracoes(tenant)
                def_km = float(configs.get('custo_km', 2.00))
                def_hora = float(configs.get('custo_hora', 50.00))
                def_taxa = float(configs.get('taxa_higienizacao', 20.00))
            except:
                pass

        st.session_state['cfg_km'] = def_km
        st.session_state['cfg_hora'] = def_hora
        st.session_state['cfg_taxa'] = def_taxa

    # --- FEEDBACK ---
    if 'feedback_msg' not in st.session_state:
        st.session_state['feedback_msg'] = None


def reset_form_state():
    """Limpa apenas os campos do formulário para iniciar um novo."""
    # Remove tudo que começa com 'in_'
    keys_to_delete = [k for k in st.session_state.keys() if k.startswith("in_")]

    # Remove também variáveis auxiliares de texto do PDF
    extras = ['txt_retirada_final', 'txt_devolucao_final']

    for k in keys_to_delete + extras:
        if k in st.session_state:
            del st.session_state[k]

    # Reinicia com os padrões chamando a função principal
    init_session_state()


def handle_feedback():
    """Exibe toasts ou mensagens flutuantes se houver."""
    if st.session_state.get('feedback_msg'):
        tipo, texto = st.session_state['feedback_msg']
        if tipo == 'success':
            st.toast(texto, icon="✅")
            if any(x in texto.lower() for x in ["criado", "salvo", "sucesso"]):
                st.balloons()
        elif tipo == 'error':
            st.toast(texto, icon="❌")
        elif tipo == 'warning':
            st.toast(texto, icon="⚠️")
        st.session_state['feedback_msg'] = None


def render_sidebar():
    """(Opcional) Se quiser mover a sidebar para cá no futuro."""
    pass