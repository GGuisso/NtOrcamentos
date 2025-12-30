# services/config.py
import os

# Tenta importar o streamlit, mas não quebra se não existir ou der erro (caso da API rodando pura)
try:
    import streamlit as st
except ImportError:
    st = None

# URLs constantes
VIACEP_URL = "https://viacep.com.br/ws/{}/json/"
AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"


def get_secret(key_name, default=""):
    """
    Busca híbrida de segredos:
    1. Tenta Variável de Ambiente (Prioridade para Render/API)
    2. Tenta Secrets do Streamlit (Fallback para desenvolvimento local)
    """
    # 1. Prioridade: Variável de Ambiente (Render)
    env_val = os.getenv(key_name)
    if env_val:
        return env_val

    # 2. Fallback: Streamlit Secrets (Apenas se o st estiver carregado)
    if st:
        try:
            # Verifica se a chave está na raiz dos segredos
            if key_name in st.secrets:
                return st.secrets[key_name]

            # Procura dentro de seções (ex: [gcp_service_account] ou [general])
            # st.secrets se comporta como dicionário
            for section in st.secrets.values():
                if isinstance(section, dict) and key_name in section:
                    return section[key_name]
        except Exception:
            # Se der erro (ex: rodando script fora do contexto do streamlit), apenas ignora
            pass

    return default


# --- Mapeamento das Chaves ---
# Use estas variáveis no resto do sistema ao invés de chamar get_secret direto

# Banco de Dados
SUPA_URL = get_secret("SUPABASE_URL")
SUPA_KEY = get_secret("SUPABASE_KEY")

# Chaves do Pix (Necessárias para a API pública)
PIX_KEY = get_secret("PIX_KEY")
PIX_NAME = get_secret("PIX_NAME")
PIX_CITY = get_secret("PIX_CITY")