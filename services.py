# ARQUIVO: services.py
import streamlit as st
import requests
import json
import gspread
import pandas as pd
import datetime
import time
from fpdf import FPDF
from oauth2client.service_account import ServiceAccountCredentials
from supabase import create_client, Client
from typing import Tuple, Dict, List, Any, Optional

# ==========================================
# CONSTANTES
# ==========================================
SHEET_URL = st.secrets.get("SHEET_URL", "")
AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"
VIACEP_URL = "https://viacep.com.br/ws/{}/json/"


# --- FUNÇÃO AUXILIAR PARA LER SECRETS COM SEGURANÇA ---
def get_secret(key_name):
    """
    Tenta buscar a chave na raiz dos secrets.
    Se não encontrar, tenta buscar dentro de GCP_SERVICE_ACCOUNT
    (caso tenha ficado indentado errado no TOML).
    """
    # 1. Tenta na raiz
    if key_name in st.secrets:
        return st.secrets[key_name]

    # 2. Tenta dentro do bloco GCP (erro comum de formatação TOML)
    if "GCP_SERVICE_ACCOUNT" in st.secrets:
        if key_name in st.secrets["GCP_SERVICE_ACCOUNT"]:
            return st.secrets["GCP_SERVICE_ACCOUNT"][key_name]

    return ""


# Credenciais Supabase (Carregamento Robusto)
SUPA_URL = get_secret("SUPABASE_URL")
SUPA_KEY = get_secret("SUPABASE_KEY")

# ID DA EMPRESA (TENANT)
TENANT_ID = "nt_festas_01"


# ==========================================
# CAMADA DE SERVIÇOS (BACKEND)
# ==========================================

class CepService:
    """Gerencia consulta de endereço via CEP (ViaCEP)."""

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


