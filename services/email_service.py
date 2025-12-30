# services/email_service.py
import streamlit as st
import requests
import json
from typing import Tuple
from .config import AUTENTIQUE_URL

class EmailService:
    @staticmethod
    def enviar_contrato(caminho_pdf: str, email_cliente: str) -> Tuple[bool, str]:
        token = st.secrets.get("AUTENTIQUE_TOKEN", "")
        if not token: return False, "Token não configurado."
        query = """
        mutation CreateDocument($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {
          createDocument(document: $document, signers: $signers, file: $file) {
            signatures { link { short_link } }
          }
        }
        """
        variables = {"document": {"name": "Contrato de Locação - NT Festas"}, "signers": [{"email": email_cliente, "action": "SIGN"}]}
        try:
            with open(caminho_pdf, "rb") as f:
                response = requests.post(AUTENTIQUE_URL,
                                         data={"operations": json.dumps({"query": query, "variables": variables}),
                                               "map": json.dumps({"0": ["variables.file"]})}, files={"0": f},
                                         headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 200:
                dados = response.json()
                if dados.get("errors"): return False, f"Erro API: {dados['errors'][0]['message']}"
                link = next((s["link"]["short_link"] for s in dados.get("data", {}).get("createDocument", {}).get("signatures", []) if s.get("link")), "EMAIL_ENVIADO")
                return True, link
            return False, f"Erro HTTP {response.status_code}"
        except Exception as e:
            return False, f"Erro Técnico: {e}"