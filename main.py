import streamlit as st
import extra_streamlit_components as stx
import time
import datetime  # Movido para o topo para evitar erros

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
from views.publico import render_view_publica
from views.dashboard import render_dashboard
from services import SupabaseService, AuthService

# ==========================================
# GERENCIADOR DE COOKIES (CORRIGIDO)
# ==========================================
# Removemos o @st.cache_resource e a função.
# Instanciamos direto com uma KEY para manter a referência entre recargas.
cookie_manager = stx.CookieManager(key="nt_festas_cookies")


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
    opcoes_menu = ["📊 Dashboard", "📝 Novo Orçamento", "📂 Histórico de Orçamentos", "📅 Calendário"]

    # Menu Extra (Só Admin vê)
    if eh_admin:
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
        nav_atual = st.session_state.get('navegacao_atual', "📊 Dashboard")

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
            # ATUALIZAÇÃO: Removemos 'value=' porque a key já existe no session_state
            c_km = st.number_input("Custo KM", step=0.10, key='cfg_km')
            c_hora = st.number_input("Vr. Hora Técnica", step=5.00, key='cfg_hora')
            c_taxa = st.number_input("Taxa Higienização", step=1.00, key='cfg_taxa')

            if st.button("💾 Salvar Configurações"):
                with st.spinner("Gravando no banco..."):
                    payload = {
                        "custo_km": c_km,
                        "custo_hora": c_hora,
                        "taxa_higienizacao": c_taxa
                    }
                    ok, msg = SupabaseService.atualizar_configuracoes(tenant_id, payload)
                    if ok:
                        st.success(msg)
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
        # ---------------------------------------------------------------

        st.markdown("---")
        if st.button("Sair (Logout)"):
            AuthService.logout()
            st.session_state['usuario_logado'] = None

            # 1. Manda deletar o cookie
            cookie_manager.delete("nt_access_token")

            # 2. Mostra feedback visual
            st.toast("Saindo do sistema...", icon="👋")

            # 3. PAUSA OBRIGATÓRIA: Dá tempo para o navegador processar a deleção
            time.sleep(2)

            st.rerun()

    # --- ROTEAMENTO DE VIEWS ---

    if nav == "📊 Dashboard":
        st.session_state['edit_id'] = None
        render_dashboard()

    elif nav == "📝 Novo Orçamento":
        if st.session_state.get('navegacao_atual') != "📝 Novo Orçamento":
            st.session_state['edit_id'] = None

        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)

    elif nav == "📂 Histórico de Orçamentos":
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
# WRAPPER DE LOGIN (Para injetar o Cookie)
# ==========================================
def handle_login_ui():
    """Renderiza o login e salva o cookie se der certo"""
    email = st.text_input("E-mail")
    senha = st.text_input("Senha", type="password")

    if st.button("Entrar", type="primary", use_container_width=True):
        ok, dados = AuthService.login(email, senha)
        if ok:
            st.session_state['usuario_logado'] = dados
            # SALVA O COOKIE (Validade 7 dias)
            # Usa datetime.datetime.now() pois importamos datetime
            expires = datetime.datetime.now() + datetime.timedelta(days=7)
            cookie_manager.set("nt_access_token", dados['access_token'], expires_at=expires)
            st.rerun()
        else:
            st.error(dados)


# ==========================================
# FLUXO PRINCIPAL (GATEKEEPER)
# ==========================================
def main():
    # --- NOVO: ROTEAMENTO PÚBLICO (LINK DE APROVAÇÃO) ---
    try:
        params = st.query_params.to_dict()
        if "proposta_id" in params:
            render_view_publica()
            return
    except Exception as e:
        print(f"Erro roteamento: {e}")
        pass
    # ----------------------------------------------------

    # Verifica se existe usuário na sessão
    if 'usuario_logado' not in st.session_state:
        st.session_state['usuario_logado'] = None

    # Se NÃO estiver logado na memória, tenta recuperar via Cookie
    if st.session_state['usuario_logado'] is None:
        # Pega o cookie
        cookies = cookie_manager.get_all()
        token_cookie = cookies.get("nt_access_token")

        if token_cookie:
            # Valida token no Supabase
            user_recuperado = AuthService.get_user_by_token(token_cookie)
            if user_recuperado:
                st.session_state['usuario_logado'] = user_recuperado
                st.toast("Login restaurado!", icon="🍪")
                time.sleep(0.5)
                st.rerun()
            else:
                # Token inválido ou expirado
                cookie_manager.delete("nt_access_token")

    # Decisão de Renderização
    if st.session_state['usuario_logado']:
        run_app()
    else:
        st.title("🔐 Acesso Restrito")
        with st.container(border=True):
            st.markdown("### NT Festas - Login")
            handle_login_ui()


if __name__ == "__main__":
    main()