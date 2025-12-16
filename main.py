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

    # Pega usuário logado (Dicionário retornado pelo AuthService)
    usuario = st.session_state.get('usuario_logado')

    email_user = usuario['email'] if usuario else ""
    role_user = usuario['role'] if usuario else "vendedor"  # Pega o cargo do banco

    # ----------------------------------------------------
    # CONTROLE DE ACESSO (PERMISSÕES VIA BANCO)
    # ----------------------------------------------------
    # Agora a verificação é dinâmica baseada na coluna 'role' da tabela profiles
    eh_admin = (role_user == 'admin')

    # Menu Base (Todos veem)
    opcoes_menu = ["📝 Novo Orçamento", "📂 Histórico de Orçamentos", "📅 Calendário"]

    # Menu Extra (Só Admin vê)
    if eh_admin:
        opcoes_menu.extend(["💰 Financeiro", "⚙️ Gestão de Acervo"])
    # ----------------------------------------------------

    # Renderiza Sidebar
    with st.sidebar:
        st.title("NT Festas")
        st.caption(f"Logado como: {email_user}")

        # Mostra o badge de acordo com o cargo real
        if eh_admin:
            st.success(f"Perfil: {role_user.upper()} 🔓")
        else:
            st.info(f"Perfil: {role_user.upper()} 👤")

        st.markdown("---")

        # --- CORREÇÃO AQUI: SINCRONIZAÇÃO DO MENU ---
        # 1. Descobre qual o índice da página atual na lista de opções
        # Isso permite que o botão "Editar" do histórico mude o menu automaticamente
        nav_atual = st.session_state.get('navegacao_atual', "📝 Novo Orçamento")
        try:
            idx_nav = opcoes_menu.index(nav_atual)
        except ValueError:
            idx_nav = 0 # Se não achar (ex: mudou de permissão), vai para o primeiro

        # 2. Cria o Radio Button usando esse índice
        nav = st.radio("Menu", opcoes_menu, index=idx_nav)

        # 3. Se o usuário clicou no menu (mudou manualmente), atualiza a sessão
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
        # Botão de Logout
        if st.button("Sair (Logout)"):
            AuthService.logout()
            st.session_state['usuario_logado'] = None
            st.rerun()

    # Roteamento de Views
    if nav == "📝 Novo Orçamento":
        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)
    elif nav == "📂 Histórico de Orçamentos":
        render_historico()
    elif nav == "📅 Calendário":
        render_calendario()
    elif nav == "💰 Financeiro":
        if eh_admin:
            render_financeiro(acervo)
        else:
            st.error("Acesso negado.")
    elif nav == "⚙️ Gestão de Acervo":
        if eh_admin:
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