class GoogleSheetsService:
    """Gerencia toda a comunicação com o Google Sheets e Supabase Storage."""

    @staticmethod
    @st.cache_resource
    def get_connection():
        """Conecta ao Google Sheets usando as credenciais do Secrets."""
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

            if "GCP_SERVICE_ACCOUNT" not in st.secrets:
                raise Exception("Segredo GCP_SERVICE_ACCOUNT não encontrado no secrets.toml")

            creds_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])

            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            client.open_by_url(SHEET_URL)
            return client
        except Exception as e:
            st.error(f"Erro de conexão com a planilha: {e}")
            st.stop()

    # --- MÉTODO DE UPLOAD SUPABASE CORRIGIDO ---
    @staticmethod
    def upload_imagem(file_obj, nome_arquivo_original: str) -> Optional[str]:
        """
        Envia foto para o Supabase Storage na pasta do cliente.
        """
        try:
            if not SUPA_URL or not SUPA_KEY:
                st.error("ERRO: SUPABASE_URL ou SUPABASE_KEY não encontrados. Verifique o secrets.toml.")
                return None

            # 1. Conectar ao Supabase
            supabase: Client = create_client(SUPA_URL, SUPA_KEY)

            # 2. Sanitizar nome
            nome_limpo = "".join(
                [c for c in nome_arquivo_original if c.isalnum() or c in (' ', '_', '.', '-')]).replace(" ", "_")

            # 3. Caminho do Arquivo
            file_path = f"{TENANT_ID}/{int(time.time())}_{nome_limpo}"

            # 4. Upload
            bucket_name = "acervo"
            file_bytes = file_obj.getvalue()

            # Envia o arquivo
            response = supabase.storage.from_(bucket_name).upload(
                path=file_path,
                file=file_bytes,
                file_options={"content-type": file_obj.type, "upsert": "false"}
            )

            # 5. Gerar URL Pública
            # Nota: O bucket "acervo" precisa estar configurado como "Public" no dashboard do Supabase
            public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)

            return public_url

        except Exception as e:
            # Imprime o erro no console para debug
            print(f"❌ Erro Supabase Detalhado: {str(e)}")

            msg_erro = str(e)
            if "Duplicate" in msg_erro:
                st.warning("Já existe um arquivo com este nome.")
            elif "kc-not-found" in msg_erro or "Bucket not found" in msg_erro:
                st.error("Erro: Bucket 'acervo' não encontrado no Supabase.")
            else:
                st.error(f"Erro ao enviar imagem: {msg_erro}")
            return None

    @staticmethod
    @st.cache_data(ttl=600)
    def carregar_catalogo() -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        try:
            client = GoogleSheetsService.get_connection()
            sheet = client.open_by_url(SHEET_URL)

            # 1. Itens
            try:
                df_itens = pd.DataFrame(sheet.worksheet("Itens").get_all_records())
                if not df_itens.empty:
                    df_itens['Preco'] = pd.to_numeric(df_itens['Preco'], errors='coerce').fillna(0.0)
                    df_itens['Qtd_Estoque'] = pd.to_numeric(df_itens['Qtd_Estoque'], errors='coerce').fillna(0).astype(
                        int)

                    if 'Imagem' not in df_itens.columns:
                        df_itens['Imagem'] = ""

                    acervo = dict(zip(df_itens['Item'], df_itens['Preco']))
                    estoque = dict(zip(df_itens['Item'], df_itens['Qtd_Estoque']))
                else:
                    acervo = {}
                    estoque = {}
            except:
                acervo = {}
                estoque = {}

            # 2. Temas
            try:
                lista_temas = sheet.worksheet("Temas").get_all_records()
                categorias = {}
                detalhes = {}
                for row in lista_temas:
                    cat, tema, desc = row['Categoria'], row['Tema'], row['Detalhes']
                    categorias.setdefault(cat, []).append(tema)
                    detalhes[tema] = desc
            except:
                categorias, detalhes = {}, {}

            # 3. Kits
            try:
                lista_kits = sheet.worksheet("Kits").get_all_records()
                kits = {}
                for row in lista_kits:
                    itens = [x.strip() for x in str(row['Descricao']).replace(';', '\n').split('\n') if x.strip()]
                    val_str = str(row['Preco']).replace(',', '.')
                    kits[row['Nome']] = {
                        "preco": float(val_str) if val_str else 0.0,
                        "descricao": itens
                    }
            except:
                kits = {}

            return acervo, categorias, kits, detalhes, estoque
        except Exception as e:
            st.error(f"Erro ao carregar configurações: {e}")
            return {}, {}, {}, {}, {}

    @staticmethod
    def carregar_orcamentos() -> List[Dict]:
        try:
            client = GoogleSheetsService.get_connection()
            ws = client.open_by_url(SHEET_URL).worksheet("Orcamentos")
            records = ws.get_all_records()
            dados = []
            for row in records:
                if row.get("DADOS_SISTEMA"):
                    try:
                        dados.append(json.loads(row["DADOS_SISTEMA"]))
                    except:
                        continue
            return dados
        except Exception as e:
            print(f"Erro ao carregar orçamentos: {e}")
            return []

    @staticmethod
    def upsert_orcamento(orcamento: Dict):
        try:
            client = GoogleSheetsService.get_connection()
            ws = client.open_by_url(SHEET_URL).worksheet("Orcamentos")

            row_data = [
                orcamento.get('id'),
                orcamento.get('cliente'),
                orcamento.get('data_evento'),
                orcamento.get('status'),
                f"R$ {orcamento.get('total', 0):.2f}".replace('.', ','),
                json.dumps(orcamento, default=str)
            ]

            cell = ws.find(str(orcamento['id']), in_column=1)

            if cell:
                range_name = f"A{cell.row}:F{cell.row}"
                ws.update(range_name=range_name, values=[row_data])
            else:
                ws.append_row(row_data)

        except Exception as e:
            st.error(f"Erro ao salvar no Google Sheets: {e}")
            raise e

    @staticmethod
    def get_dataframe(worksheet_name: str) -> pd.DataFrame:
        try:
            client = GoogleSheetsService.get_connection()
            sheet = client.open_by_url(SHEET_URL)
            ws = sheet.worksheet(worksheet_name)
            return pd.DataFrame(ws.get_all_records())
        except Exception as e:
            st.error(f"Erro ao ler aba {worksheet_name}: {e}")
            return pd.DataFrame()

    @staticmethod
    def salvar_dataframe(worksheet_name: str, df: pd.DataFrame):
        try:
            client = GoogleSheetsService.get_connection()
            sheet = client.open_by_url(SHEET_URL)
            ws = sheet.worksheet(worksheet_name)
            dados = [df.columns.values.tolist()] + df.astype(str).values.tolist()
            ws.clear()
            ws.update(dados)
        except Exception as e:
            st.error(f"Erro ao salvar {worksheet_name}: {e}")
            raise e

    @staticmethod
    def registrar_transacao(transacao: Dict, update_estoque: Dict = None):
        """Salva a transação financeira e atualiza o estoque (novo ou existente)."""
        client = GoogleSheetsService.get_connection()
        sheet = client.open_by_url(SHEET_URL)

        # 1. Salvar na aba Financeiro
        try:
            ws_fin = sheet.worksheet("Financeiro")
            row = [
                transacao['id'], transacao['data'], transacao['tipo'], transacao['categoria'],
                transacao['descricao'], transacao['valor'], transacao['quem'],
                transacao['forma_pagto'], transacao['status'], transacao.get('loja', ''), transacao.get('link', '')
            ]
            ws_fin.append_row(row)
        except Exception as e:
            raise Exception(f"Erro ao salvar financeiro: {e}")

        # 2. Atualizar Estoque (se houver payload de estoque)
        if update_estoque:
            try:
                ws_itens = sheet.worksheet("Itens")
                item_nome = update_estoque['item']
                qtd_compra = update_estoque['qtd']
                custo_unit = update_estoque['custo']
                loja = update_estoque['loja']
                link = update_estoque['link']
                novo_preco_locacao = update_estoque.get('preco_locacao', 0.0)
                eh_novo = update_estoque.get('is_new', False)

                if eh_novo:
                    nova_linha = [item_nome, novo_preco_locacao, "Acervo", qtd_compra, custo_unit, loja, link, ""]
                    ws_itens.append_row(nova_linha)
                else:
                    cell = ws_itens.find(item_nome, in_column=1)
                    if cell:
                        row_idx = cell.row
                        est_atual = int(ws_itens.cell(row_idx, 4).value or 0)
                        novo_estoque = est_atual + qtd_compra
                        ws_itens.update_cell(row_idx, 4, novo_estoque)  # Qtd
                        ws_itens.update_cell(row_idx, 5, custo_unit)  # Custo
                        ws_itens.update_cell(row_idx, 6, loja)  # Loja
                        ws_itens.update_cell(row_idx, 7, link)  # Link
                    else:
                        nova_linha = [item_nome, 0.0, "Acervo", qtd_compra, custo_unit, loja, link, ""]
                        ws_itens.append_row(nova_linha)

            except Exception as e:
                raise Exception(f"Transação salva, mas erro ao atualizar estoque: {e}")


