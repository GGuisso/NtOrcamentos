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
from views.usuarios import render_usuarios
from views.logistica import render_logistica
from views.publico import render_view_publica  # <--- NOVO IMPORT
from services import SupabaseService, AuthService


# ==========================================
# FUNÇÃO DO SISTEMA PRINCIPAL (App Protegido)
# ==========================================
def run_app():
    # Inicializa estado
    init_session_state()

    # Pega usuário logado (Dicionário retornado pelo AuthService)
    usuario = st.session_state.get('usuario_logado')

    # Extrai o ID do tenant para passar ao cache e a role
    tenant_id = usuario['tenant_id'] if usuario else None
    email_user = usuario['email'] if usuario else ""
    role_user = usuario['role'] if usuario else "vendedor"

    # Carrega dados do backend passando o tenant_id
    acervo, categorias, kits, detalhes, estoque_dict = SupabaseService.carregar_catalogo(tenant_id)

    # Processa feedbacks (toast/balões)
    handle_feedback()

    # ----------------------------------------------------
    # CONTROLE DE ACESSO (PERMISSÕES VIA BANCO)
    # ----------------------------------------------------
    eh_admin = (role_user == 'admin')

    # Menu Base (Todos veem)
    opcoes_menu = ["📝 Novo Orçamento", "📂 Histórico de Orçamentos", "📅 Calendário"]

    # Menu Extra (Só Admin vê)
    if eh_admin:
        # Adicionado "📦 Logística"
        opcoes_menu.extend(["📦 Logística", "💰 Financeiro", "⚙️ Gestão de Acervo", "👥 Equipe"])
    # ----------------------------------------------------

    # Renderiza Sidebar
    with st.sidebar:
        st.title("NT Festas")
        st.caption(f"Logado como: {email_user}")

        if eh_admin:
            st.success(f"Perfil: {role_user.upper()} 🔓")
        else:
            st.info(f"Perfil: {role_user.upper()} 👤")

        st.markdown("---")

        # --- SINCRONIZAÇÃO DO MENU ---
        nav_atual = st.session_state.get('navegacao_atual', "📝 Novo Orçamento")
        try:
            idx_nav = opcoes_menu.index(nav_atual)
        except ValueError:
            idx_nav = 0

        nav = st.radio("Menu", opcoes_menu, index=idx_nav)

        if nav != st.session_state.get('navegacao_atual'):
            st.session_state['navegacao_atual'] = nav
            st.rerun()
        # ----------------------------------------------

        # --- CUSTOS OPERACIONAIS (Só para Admin) ---
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
        if st.button("Sair (Logout)"):
            AuthService.logout()
            st.session_state['usuario_logado'] = None
            st.rerun()

    # Roteamento de Views
    if nav == "📝 Novo Orçamento":
        # CORREÇÃO: Se clicar no menu, limpa o modo edição para começar do zero
        if st.session_state.get('navegacao_atual') != "📝 Novo Orçamento":
            st.session_state['edit_id'] = None
            # Opcional: Limpar formulário também se quiser garantir tela limpa
            # reset_form_state()

        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)

    elif nav == "📂 Histórico de Orçamentos":
        # Garante que ao sair do form, o modo edição morra
        st.session_state['edit_id'] = None
        render_historico()

    elif nav == "📅 Calendário":
        st.session_state['edit_id'] = None
        render_calendario()

    elif nav == "📦 Logística":
        st.session_state['edit_id'] = None
        if eh_admin:
            render_logistica()
        else:
            st.error("Acesso restrito.")

    elif nav == "💰 Financeiro":
        st.session_state['edit_id'] = None
        if eh_admin:
            render_financeiro(acervo)
        else:
            st.error("Acesso negado.")

    elif nav == "⚙️ Gestão de Acervo":
        st.session_state['edit_id'] = None
        if eh_admin:
            render_gestao()

    elif nav == "👥 Equipe":
        st.session_state['edit_id'] = None
        if eh_admin:
            render_usuarios()


# ==========================================
# FLUXO PRINCIPAL (GATEKEEPER)
# ==========================================
def main():
    # --- NOVO: ROTEAMENTO PÚBLICO (LINK DE APROVAÇÃO) ---
    # Verifica se há parâmetros na URL (query params) ANTES de pedir login
    try:
        # Pega parâmetros da URL
        params = st.query_params.to_dict()

        # Se existir 'proposta_id', é um cliente acessando o link público
        if "proposta_id" in params:
            # Renderiza a view pública e encerra a função main() aqui.
            # O cliente não verá login nem sidebar.
            render_view_publica()
            return
    except Exception as e:
        # Se der erro ao ler params, apenas segue o fluxo normal
        print(f"Erro roteamento: {e}")
        pass
    # ----------------------------------------------------

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