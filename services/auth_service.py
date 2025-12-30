# services/auth_service.py
import streamlit as st
from .database_service import SupabaseService

class AuthService:
    @staticmethod
    def login(email, senha):
        supabase = SupabaseService.get_client()
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": senha})
            if response.user and response.session:
                res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id", response.user.id).execute()
                tenant_id = None
                role = 'vendedor'
                if res_profile.data:
                    tenant_id = res_profile.data[0]['tenant_id']
                    role = res_profile.data[0]['role']
                st.session_state['tenant_id'] = tenant_id
                return True, {"user_auth": response.user, "tenant_id": tenant_id, "role": role, "email": email, "access_token": response.session.access_token}
            return False, "Credenciais inválidas."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_user_by_token(token):
        supabase = SupabaseService.get_client()
        try:
            response = supabase.auth.get_user(token)
            if response and response.user:
                user = response.user
                res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id", user.id).execute()
                tenant_id = None
                role = 'vendedor'
                if res_profile.data:
                    tenant_id = res_profile.data[0]['tenant_id']
                    role = res_profile.data[0]['role']
                st.session_state['tenant_id'] = tenant_id
                return {"user_auth": user, "tenant_id": tenant_id, "role": role, "email": user.email, "access_token": token}
            return None
        except Exception:
            return None

    @staticmethod
    def logout():
        supabase = SupabaseService.get_client()
        try:
            supabase.auth.sign_out()
            return True
        except:
            return False