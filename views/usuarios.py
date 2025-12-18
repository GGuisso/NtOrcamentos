import streamlit as st
import pandas as pd
import time
from services import AdminService


def render_usuarios():
    st.header("👥 Gestão de Equipe")
    st.caption("Gerencie quem tem acesso ao sistema da sua empresa.")

    equipe = AdminService.listar_equipe()

    if equipe:
        df_equipe = pd.DataFrame(equipe)

        if not df_equipe.empty:
            cols_mostrar = ["nome", "email", "role"]
            cols_existentes = [c for c in cols_mostrar if c in df_equipe.columns]
            df_visual = df_equipe[cols_existentes].copy()

            mapa_nomes = {"nome": "Nome", "email": "E-mail", "role": "Permissão"}
            df_visual.rename(columns=mapa_nomes, inplace=True)

            # AJUSTE DE WARNING: use_container_width -> width="stretch"
            st.dataframe(df_visual, width="stretch", hide_index=True)

            with st.expander("🗑️ Remover Funcionário"):
                opcoes = {f"{u['nome']} ({u['email']})": u['id'] for u in equipe}

                c_del1, c_del2 = st.columns([3, 1])
                user_sel = c_del1.selectbox("Selecione para excluir:", list(opcoes.keys()),
                                            label_visibility="collapsed")

                if c_del2.button("Remover Selecionado", type="primary"):
                    uid = opcoes[user_sel]

                    meu_user_data = st.session_state.get('usuario_logado', {})
                    meu_id = meu_user_data.get('user_auth').id
                    tenant_atual = meu_user_data.get('tenant_id')

                    if uid == meu_id:
                        st.error("🚫 Você não pode excluir seu próprio usuário aqui.")
                    else:
                        with st.spinner("Removendo acesso..."):
                            ok, msg = AdminService.excluir_usuario(uid, tenant_atual)
                            if ok:
                                st.success(f"✅ {msg}")
                                time.sleep(1)
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"❌ {msg}")
    else:
        st.info("Nenhum usuário encontrado.")

    st.markdown("---")

    st.subheader("➕ Novo Cadastro")

    with st.form("form_novo_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        novo_nome = c1.text_input("Nome do Funcionário")
        novo_role = c2.selectbox("Nível de Acesso", ["vendedor", "admin"],
                                 help="Admin: Acesso total (Financeiro, Estoque, Equipe).\nVendedor: Apenas Orçamentos e Calendário.")

        c3, c4 = st.columns(2)
        novo_email = c3.text_input("E-mail de Login")
        nova_senha = c4.text_input("Senha Inicial", type="password", help="Mínimo 6 caracteres")

        submitted = st.form_submit_button("Criar Usuário")

        if submitted:
            if not novo_nome or not novo_email or not nova_senha:
                st.warning("⚠️ Por favor, preencha todos os campos.")
            elif len(nova_senha) < 6:
                st.warning("⚠️ A senha precisa ter pelo menos 6 caracteres.")
            else:
                tenant_atual = st.session_state.get('tenant_id')

                if not tenant_atual:
                    st.error("Erro de sessão. Faça login novamente.")
                else:
                    with st.spinner("Registrando novo membro..."):
                        ok, msg = AdminService.criar_usuario_equipe(
                            email=novo_email,
                            senha=nova_senha,
                            nome=novo_nome,
                            role=novo_role,
                            tenant_id=tenant_atual
                        )

                        if ok:
                            st.success(f"✅ {msg}")
                            st.balloons()
                            time.sleep(1)
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"❌ {msg}")