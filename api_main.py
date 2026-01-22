# api_main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

# Importando os serviços
from services.public_service import PublicService
from services.pix_service import PixService
from services.database_service import SupabaseService  # <--- Adicionado
from services.config import PIX_KEY, PIX_NAME, PIX_CITY

app = FastAPI(title="API Pública NT Festas")

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- MODELOS DE DADOS ---

class AceiteRequest(BaseModel):
    ip: str
    navegador: Optional[str] = None


class LoginRequest(BaseModel):  # <--- Adicionado
    email: str
    password: str


# --- ROTA 1: Health Check ---
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
    orcamento = PublicService.buscar_orcamento_uuid(uuid)
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

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

    valor_sinal = round(orcamento['total'] * 0.30, 2)

    if not PIX_KEY:
        raise HTTPException(status_code=500, detail="Chave PIX não configurada no servidor.")

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


# --- ROTA 5: Login Administrativo (NOVA) ---
@app.post("/api/auth/login")
def login_api(dados: LoginRequest):
    supabase = SupabaseService.get_client()
    try:
        # 1. Tenta autenticar no Auth do Supabase
        response = supabase.auth.sign_in_with_password({
            "email": dados.email,
            "password": dados.password
        })

        if response.user and response.session:
            user_id = response.user.id

            # 2. Busca dados extras na tabela 'profiles' (Tenant, Role, Nome)
            # Isso é importante para saber qual "loja" o usuário administra
            res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id", user_id).execute()

            # Valores padrão caso não tenha perfil criado
            nome = "Usuário"
            role = "vendedor"
            tenant_id = None

            if res_profile.data:
                profile = res_profile.data[0]
                tenant_id = profile['tenant_id']
                role = profile['role']
                nome = profile.get('nome', 'Usuário')

            # 3. Retorna tudo que o Frontend precisa
            return {
                "access_token": response.session.access_token,
                "user": {
                    "id": user_id,
                    "email": dados.email,
                    "nome": nome,
                    "role": role,
                    "tenant_id": tenant_id
                }
            }

        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    except Exception as e:
        # Captura erros do Supabase (ex: AuthApiError)
        print(f"Erro Login: {e}")
        raise HTTPException(status_code=401, detail="Email ou senha incorretos.")