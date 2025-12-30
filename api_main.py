# api_main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

# Importando os serviços da pasta refatorada
from services.public_service import PublicService
from services.pix_service import PixService
from services.config import PIX_KEY, PIX_NAME, PIX_CITY

app = FastAPI(title="API Pública NT Festas")

# Configuração de CORS (Permite que seu site Vercel acesse esta API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, troque "*" pela URL do seu Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Modelo de dados para o Aceite
class AceiteRequest(BaseModel):
    ip: str
    navegador: Optional[str] = None


# --- ROTA 1: Health Check (Para o Render saber que está vivo) ---
@app.get("/")
def health_check():
    return {"status": "online", "service": "NT Festas API"}


# --- ROTA 2: Buscar Dados do Orçamento ---
@app.get("/api/orcamento/{uuid}")
def obter_orcamento(uuid: str):
    dados = PublicService.buscar_orcamento_uuid(uuid)

    if not dados:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    if dados.get('status') == 'Cancelado':
        raise HTTPException(status_code=400, detail="Orçamento cancelado.")

    return dados


# --- ROTA 3: Registrar Aceite ---
@app.post("/api/orcamento/{uuid}/aceite")
def registrar_aceite(uuid: str, req: AceiteRequest):
    # Verifica existência
    orcamento = PublicService.buscar_orcamento_uuid(uuid)
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    # Registra no banco
    sucesso, mensagem = PublicService.registrar_aceite(orcamento['id'], req.ip)

    if not sucesso:
        raise HTTPException(status_code=500, detail=mensagem)

    return {"status": "sucesso", "mensagem": "Termos aceitos!"}


# --- ROTA 4: Gerar Pix ---
@app.get("/api/orcamento/{uuid}/pix")
def gerar_pix(uuid: str):
    orcamento = PublicService.buscar_orcamento_uuid(uuid)
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    # Regra: 30% de Sinal
    valor_sinal = round(orcamento['total'] * 0.30, 2)

    # Validação da Chave
    if not PIX_KEY:
        raise HTTPException(status_code=500, detail="Chave PIX não configurada no servidor.")

    # Gera Payload
    payload = PixService.gerar_payload_pix(
        chave_pix=PIX_KEY,
        beneficiario_nome=PIX_NAME or "NT Festas",
        beneficiario_cidade=PIX_CITY or "Esteio",
        valor=valor_sinal,
        txid=f"PED{orcamento['id']}"
    )

    return {
        "payload_pix": payload,
        "valor_sinal": valor_sinal
    }