class InventoryService:
    """Gerencia lógica de disponibilidade com Otimização (Cache)."""

    @staticmethod
    @st.cache_data(show_spinner=False)
    def calcular_mapa_ocupacao(orcamentos: List[Dict]) -> Dict[str, Dict[str, int]]:
        """Cria mapa de ocupação por dia/item para consulta rápida."""
        mapa = {}
        for orc in orcamentos:
            if orc.get('status') in ['Cancelado', 'Reprovado']: continue
            data_str = orc.get('data_evento')
            if not data_str: continue
            if data_str not in mapa: mapa[data_str] = {}

            dados = orc.get('dados_form', {})
            itens = dados.get('in_itens_pers', []) + dados.get('in_itens_add', [])

            for item in itens:
                mapa[data_str][item] = mapa[data_str].get(item, 0) + 1
        return mapa

    @staticmethod
    def verificar_disponibilidade_rapida(item_nome: str, data_evento: str, estoque_total: int, mapa_ocupacao: Dict) -> \
            Tuple[int, int]:
        """Consulta rápida no mapa O(1)."""
        data_str = str(data_evento)
        uso_dia = mapa_ocupacao.get(data_str, {}).get(item_nome, 0)
        saldo = estoque_total - uso_dia
        return uso_dia, saldo


