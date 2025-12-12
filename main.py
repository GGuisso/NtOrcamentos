# ARQUIVO: main.py
import streamlit as st

# Importa as Views do pacote 'views'
from views.componentes import init_session_state, handle_feedback, render_sidebar
from views.orcamento import render_form_orcamento
from views.historico import render_historico
from views.financeiro import render_financeiro
from views.gestao import render_gestao
from views.calendario import render_calendario  # <--- NOVA IMPORTAÇÃO
from services import GoogleSheetsService

# ==========================================
# CONFIGURAÇÃO INICIAL
# ==========================================
st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")


# ==========================================
# MAIN APP LOOP
# ==========================================

def main():
    # Inicializa estado
    init_session_state()

    # Carrega dados do backend
    acervo, categorias, kits, detalhes, estoque_dict = GoogleSheetsService.carregar_catalogo()

    # Processa feedbacks (toast/balões)
    handle_feedback()

    # Renderiza Sidebar
    render_sidebar()

    # Menu de Navegação (Adicionado "📅 Calendário")
    opcoes_menu = ["📝 Novo Orçamento", "📂 Histórico de Orçamentos", "📅 Calendário", "💰 Financeiro",
                   "⚙️ Gestão de Acervo"]

    nav = st.radio("Menu", opcoes_menu, horizontal=True, key="navegacao_atual", label_visibility="collapsed")
    st.divider()

    # Roteamento de Views
    if nav == "📝 Novo Orçamento":
        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)
    elif nav == "📂 Histórico de Orçamentos":
        render_historico()
    elif nav == "📅 Calendário":  # <--- NOVA ROTA
        render_calendario()
    elif nav == "💰 Financeiro":
        render_financeiro(acervo)
    elif nav == "⚙️ Gestão de Acervo":
        render_gestao()


if __name__ == "__main__":
    main()