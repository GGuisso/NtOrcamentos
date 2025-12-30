# services/cep_service.py
import requests
from typing import Optional, Dict
from .config import VIACEP_URL

class CepService:
    @staticmethod
    def consultar(cep: str) -> Optional[Dict[str, str]]:
        if not cep: return None
        cep_limpo = "".join([c for c in cep if c.isdigit()])
        if len(cep_limpo) != 8: return None
        try:
            response = requests.get(VIACEP_URL.format(cep_limpo), timeout=3)
            if response.status_code == 200:
                dados = response.json()
                if "erro" in dados: return None
                return dados
            return None
        except Exception as e:
            print(f"Erro ao consultar CEP: {e}")
            return None