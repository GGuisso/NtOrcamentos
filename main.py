import streamlit as st

# Configuração da página DEVE ser a primeira linha executável
st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")

from views.componentes import init_session_state, handle_feedback, render_sidebar
from views.orcamento import render_form_orcamento
from views.historico import render_historico
from views.financeiro import render_financeiro
from views.gestao import render_gestao
from views.calendario import render_calendario
from views.login import render_login
from services import SupabaseService, AuthService


# ==========================================
# FUNÇÃO DO SISTEMA PRINCIPAL (App Protegido)
# ==========================================
def run_app():
    # Inicializa estado
    init_session_state()

    # Carrega dados do backend
    acervo, categorias, kits, detalhes, estoque_dict = SupabaseService.carregar_catalogo()

    # Processa feedbacks (toast/balões)
    handle_feedback()

    # Pega usuário logado
    usuario = st.session_state.get('usuario_logado')
    email_user = usuario.email if usuario else ""

    # ----------------------------------------------------
    # CONTROLE DE ACESSO (PERMISSÕES)
    # ----------------------------------------------------
    # Defina aqui quem são os administradores
    LISTA_ADMINS = ["ntfestasrs@gmail.com"]

    eh_admin = email_user in LISTA_ADMINS

    # Menu Base (Todos veem)
    opcoes_menu = ["📝 Novo Orçamento", "📂 Histórico de Orçamentos", "📅 Calendário"]

    # Menu Extra (Só Admin vê)
    if eh_admin:
        opcoes_menu.extend(["💰 Financeiro", "⚙️ Gestão de Acervo"])
    # ----------------------------------------------------

    # Renderiza Sidebar
        # Renderiza Sidebar
        with st.sidebar:
            st.title("NT Festas")
            st.caption(f"Logado como: {email_user}")
            if eh_admin:
                st.success("Acesso Admin 🔓")
            else:
                st.info("Acesso Vendedor 👤")

            st.markdown("---")

            # Menu de Navegação
            nav = st.radio("Menu", opcoes_menu)

            # --- AQUI: RECOLOCAMOS OS CUSTOS OPERACIONAIS (Só para Admin) ---
            if eh_admin:
                st.markdown("---")
                st.header("⚙️ Custos")
                st.number_input("Custo KM", value=st.session_state.get('cfg_km', 2.00), step=0.10, key='cfg_km')
                st.number_input("Vr. Hora Técnica", value=st.session_state.get('cfg_hora', 50.00), step=5.00,
                                key='cfg_hora')
                st.number_input("Taxa Higienização", value=st.session_state.get('cfg_taxa', 20.00), key='cfg_taxa')

                if st.button("🔄 Atualizar Dados"):
                    st.cache_data.clear()
                    st.rerun()
            # ---------------------------------------------------------------

            st.markdown("---")
            # Botão de Logout
            if st.button("Sair (Logout)"):
                AuthService.logout()
                st.session_state['usuario_logado'] = None
                st.rerun()

    # Roteamento de Views
    #st.header(nav)  # Título da página atual

    if nav == "📝 Novo Orçamento":
        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)
    elif nav == "📂 Histórico de Orçamentos":
        render_historico()
    elif nav == "📅 Calendário":
        render_calendario()
    elif nav == "💰 Financeiro":
        if eh_admin:  # Dupla verificação de segurança
            render_financeiro(acervo)
        else:
            st.error("Acesso negado.")
    elif nav == "⚙️ Gestão de Acervo":
        if eh_admin:  # Dupla verificação de segurança
            render_gestao()


# ==========================================
# FLUXO PRINCIPAL (GATEKEEPER)
# ==========================================
def main():
    # Verifica se existe usuário na sessão
    if 'usuario_logado' not in st.session_state:
        st.session_state['usuario_logado'] = None

    # Se não estiver logado, renderiza APENAS a tela de login e para.
    if not st.session_state['usuario_logado']:
        render_login()
    else:
        # Se estiver logado, roda o app normal
        run_app()


if __name__ == "__main__":
    main()