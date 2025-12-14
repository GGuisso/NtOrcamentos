import streamlit as st
import time
from services import AuthService


def render_login():
    # Centraliza o formulário usando colunas
    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.header("🎈 NT Software - Acesso")

        with st.container(border=True):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")

            if st.button("Entrar", type="primary", use_container_width=True):
                if not email or not senha:
                    st.error("Preencha todos os campos.")
                else:
                    with st.spinner("Autenticando..."):
                        ok, resposta = AuthService.login(email, senha)
                        if ok:
                            st.session_state['usuario_logado'] = resposta
                            st.success("Login realizado!")
                            time.sleep(1)
                            st.rerun()  # Recarrega a página para entrar no sistema
                        else:
                            st.error(f"Erro: {resposta}")

        st.caption("Esqueceu a senha? Contate o administrador.")