# services/admin_service.py
import streamlit as st
from supabase import create_client, Client
from .config import get_secret, SUPA_URL

class AdminService:
    @staticmethod
    def get_admin_client() -> Client:
        service_key = get_secret("SUPABASE_SERVICE_KEY")
        if not service_key:
            st.error("⚠️ Configuração de segurança ausente: SUPABASE_SERVICE_KEY")
            st.stop()
        return create_client(SUPA_URL, service_key)

    @staticmethod
    def criar_usuario_equipe(email, senha, nome, role, tenant_id):
        admin_supabase = AdminService.get_admin_client()
        try:
            user_response = admin_supabase.auth.admin.create_user({
                "email": email, "password": senha, "email_confirm": True, "user_metadata": {"nome": nome}
            })
            new_user_id = user_response.user.id
            profile_payload = {"id": new_user_id, "tenant_id": tenant_id, "email": email, "nome": nome, "role": role}
            admin_supabase.table("profiles").insert(profile_payload).execute()
            return True, "Usuário criado com sucesso!"
        except Exception as e:
            msg_erro = str(e)
            if "already registered" in msg_erro: return False, "Este e-mail já está cadastrado."
            return False, f"Erro ao criar usuário: {msg_erro}"

    @staticmethod
    def listar_equipe():
        admin_supabase = AdminService.get_admin_client()
        tenant = st.session_state.get('tenant_id')
        if not tenant: return []
        res = admin_supabase.table("profiles").select("*").eq("tenant_id", tenant).execute()
        return res.data

    @staticmethod
    def excluir_usuario(user_id_alvo, tenant_atual):
        admin_supabase = AdminService.get_admin_client()
        if not tenant_atual: return False, "Sessão inválida."
        try:
            res = admin_supabase.table("profiles").select("id").eq("id", user_id_alvo).eq("tenant_id", tenant_atual).execute()
            if not res.data: return False, "Usuário não encontrado ou não pertence à sua equipe."
            admin_supabase.auth.admin.delete_user(user_id_alvo)
            return True, "Usuário removido."
        except Exception as e:
            return False, str(e)