class PDFGenerator:
    """Responsável apenas pela criação do arquivo PDF."""

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text: return ""
        text = text.replace("✅", "").replace("•", "-").replace("⚠️", "[OBS]").replace("🎁", "").replace("💰", "")
        return str(text).encode('latin-1', 'replace').decode('latin-1')

    @classmethod
    def gerar(cls, dados_cli, dados_evt, itens, total, sinal, restante, txt_retirada, txt_devolucao) -> str:
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", style="B", size=16)
            pdf.cell(190, 10, txt="CONTRATO DE LOCACAO - NT FESTAS", ln=True, align='C')
            pdf.ln(5)
            pdf.set_font("Arial", size=10)
            pdf.cell(190, 6, txt=cls._clean_text(f"LOCADOR: NT Festas Decorações"), ln=True)
            end_cli = f"{dados_cli['rua']}, {dados_cli['numero']} - {dados_cli['bairro']}, {dados_cli['cidade']} (CEP: {dados_cli['cep']})"
            pdf.cell(190, 6, txt=cls._clean_text(f"LOCATÁRIO: {dados_cli['nome']} | CPF: {dados_cli['cpf']}"), ln=True)
            pdf.cell(190, 6, txt=cls._clean_text(f"ENDEREÇO: {end_cli}"), ln=True)
            pdf.ln(2)
            end_evt = f"{dados_evt['rua']}, {dados_evt['numero']} - {dados_evt['bairro']}, {dados_evt['cidade']} (CEP: {dados_evt['cep']})"
            pdf.set_fill_color(240, 240, 240)
            pdf.set_font("Arial", style="B", size=10)
            pdf.cell(190, 8, txt=cls._clean_text(f"DADOS DO EVENTO: {dados_evt['data']}"), border=1, ln=True, fill=True)
            pdf.set_font("Arial", size=9)
            pdf.multi_cell(190, 6, txt=cls._clean_text(f"LOCAL: {end_evt}"), border=1)
            pdf.ln(2)
            pdf.set_font("Arial", style="B", size=10)
            pdf.cell(190, 8, txt="AGENDAMENTO (JANELA DE HORÁRIOS):", border=1, ln=True, fill=True, align='C')
            pdf.set_font("Arial", size=9)
            pdf.cell(95, 8, txt=cls._clean_text(f"RETIRADA: {txt_retirada}"), border=1, fill=True)
            pdf.cell(95, 8, txt=cls._clean_text(f"DEVOLUÇÃO: {txt_devolucao}"), border=1, ln=True, fill=True)
            pdf.ln(5)
            pdf.set_font("Arial", style="B", size=12)
            pdf.cell(190, 8, txt="ITENS CONTRATADOS:", ln=True)
            pdf.set_font("Arial", size=9)
            for linha in itens.split('\n'):
                if linha.strip(): pdf.multi_cell(0, 5, txt=cls._clean_text(linha))
            pdf.ln(5)
            pdf.set_font("Arial", style="B", size=12)
            pdf.cell(190, 8, txt=cls._clean_text(f"VALOR TOTAL: R$ {total:.2f}"), ln=True)
            pdf.set_font("Arial", size=10)
            pdf.cell(190, 6, txt=cls._clean_text(f"Sinal para Reserva (30%): R$ {sinal:.2f}"), ln=True)
            pdf.cell(190, 6, txt=cls._clean_text(f"Restante (Dia do Evento): R$ {restante:.2f}"), ln=True)
            pdf.ln(8)
            pdf.set_font("Arial", style="B", size=10)
            pdf.cell(190, 8, txt="TERMOS E CONDICOES GERAIS:", ln=True)
            pdf.set_font("Arial", size=7)
            clausulas = """
            1. DO OBJETO: O presente contrato tem como objeto a locação dos itens descritos.
            2. DA RETIRADA E DEVOLUÇÃO: Respeitar a janela de horários estipulada. Atrasos sujeitos a multa.
            3. DA CONSERVAÇÃO: O locatário é responsável por danos ou perdas.
            4. DO PAGAMENTO: O sinal não é reembolsável em caso de desistência.
            5. PEGUE E MONTE: Transporte, montagem e desmontagem são de responsabilidade do cliente.
            """
            pdf.multi_cell(0, 4, txt=cls._clean_text(clausulas))
            pdf.ln(10)
            pdf.cell(90, 0, "", "T")
            pdf.cell(10, 0, "")
            pdf.cell(90, 0, "", "T")
            pdf.ln(2)
            pdf.cell(90, 5, "NT FESTAS", align='C')
            pdf.cell(10, 5, "")
            pdf.cell(90, 5, cls._clean_text(dados_cli['nome']), align='C')
            filename = f"contrato_{dados_cli['nome'].replace(' ', '_')}.pdf"
            pdf.output(filename)
            return filename
        except Exception as e:
            print(f"Erro PDF: {e}")
            raise e


class EmailService:
    """Gerencia integração com Autentique."""

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
        variables = {
            "document": {"name": "Contrato de Locação - NT Festas"},
            "signers": [{"email": email_cliente, "action": "SIGN"}]
        }
        try:
            with open(caminho_pdf, "rb") as f:
                response = requests.post(
                    AUTENTIQUE_URL,
                    data={"operations": json.dumps({"query": query, "variables": variables}),
                          "map": json.dumps({"0": ["variables.file"]})},
                    files={"0": f},
                    headers={"Authorization": f"Bearer {token}"}
                )
            if response.status_code == 200:
                dados = response.json()
                if dados.get("errors"): return False, f"Erro API: {dados['errors'][0]['message']}"
                doc_data = dados.get("data", {}).get("createDocument", {})
                sigs = doc_data.get("signatures", [])
                link = next((s["link"]["short_link"] for s in sigs if s.get("link")), "EMAIL_ENVIADO")
                return True, link
            return False, f"Erro HTTP {response.status_code}"
        except Exception as e:
            return False, f"Erro Técnico: {e}"