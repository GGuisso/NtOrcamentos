# api_main.py
from datetime import date, datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

# --- IMPORTS DOS SERVIÇOS ---
from services.public_service import PublicService
from services.pix_service import PixService
from services.database_service import SupabaseService
from services.admin_service import AdminService  # <--- CRUCIAL para o Dashboard
from services.config import PIX_KEY, PIX_NAME, PIX_CITY

app = FastAPI(title="API Pública NT Festas")

# --- CONFIGURAÇÃO DE CORS ---
# Permite que o Next.js (localhost:3000) e o Vercel acessem sua API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- MODELOS DE DADOS (Pydantic) ---

class AceiteRequest(BaseModel):
    ip: str
    navegador: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


# ==========================================
#              ROTAS GERAIS
# ==========================================

@app.get("/")
def health_check():
    """Rota para verificar se a API está online no Render."""
    return {
        "status": "online",
        "service": "NT Festas API",
        "server_date": str(date.today())
    }


# ==========================================
#           ROTAS PÚBLICAS (CLIENTE FINAL)
# ==========================================

@app.get("/api/orcamento/{uuid}")
def obter_orcamento(uuid: str):
    """Busca os dados do orçamento pelo UUID do link público."""
    dados = PublicService.buscar_orcamento_uuid(uuid)

    if not dados:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    if dados.get('status') == 'Cancelado':
        raise HTTPException(status_code=400, detail="Orçamento cancelado.")

    return dados


@app.post("/api/orcamento/{uuid}/aceite")
def registrar_aceite(uuid: str, req: AceiteRequest):
    """Registra o aceite dos termos pelo cliente."""
    orcamento = PublicService.buscar_orcamento_uuid(uuid)
    if not orcamento:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")

    sucesso, mensagem = PublicService.registrar_aceite(orcamento['id'], req.ip)

    if not sucesso:
        raise HTTPException(status_code=500, detail=mensagem)

    return {"status": "sucesso", "mensagem": "Termos aceitos!"}


@app.get("/api/orcamento/{uuid}/pix")
def gerar_pix(uuid: str):
    """Gera o payload Pix Copia e Cola para o sinal (30%)."""
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


# ==========================================
#           ROTAS ADMIN (DASHBOARD)
# ==========================================

@app.post("/api/auth/login")
def login_api(dados: LoginRequest):
    """Realiza o login administrativo e retorna o token + dados do usuário."""
    supabase = SupabaseService.get_client()  # Usa cliente padrão para Auth
    try:
        # 1. Autenticação no Supabase Auth
        response = supabase.auth.sign_in_with_password({
            "email": dados.email,
            "password": dados.password
        })

        if response.user and response.session:
            user_id = response.user.id

            # 2. Busca dados do perfil (Tenant/Loja)
            # Tenta buscar com o cliente logado, se falhar por RLS, o AdminService seria opção,
            # mas geralmente o próprio usuário pode ler seu perfil.
            res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id", user_id).execute()

            nome = "Usuário"
            role = "vendedor"
            tenant_id = None

            if res_profile.data:
                profile = res_profile.data[0]
                tenant_id = profile['tenant_id']
                role = profile['role']
                nome = profile.get('nome', 'Usuário')

            # 3. Retorna Token e Objeto User
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
        print(f"Erro Login: {e}")
        raise HTTPException(status_code=401, detail="Email ou senha incorretos.")


@app.get("/api/dashboard/kpis")
def get_dashboard_kpis(tenant_id: str, mes: Optional[int] = None, ano: Optional[int] = None):
    """Calcula os indicadores do dashboard. Usa AdminService para bypass de RLS."""

    # ATENÇÃO: Usando AdminService para garantir leitura dos dados
    supabase = AdminService.get_admin_client()

    try:
        # Define filtro de data (se não passado, usa data de hoje)
        hoje = date.today()
        filtro_mes = mes if mes else hoje.month
        filtro_ano = ano if ano else hoje.year

        # Busca orçamentos do tenant
        res = supabase.table("orcamentos").select("id, status, data_evento, valor_total").eq("tenant_id",
                                                                                             tenant_id).execute()

        # Inicializa contadores
        kpis = {
            "faturamento": 0.0,  # Específico do mês/ano filtrado (ex: Jan/2025)
            "faturamento_geral": 0.0,  # Total acumulado histórico (ex: Inclui 2026)
            "pipeline": 0.0,  # Orçamentos aguardando aprovação
            "pipeline_qtd": 0,
            "festas_semana": 0,
            "ticket_medio": 0.0
        }

        total_fechado_valor = 0.0
        total_fechado_qtd = 0
        status_fechado = ['Reserva Confirmada', 'Itens Retirados', 'Finalizado', 'Aguardando Pagamento']

        for orc in res.data:
            valor = float(orc.get('valor_total') or 0.0)
            status = orc.get('status')

            # Converte data com segurança
            d_evento = None
            if orc.get('data_evento'):
                try:
                    d_evento = datetime.strptime(orc['data_evento'], '%Y-%m-%d').date()
                except:
                    pass

            # 1. Pipeline (Aguardando Aprovação - Independe de data)
            if status == 'Aguardando Aprovação':
                kpis["pipeline"] += valor
                kpis["pipeline_qtd"] += 1

            # 2. Dados de Fechamento (Faturamento)
            if status in status_fechado:
                # Acumula no Geral (LIFETIME)
                kpis["faturamento_geral"] += valor
                total_fechado_valor += valor
                total_fechado_qtd += 1

                # Acumula no Mensal (Se bater a data do filtro)
                if d_evento and d_evento.month == filtro_mes and d_evento.year == filtro_ano:
                    kpis["faturamento"] += valor

                # 3. Festas na Semana (Baseado na data real de hoje)
                if d_evento:
                    delta = (d_evento - hoje).days
                    if 0 <= delta <= 7:
                        kpis["festas_semana"] += 1

        # 4. Cálculo do Ticket Médio
        if total_fechado_qtd > 0:
            kpis["ticket_medio"] = total_fechado_valor / total_fechado_qtd

        return kpis

    except Exception as e:
        print(f"Erro KPI: {e}")
        # Retorna erro 500 se falhar a conexão ou cálculo
        raise HTTPException(status_code=500, detail=f"Erro ao calcular indicadores: {str(e)}")


@app.get("/api/dashboard/recentes")
def get_orcamentos_recentes(tenant_id: str):
    """Lista os 5 últimos orçamentos. Usa AdminService para bypass de RLS."""

    # ATENÇÃO: Usando AdminService para garantir leitura dos dados
    supabase = AdminService.get_admin_client()

    try:
        # Busca os 5 últimos
        res = supabase.table("orcamentos") \
            .select("id, status, data_evento, valor_total, link_uuid, clientes(nome)") \
            .eq("tenant_id", tenant_id) \
            .order("created_at", desc=True) \
            .limit(5) \
            .execute()

        dados_formatados = []
        for row in res.data:
            cliente_nome = row['clientes']['nome'] if row['clientes'] else "Desconhecido"

            dados_formatados.append({
                "id": row['id'],
                "cliente": cliente_nome,
                "data_evento": row['data_evento'],
                "status": row['status'],
                "total": float(row['valor_total'] or 0),
                "uuid": row['link_uuid']
            })

        return dados_formatados

    except Exception as e:
        print(f"Erro Lista Recentes: {e}")
        return []