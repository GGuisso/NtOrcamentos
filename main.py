import streamlit as st
from fpdf import FPDF
import requests
import os
import json
import datetime
import pandas as pd
from datetime import date
import time
import gspread
import urllib.parse
from oauth2client.service_account import ServiceAccountCredentials
from typing import Tuple, Dict, List, Any, Optional

# ==========================================
# CONFIGURAÇÃO INICIAL E CONSTANTES
# ==========================================
st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")

SHEET_URL = st.secrets["SHEET_URL"]
AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"
VIACEP_URL = "https://viacep.com.br/ws/{}/json/"


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
    """Gerencia toda a comunicação com o Google Sheets."""

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

    @staticmethod
    @st.cache_data(ttl=600)
    def carregar_catalogo() -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        try:
            client = GoogleSheetsService.get_connection()
            sheet = client.open_by_url(SHEET_URL)

            # 1. Itens (Agora carregando estoque)
            try:
                df_itens = pd.DataFrame(sheet.worksheet("Itens").get_all_records())
                df_itens['Preco'] = pd.to_numeric(df_itens['Preco'], errors='coerce').fillna(0.0)
                df_itens['Qtd_Estoque'] = pd.to_numeric(df_itens['Qtd_Estoque'], errors='coerce').fillna(0).astype(int)

                acervo = dict(zip(df_itens['Item'], df_itens['Preco']))
                estoque = dict(zip(df_itens['Item'], df_itens['Qtd_Estoque']))
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

            # --- CORREÇÃO GSPREAD V6+ (Mantida da resposta anterior) ---
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

    # --- MÉTODOS FINANCEIROS ---
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
                    nova_linha = [item_nome, novo_preco_locacao, "Acervo", qtd_compra, custo_unit, loja, link]
                    ws_itens.append_row(nova_linha)
                else:
                    # --- CORREÇÃO GSPREAD V6+ (Mantida da resposta anterior) ---
                    cell = ws_itens.find(item_nome, in_column=1)

                    if cell:
                        row_idx = cell.row
                        estoque_atual_str = ws_itens.cell(row_idx, 4).value
                        estoque_atual = int(
                            estoque_atual_str) if estoque_atual_str and estoque_atual_str.isdigit() else 0

                        novo_estoque = estoque_atual + qtd_compra
                        ws_itens.update_cell(row_idx, 4, novo_estoque)  # Qtd
                        ws_itens.update_cell(row_idx, 5, custo_unit)  # Custo
                        ws_itens.update_cell(row_idx, 6, loja)  # Loja
                        ws_itens.update_cell(row_idx, 7, link)  # Link
                    else:
                        # Caso de segurança
                        nova_linha = [item_nome, 0.0, "Acervo", qtd_compra, custo_unit, loja, link]
                        ws_itens.append_row(nova_linha)

            except Exception as e:
                raise Exception(f"Transação salva, mas erro ao atualizar estoque: {e}")


class InventoryService:
    """Gerencia lógica de disponibilidade de itens."""

    @staticmethod
    def verificar_disponibilidade(item_nome: str, data_evento: str, estoque_total: int, orcamentos: List[Dict]) -> \
            Tuple[int, int]:
        usados_no_dia = 0
        try:
            target_date = datetime.datetime.strptime(data_evento, '%Y-%m-%d').date()
        except:
            return 0, estoque_total

        for orc in orcamentos:
            if orc.get('status') in ['Reprovado', 'Cancelado']: continue
            orc_date_str = orc.get('data_evento')
            if not orc_date_str: continue

            try:
                orc_date = datetime.datetime.strptime(orc_date_str, '%Y-%m-%d').date()
            except:
                continue

            if orc_date == target_date:
                dados_form = orc.get('dados_form', {})
                itens_lista = dados_form.get('in_itens_pers', []) + dados_form.get('in_itens_add', [])
                if item_nome in itens_lista:
                    usados_no_dia += 1

        saldo = estoque_total - usados_no_dia
        return usados_no_dia, saldo


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


# ==========================================
# CAMADA DE ESTADO E UTILITÁRIOS DA UI
# ==========================================

def init_session_state():
    if 'db_orcamentos' not in st.session_state:
        st.session_state['db_orcamentos'] = GoogleSheetsService.carregar_orcamentos()
    if 'edit_id' not in st.session_state: st.session_state['edit_id'] = None
    if 'navegacao_atual' not in st.session_state: st.session_state['navegacao_atual'] = "📝 Novo Orçamento"
    if 'feedback_msg' not in st.session_state: st.session_state['feedback_msg'] = None
    keys_end = ["in_cli_rua", "in_cli_bairro", "in_cli_cidade", "in_cli_num",
                "in_evt_rua", "in_evt_bairro", "in_evt_cidade", "in_evt_num",
                "in_evt_cep", "in_cli_cep"]
    for k in keys_end:
        if k not in st.session_state: st.session_state[k] = ""


def reset_form_state():
    keys_to_delete = [k for k in st.session_state.keys() if k.startswith("in_")]
    for k in keys_to_delete:
        del st.session_state[k]
    st.session_state['in_data'] = date.today()
    init_session_state()


def handle_feedback():
    if st.session_state['feedback_msg']:
        tipo, msg = st.session_state['feedback_msg']
        if tipo == "success":
            st.toast(msg, icon="✅")
            if any(x in msg for x in ["criado", "atualizado", "copiados"]): st.balloons()
        else:
            st.error(msg)
        st.session_state['feedback_msg'] = None


# ==========================================
# CAMADA DE INTERFACE (VIEW)
# ==========================================

def render_sidebar():
    with st.sidebar:
        st.title("NT Festas")
        st.markdown("---")
        if st.button("🔄 Atualizar Estoque/Temas"):
            st.cache_data.clear()
            st.rerun()
        st.header("⚙️ Custos Operacionais")
        st.number_input("Custo KM", value=st.session_state.get('cfg_km', 2.00), step=0.10, key='cfg_km')
        st.number_input("Valor Hora Técnica", value=st.session_state.get('cfg_hora', 50.00), step=5.00, key='cfg_hora')
        st.number_input("Taxa Higienização", value=st.session_state.get('cfg_taxa', 20.00), key='cfg_taxa')


def render_gestao():
    st.header("📦 Gestão de Acervo e Configurações")
    tab_itens, tab_temas, tab_kits = st.tabs(["🧩 Itens Avulsos", "🎨 Temas", "🎁 Kits"])

    with tab_itens:
        st.subheader("Cadastro de Itens, Preços e Estoque")
        df_itens = GoogleSheetsService.get_dataframe("Itens")
        if not df_itens.empty:
            df_editado = st.data_editor(
                df_itens,
                num_rows="dynamic",
                column_config={
                    "Preco": st.column_config.NumberColumn("Preço Locação (R$)", format="%.2f", min_value=0.0),
                    "Qtd_Estoque": st.column_config.NumberColumn("Estoque Total", step=1),
                    "Custo_Unitario": st.column_config.NumberColumn("Custo Aq. (R$)", format="%.2f"),
                    "Link_Referencia": st.column_config.LinkColumn("Link Compra")
                },
                width='stretch',
                key="editor_itens"
            )
            if st.button("💾 Salvar Alterações em ITENS"):
                with st.spinner("Atualizando banco de dados..."):
                    GoogleSheetsService.salvar_dataframe("Itens", df_editado)
                    st.cache_data.clear()
                    st.session_state['feedback_msg'] = ("success", "Tabela de Itens atualizada!")
                    st.rerun()

    with tab_temas:
        st.subheader("Cadastro de Temas")
        df_temas = GoogleSheetsService.get_dataframe("Temas")
        if not df_temas.empty:
            df_editado_temas = st.data_editor(df_temas, num_rows="dynamic", width='stretch', key="editor_temas")
            if st.button("💾 Salvar Alterações em TEMAS"):
                with st.spinner("Atualizando temas..."):
                    GoogleSheetsService.salvar_dataframe("Temas", df_editado_temas)
                    st.cache_data.clear()
                    st.session_state['feedback_msg'] = ("success", "Temas atualizados!")
                    st.rerun()

    with tab_kits:
        st.subheader("Configuração de Kits")
        df_kits = GoogleSheetsService.get_dataframe("Kits")
        if not df_kits.empty:
            df_editado_kits = st.data_editor(
                df_kits,
                num_rows="dynamic",
                column_config={
                    "Preco": st.column_config.NumberColumn("Preço Base (R$)", format="%.2f"),
                    "Descricao": st.column_config.TextColumn("Itens do Kit", width="large")
                },
                width='stretch',
                key="editor_kits"
            )
            if st.button("💾 Salvar Alterações em KITS"):
                with st.spinner("Atualizando kits..."):
                    GoogleSheetsService.salvar_dataframe("Kits", df_editado_kits)
                    st.cache_data.clear()
                    st.session_state['feedback_msg'] = ("success", "Kits atualizados!")
                    st.rerun()


def render_financeiro(acervo_dict):
    st.header("💰 Controle Financeiro")
    tab_lanc, tab_dash = st.tabs(["📝 Novo Lançamento", "📊 Extrato & Dashboard"])

    with tab_lanc:
        st.subheader("Registrar Movimentação")
        tipo_mov = st.radio("O que você deseja lançar?", ["Receita (Entrada)", "Despesa (Saída)"], horizontal=True)

        # === CORREÇÃO: Removido st.form para permitir atualização dinâmica do UI ===
        # with st.form("form_financeiro"): <-- Removido
        c1, c2 = st.columns(2)
        f_data = c1.date_input("Data do Pagamento/Gasto", value=date.today())

        if tipo_mov == "Receita (Entrada)":
            f_cat = c2.selectbox("Categoria", ["Sinal de Reserva", "Restante Pagamento", "Receita Extra", "Outros"])
            st.markdown("##### 🔗 Vínculo com Orçamento")
            orcamentos_ativos = [o for o in st.session_state['db_orcamentos'] if
                                    o['status'] in ['Aprovado', 'Aguardando', 'Reserva Confirmada']]
            opcoes_orc = ["Sem Vínculo"] + [f"#{o['id']} - {o['cliente']} ({o['data_evento']})" for o in
                                            orcamentos_ativos]
            orc_selecionado = st.selectbox("Este valor refere-se a qual festa?", opcoes_orc)
            f_tipo = "Receita"
            desc_placeholder = "Ex: Sinal do cliente X"
            if orc_selecionado != "Sem Vínculo":
                desc_placeholder = f"Entrada ref. {orc_selecionado}"
        else:
            f_cat = c2.selectbox("Categoria", ["Compra de Acervo", "Consumo (Balões, Descartáveis)",
                                                "Fixo (Luz, Aluguel, Internet)",
                                                "Serviço (Frete, Mão de obra, Higienização)"])
            f_tipo = "Despesa"
            desc_placeholder = "Ex: Conta de Luz, Compra Shopee"

        desc_input = st.text_input("Descrição",
                                    value=desc_placeholder if 'orc_selecionado' in locals() and orc_selecionado != "Sem Vínculo" else "",
                                    placeholder="Descreva o lançamento")

        c3, c4, c5 = st.columns(3)
        val = c3.number_input("Valor (R$)", min_value=0.0, step=10.0)
        quem = c4.text_input("Quem Realizou?", value="NT Festas")
        forma = c5.selectbox("Forma Pagto", ["Pix", "Cartão Crédito", "Dinheiro", "Boleto", "Débito"])

        update_stock = False
        is_new_item = False
        item_nome = None
        qtd_compra = 0
        custo_locacao = 0.0
        loja_compra = ""
        link_compra = ""

        if f_tipo == "Despesa" and f_cat == "Compra de Acervo":
            st.markdown("---")
            st.info("📦 **Atualização de Estoque:** Preencha abaixo para cadastrar o item comprado.")
            # Agora fora do form, esta mudança de radio dispara um rerun e atualiza o IF abaixo
            modo_item = st.radio("Este item já existe no sistema?",
                                    ["Sim, aumentar estoque", "Não, é um item novo"], horizontal=True)

            if modo_item == "Sim, aumentar estoque":
                c_i1, c_i2 = st.columns([2, 1])
                item_nome = c_i1.selectbox("Selecione o Item", list(acervo_dict.keys()))
                qtd_compra = c_i2.number_input("Qtd Comprada", min_value=1, value=1)
            else:
                is_new_item = True
                c_n1, c_n2 = st.columns([2, 1])
                item_nome = c_n1.text_input("Nome do Novo Item")
                qtd_compra = c_n2.number_input("Qtd Comprada", min_value=1, value=1)
                custo_locacao = st.number_input("Preço de Aluguel Sugerido (R$)", min_value=0.0, value=30.0)

            c_l1, c_l2 = st.columns(2)
            loja_compra = c_l1.text_input("Loja/Fornecedor")
            link_compra = c_l2.text_input("Link do Produto (Opcional)")
            update_stock = True

        # Trocado st.form_submit_button por st.button normal (type primary para destaque)
        submitted = st.button("💾 Confirmar Lançamento", type="primary")

        if submitted:
            if val <= 0:
                st.error("O valor deve ser maior que zero.")
            elif update_stock and is_new_item and not item_nome:
                st.error("Preencha o nome do novo item.")
            else:
                novo_id = int(time.time())
                descricao_final = desc_input
                transacao = {
                    "id": novo_id, "data": str(f_data), "tipo": f_tipo, "categoria": f_cat,
                    "descricao": descricao_final, "valor": val, "quem": quem, "forma_pagto": forma,
                    "status": "Pago" if f_tipo == "Despesa" else "Recebido",
                    "loja": loja_compra, "link": link_compra
                }
                dados_estoque = None
                if update_stock:
                    dados_estoque = {
                        "item": item_nome, "qtd": qtd_compra,
                        "custo": val / qtd_compra if qtd_compra > 0 else val,
                        "loja": loja_compra, "link": link_compra,
                        "is_new": is_new_item,
                        "preco_locacao": custo_locacao
                    }
                with st.spinner("Salvando..."):
                    GoogleSheetsService.registrar_transacao(transacao, dados_estoque)
                    st.cache_data.clear()
                    st.success("Lançamento salvo!")
                    time.sleep(1)
                    st.rerun()

    with tab_dash:
        st.subheader("Extrato")
        df_fin = GoogleSheetsService.get_dataframe("Financeiro")
        if not df_fin.empty:
            df_fin['Valor'] = pd.to_numeric(df_fin['Valor'], errors='coerce').fillna(0.0)
            receitas = df_fin[df_fin['Tipo'] == 'Receita']['Valor'].sum()
            despesas = df_fin[df_fin['Tipo'] == 'Despesa']['Valor'].sum()
            lucro = receitas - despesas
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Receitas", f"R$ {receitas:.2f}")
            m2.metric("Total Despesas", f"R$ {despesas:.2f}")
            m3.metric("Lucro Líquido", f"R$ {lucro:.2f}", delta_color="normal")
            st.dataframe(df_fin, width='stretch')
        else:
            st.info("Nenhum lançamento encontrado.")


def render_area_contrato(dados_cli, dados_evt, itens, total, sinal, restante):
    st.header("📝 Contrato e Documentação")
    with st.expander("Gerenciar Contrato (Baixar ou Enviar)"):
        st.info("Janela de horários:")
        c1, c2, c3 = st.columns([2, 1, 1])
        d_ret = c1.date_input("Retirada", value=datetime.datetime.strptime(dados_evt['data'], '%Y-%m-%d').date())
        h_ret_i = c2.time_input("Das", value=datetime.time(10, 0))
        h_ret_f = c3.time_input("Até", value=datetime.time(11, 0))

        c4, c5, c6 = st.columns([2, 1, 1])
        d_dev = c4.date_input("Devolução", value=datetime.datetime.strptime(dados_evt['data'],
                                                                            '%Y-%m-%d').date() + datetime.timedelta(
            days=1))
        h_dev_i = c5.time_input("Das ", value=datetime.time(8, 0))
        h_dev_f = c6.time_input("Até ", value=datetime.time(10, 0))

        txt_ret = f"{d_ret.strftime('%d/%m/%Y')} entre {h_ret_i.strftime('%H:%M')} e {h_ret_f.strftime('%H:%M')}"
        txt_dev = f"{d_dev.strftime('%d/%m/%Y')} entre {h_dev_i.strftime('%H:%M')} e {h_dev_f.strftime('%H:%M')}"

        st.markdown("---")
        b_down, b_send = st.columns(2)

        with b_down:
            if st.button("📄 Gerar PDF Local"):
                if not dados_cli['nome']:
                    st.error("Nome obrigatório")
                else:
                    f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret, txt_dev)
                    with open(f_path, "rb") as f:
                        st.download_button("💾 Baixar PDF", f, file_name=f_path)
                    os.remove(f_path)

        with b_send:
            email = st.text_input("E-mail do Cliente:")
            if st.button("📧 Enviar via Autentique"):
                if not email or not dados_cli['nome']:
                    st.error("Preencha e-mail e nome.")
                else:
                    with st.spinner("Enviando..."):
                        f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret,
                                                    txt_dev)
                        ok, res = EmailService.enviar_contrato(f_path, email)
                        if ok:
                            st.success("Enviado!" if res == "EMAIL_ENVIADO" else "Enviado! Link gerado.")
                            if "http" in res: st.code(res)
                            if os.path.exists(f_path): os.remove(f_path)
                        else:
                            st.error(res)


def render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict):
    bloqueado = False
    status_atual = "Novo"

    if st.session_state['edit_id']:
        orc_atual = next(
            (x for x in st.session_state['db_orcamentos'] if str(x['id']) == str(st.session_state['edit_id'])), None)
        if orc_atual:
            status_atual = orc_atual['status']
            if status_atual not in ["Aguardando", "Novo"]:
                bloqueado = True
                st.warning(f"🔒 Este orçamento está **{status_atual.upper()}** e não pode ser editado.")
            else:
                st.info(f"✏️ Editando orçamento #{st.session_state['edit_id']} (Status: {status_atual})")

        c1, c2 = st.columns(2)
        c1.button("🔙 Voltar ao Histórico",
                  on_click=lambda: (setattr(st.session_state, 'edit_id', None), reset_form_state(),
                                    setattr(st.session_state, 'navegacao_atual', "📂 Histórico de Orçamentos")),
                  use_container_width=True)

        def _duplicar():
            st.session_state['edit_id'] = None
            st.session_state['feedback_msg'] = ("success", "Dados copiados para novo orçamento.")

        c2.button("📑 Usar como base (Duplicar)", on_click=_duplicar, use_container_width=True)
        st.markdown("---")

    # --- FUNÇÕES DE CALLBACK ---
    def _buscar_cep_cli():
        cep = st.session_state.get("in_cli_cep", "")
        res = CepService.consultar(cep)
        if res:
            st.session_state["in_cli_rua"] = res.get("logradouro", "")
            st.session_state["in_cli_bairro"] = res.get("bairro", "")
            st.session_state["in_cli_cidade"] = res.get("localidade", "")
            st.toast("Endereço do cliente encontrado!", icon="📍")
        elif cep:
            st.toast("CEP não encontrado ou inválido.", icon="⚠️")

    def _buscar_cep_evt():
        cep = st.session_state.get("in_evt_cep", "")
        res = CepService.consultar(cep)
        if res:
            st.session_state["in_evt_rua"] = res.get("logradouro", "")
            st.session_state["in_evt_bairro"] = res.get("bairro", "")
            st.session_state["in_evt_cidade"] = res.get("localidade", "")
            st.toast("Endereço do evento encontrado!", icon="📍")
        elif cep:
            st.toast("CEP não encontrado ou inválido.", icon="⚠️")

    def _copiar_endereco():
        if st.session_state.get("chk_mesmo_end"):
            st.session_state["in_evt_cep"] = st.session_state.get("in_cli_cep", "")
            st.session_state["in_evt_rua"] = st.session_state.get("in_cli_rua", "")
            st.session_state["in_evt_num"] = st.session_state.get("in_cli_num", "")
            st.session_state["in_evt_bairro"] = st.session_state.get("in_cli_bairro", "")
            st.session_state["in_evt_cidade"] = st.session_state.get("in_cli_cidade", "")

    st.subheader("👤 Dados do Cliente")
    col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
    nome = col_c1.text_input("Nome Completo", key="in_nome", disabled=bloqueado)
    cpf = col_c2.text_input("CPF", key="in_cpf", disabled=bloqueado)
    celular = col_c3.text_input("WhatsApp (com DDD)", key="in_telefone", disabled=bloqueado)

    col_ce1, col_ce2, col_ce3, col_ce4, col_ce5 = st.columns([1, 2, 1, 1.5, 1.5])
    cep_cli = col_ce1.text_input("CEP Cli.", key="in_cli_cep", on_change=_buscar_cep_cli, disabled=bloqueado)
    rua_cli = col_ce2.text_input("Rua", key="in_cli_rua", disabled=bloqueado)
    num_cli = col_ce3.text_input("Nº", key="in_cli_num", disabled=bloqueado)
    bairro_cli = col_ce4.text_input("Bairro", key="in_cli_bairro", disabled=bloqueado)
    cid_cli = col_ce5.text_input("Cidade", key="in_cli_cidade", disabled=bloqueado)

    st.subheader("📍 Local do Evento")
    col_ev0, col_ev_dup = st.columns([2, 1])
    data_evt = col_ev0.date_input("Data do Evento", value=date.today(), key="in_data", disabled=bloqueado)
    usar_mesmo_end = col_ev_dup.checkbox("🏠 Mesmo endereço do cliente?", key="chk_mesmo_end",
                                         on_change=_copiar_endereco, disabled=bloqueado)

    col_ev1, col_ev2, col_ev3, col_ev4, col_ev5 = st.columns([1, 2, 1, 1.5, 1.5])
    cep_evt = col_ev1.text_input("CEP Evt.", key="in_evt_cep", on_change=_buscar_cep_evt, disabled=bloqueado)
    rua_evt = col_ev2.text_input("Rua", key="in_evt_rua", disabled=bloqueado)
    num_evt = col_ev3.text_input("Nº", key="in_evt_num", disabled=bloqueado)
    bairro_evt = col_ev4.text_input("Bairro", key="in_evt_bairro", disabled=bloqueado)
    cid_evt = col_ev5.text_input("Cidade", key="in_evt_cidade", disabled=bloqueado)

    st.markdown("---")

    c_tm1, c_tm2 = st.columns(2)
    cat_sel = c_tm1.selectbox("Tipo de Festa", list(categorias.keys()) if categorias else ["Vazio"], key="in_categoria",
                              disabled=bloqueado)
    tema_sel = c_tm2.selectbox("Qual o Tema?", categorias.get(cat_sel, ["Vazio"]), key="in_tema", disabled=bloqueado)

    st.subheader("Composição do Kit")
    opcoes_kits = list(kits.keys())
    opcao_custom = "Montar Personalizado (Do Zero)"
    if opcao_custom not in opcoes_kits:
        opcoes_kits.append(opcao_custom)

    nivel = st.radio("Selecione o Nível do Kit:", opcoes_kits, horizontal=True, key="in_kit", disabled=bloqueado)

    itens_pers, itens_desc, preco_base = [], [], 0.0

    if nivel == "Montar Personalizado (Do Zero)":
        st.markdown("### 🛠️ Monte o Kit Item por Item:")
        itens_pers = st.multiselect("Acervo Completo:", list(acervo.keys()), key="in_itens_pers", disabled=bloqueado)
        preco_base = sum(acervo.get(i, 0) for i in itens_pers)
        itens_desc = itens_pers
    else:
        dados_kit = kits.get(nivel, {"preco": 0.0, "descricao": ["Kit não encontrado"]})
        preco_base, itens_desc = dados_kit["preco"], dados_kit["descricao"]
        st.info(f"📦 **Itens inclusos no {nivel}:**")
        for i in itens_desc: st.markdown(f"- {i}")
        st.markdown("---")

    itens_add = st.multiselect("Selecione itens avulsos:", list(acervo.keys()), key="in_itens_add",
                               disabled=bloqueado) if nivel != "Montar Personalizado (Do Zero)" else []
    val_add = sum(acervo.get(i, 0) for i in itens_add)

    if not bloqueado:
        itens_verificar = itens_pers + itens_add
        avisos_estoque = []
        for it in itens_verificar:
            qtd_total = estoque_dict.get(it, 0)
            usados_dia, saldo = InventoryService.verificar_disponibilidade(
                it, str(data_evt), qtd_total, st.session_state['db_orcamentos']
            )
            if st.session_state['edit_id']:
                saldo += 1
            if saldo <= 0:
                avisos_estoque.append(
                    f"⚠️ **{it}:** Você tem {qtd_total}, mas {usados_dia} já estão alugados neste dia.")
        if avisos_estoque:
            st.warning("🚨 **ALERTA DE ESTOQUE (Overbooking):**\n" + "\n".join(avisos_estoque))

    obs_alt = ""
    if nivel != "Montar Personalizado (Do Zero)" and st.checkbox("🔄 Houve troca de itens?", key="in_check_obs",
                                                                 disabled=bloqueado):
        obs_alt = st.text_input("Descreva a alteração:", key="in_obs", disabled=bloqueado)

    st.subheader("3. Logística e Serviços")
    frete, mao_obra, dist, horas = 0.0, 0.0, 0.0, 0.0
    tipo_entrega = st.radio("Logística:", ["Pegue e Monte", "Nós Levamos e Montamos"], key="in_entrega",
                            disabled=bloqueado)

    if tipo_entrega == "Nós Levamos e Montamos":
        c1, c2 = st.columns(2)
        dist = c1.number_input("Distância Ida (KM)", value=5.0, key="in_dist", disabled=bloqueado)
        horas = c2.number_input("Horas Totais", value=3.0, key="in_horas", disabled=bloqueado)
        frete = (dist * 4) * st.session_state['cfg_km']
        mao_obra = horas * st.session_state['cfg_hora']

    custo_baloes, desc_balao = 0.0, ""
    if st.checkbox("Adicionar Balões?", key="in_check_balao", disabled=bloqueado):
        tipo_b = st.selectbox("Tipo", ["Arco Simples", "Orgânico", "Orgânico Premium"], key="in_tipo_balao",
                              disabled=bloqueado)
        metros = st.slider("Metros", 2.0, 5.0, 2.5, key="in_metros", disabled=bloqueado)
        custo_baloes = metros * {"Arco Simples": 40, "Orgânico": 80, "Orgânico Premium": 120}[tipo_b]
        desc_balao = f"Arte com Balões: {tipo_b} ({metros}m)"

    st.subheader("4. Fechamento e Valores")
    taxa_hig = st.session_state['cfg_taxa']
    bruto = preco_base + val_add + frete + mao_obra + custo_baloes + taxa_hig

    c_d1, c_d2 = st.columns([1, 3])
    perc_desc = c_d1.number_input("Aplicar Desconto (%)", 0.0, 100.0, 0.0, step=1.0, key="in_desc_perc",
                                  disabled=bloqueado)
    val_desc = bruto * (perc_desc / 100)
    liquido = bruto - val_desc
    sinal, restante = liquido * 0.30, liquido * 0.70

    txt_itens = f"- KIT PERSONALIZADO:\n" if nivel == "Montar Personalizado (Do Zero)" else f"- ESTRUTURA {nivel.upper()}:\n"
    for i in itens_desc: txt_itens += f"  • {i}\n"
    if obs_alt: txt_itens += f"⚠️ OBS: {obs_alt}\n"
    if itens_add:
        txt_itens += "\n- ITENS ADICIONAIS:\n"
        for i in itens_add: txt_itens += f"  • {i}\n"

    texto_whats = f"""
*ORÇAMENTO NT FESTAS* 🎈
Olá *{nome}*! Segue o orçamento para o tema *{tema_sel}*.
📅 Data: {data_evt}
📍 Local: {rua_evt}, {num_evt} - {cid_evt}

*COMPOSIÇÃO:*
{detalhes.get(tema_sel, f"Tema: {tema_sel}")}
{txt_itens}
{f"- {desc_balao}" if custo_baloes > 0 else ""}

*SERVIÇOS:*
- Higienização e Embalagem
{f"- Frete e Logística" if frete > 0 else "- Cliente retira e devolve (Pegue e Monte)"}
{f"- Montagem Profissional" if mao_obra > 0 else ""}

-----------------------------
*VALOR TOTAL: R$ {liquido:.2f}*
{f"🎁 Desconto: - R$ {val_desc:.2f}" if val_desc > 0 else ""}
-----------------------------
💰 *PAGAMENTO:*
✅ Sinal (30%): R$ {sinal:.2f}
✅ Restante: R$ {restante:.2f}
"""

    c_res1, c_res2 = st.columns([3, 2])
    with c_res1:
        st.subheader("📲 Mensagem WhatsApp")
        st.code(texto_whats)

        if celular:
            nums = "".join([c for c in celular if c.isdigit()])
            msg_encoded = urllib.parse.quote(texto_whats)
            link_zap = f"https://api.whatsapp.com/send?phone=55{nums}&text={msg_encoded}"
            st.link_button("🚀 Enviar no WhatsApp", link_zap, type="secondary")
        else:
            st.warning("Preencha o WhatsApp do cliente para habilitar o envio.")

        if not bloqueado:
            def _salvar():
                if not nome:
                    st.session_state['feedback_msg'] = ("error", "Preencha o nome do cliente.")
                    return

                novo_id = int(time.time())
                orcamento = {
                    "id": st.session_state['edit_id'] or novo_id,
                    "data_registro": str(datetime.date.today()),
                    "status": "Aguardando" if not st.session_state['edit_id'] else status_atual,
                    "cliente": nome,
                    "data_evento": str(data_evt),
                    "cidade": cid_evt,
                    "tema": tema_sel,
                    "total": liquido,
                    "dados_form": {k: st.session_state[k] for k in st.session_state if
                                   k.startswith('in_') or k == 'in_data'}
                }

                with st.spinner("Salvando na nuvem..."):
                    GoogleSheetsService.upsert_orcamento(orcamento)

                db = st.session_state['db_orcamentos']
                if st.session_state['edit_id']:
                    db = [orcamento if str(o['id']) == str(orcamento['id']) else o for o in db]
                    msg = "Orçamento atualizado!"
                else:
                    db.append(orcamento)
                    msg = "Novo orçamento criado!"

                st.session_state['db_orcamentos'] = db
                st.session_state['feedback_msg'] = ("success", msg)
                st.session_state['edit_id'] = None
                reset_form_state()

            st.button("💾 SALVAR ORÇAMENTO NO SISTEMA", type="primary", on_click=_salvar)

    with c_res2:
        st.subheader("📋 Demonstrativo")
        with st.container(border=True):
            st.caption("📦 ITENS E KITS")

            def linha_resumo(texto, valor, destaque=False):
                c1, c2 = st.columns([3, 1])
                c1.write(texto)
                if destaque:
                    c2.markdown(f"**R$ {valor:.2f}**")
                else:
                    c2.write(f"R$ {valor:.2f}")

            linha_resumo("Base do Kit", preco_base)
            if val_add: linha_resumo("Itens Extras", val_add)
            if custo_baloes: linha_resumo("Balões", custo_baloes)
            st.markdown("---")
            st.caption("🛠️ TAXAS E SERVIÇOS")
            cs1, cs2, cs3 = st.columns(3)
            cs1.markdown(f"<small>Higienização</small><br>**R$ {taxa_hig:.2f}**", unsafe_allow_html=True)
            cs2.markdown(f"<small>Frete</small><br>**R$ {frete:.2f}**", unsafe_allow_html=True)
            cs3.markdown(f"<small>Montagem</small><br>**R$ {mao_obra:.2f}**", unsafe_allow_html=True)
            st.markdown("---")
            c_tot1, c_tot2 = st.columns([3, 2])
            c_tot1.write("Subtotal:")
            c_tot2.write(f"**R$ {bruto:.2f}**")
            if val_desc:
                c_tot1.write("Desconto:")
                c_tot2.markdown(f":red[- R$ {val_desc:.2f}]")
            st.write("")
            st.success(f"### TOTAL: R$ {liquido:.2f}")

    st.markdown("---")
    dados_cli_pdf = {"nome": nome, "cpf": cpf, "cep": cep_cli, "rua": rua_cli, "numero": num_cli, "bairro": bairro_cli,
                     "cidade": cid_cli}
    dados_evt_pdf = {"data": str(data_evt), "cep": cep_evt, "rua": rua_evt, "numero": num_evt, "bairro": bairro_evt,
                     "cidade": cid_evt}
    render_area_contrato(dados_cli_pdf, dados_evt_pdf, txt_itens, liquido, sinal, restante)


# --- DIALOG PARA GERENCIAR STATUS (FASE 4) ---
@st.dialog("Gerenciar Status")
def dialog_gerenciar_status(orcamento):
    st.write(f"Alterar status de: **{orcamento['cliente']}**")
    st.caption(f"Status Atual: {orcamento['status']}")

    novo_status = st.selectbox("Novo Status",
                               ["Aguardando", "Reserva Confirmada", "Evento Realizado", "Finalizado", "Cancelado",
                                "Reprovado"],
                               index=["Aguardando", "Reserva Confirmada", "Evento Realizado", "Finalizado", "Cancelado",
                                      "Reprovado"].index(orcamento['status']) if orcamento['status'] in ["Aguardando",
                                                                                                         "Reserva Confirmada",
                                                                                                         "Evento Realizado",
                                                                                                         "Finalizado",
                                                                                                         "Cancelado",
                                                                                                         "Reprovado"] else 0
                               )

    # Calcular Valores Estimados
    total = orcamento.get('total', 0)
    sinal_estimado = total * 0.30
    restante_estimado = total * 0.70

    financeiro_payload = None

    if novo_status == "Reserva Confirmada":
        st.info("💰 Esta ação irá gerar uma entrada de SINAL no financeiro.")
        val_sinal = st.number_input("Valor do Sinal Recebido (R$)", value=sinal_estimado)
        data_pagto = st.date_input("Data do Pagamento", value=date.today())
        forma = st.selectbox("Forma", ["Pix", "Cartão", "Dinheiro"])

        if st.button("Confirmar Reserva"):
            financeiro_payload = {
                "id": int(time.time()), "data": str(data_pagto), "tipo": "Receita",
                "categoria": "Sinal de Reserva", "descricao": f"Sinal ref. {orcamento['cliente']} (#{orcamento['id']})",
                "valor": val_sinal, "quem": "NT Festas", "forma_pagto": forma, "status": "Recebido"
            }

    elif novo_status == "Finalizado":
        st.info("💰 Esta ação irá gerar uma entrada do RESTANTE no financeiro.")
        val_rest = st.number_input("Valor Recebido (R$)", value=restante_estimado)
        data_pagto = st.date_input("Data da Quitação", value=date.today())
        forma = st.selectbox("Forma", ["Pix", "Cartão", "Dinheiro"])

        if st.button("Confirmar Quitação"):
            financeiro_payload = {
                "id": int(time.time()), "data": str(data_pagto), "tipo": "Receita",
                "categoria": "Restante Pagamento",
                "descricao": f"Quitação ref. {orcamento['cliente']} (#{orcamento['id']})",
                "valor": val_rest, "quem": "NT Festas", "forma_pagto": forma, "status": "Recebido"
            }

    elif novo_status == "Cancelado":
        st.warning("⚠️ Cancelamento de Contrato")
        houve_reembolso = st.checkbox("Houve devolução de dinheiro ao cliente?")

        if houve_reembolso:
            val_dev = st.number_input("Valor Devolvido (R$)", min_value=0.0)
            if st.button("Confirmar Cancelamento com Devolução"):
                financeiro_payload = {
                    "id": int(time.time()), "data": str(date.today()), "tipo": "Despesa",
                    "categoria": "Outros", "descricao": f"Reembolso Cancelamento - {orcamento['cliente']}",
                    "valor": val_dev, "quem": "NT Festas", "forma_pagto": "Pix", "status": "Pago"
                }
        else:
            if st.button("Confirmar Cancelamento (Sem Devolução)"):
                financeiro_payload = "SKIP"  # Marcador para apenas mudar status

    else:
        # Reprovado, Aguardando, Evento Realizado (Sem financeiro automático)
        if st.button("Atualizar Status"):
            financeiro_payload = "SKIP"

    # Lógica de Salvamento
    if financeiro_payload:
        # 1. Salva Financeiro (se não for SKIP)
        if financeiro_payload != "SKIP":
            with st.spinner("Lançando no Financeiro..."):
                GoogleSheetsService.registrar_transacao(financeiro_payload)

        # 2. Atualiza Status
        with st.spinner("Atualizando Orçamento..."):
            orcamento['status'] = novo_status
            GoogleSheetsService.upsert_orcamento(orcamento)

            # Atualiza estado local
            st.session_state['db_orcamentos'] = [
                orcamento if o['id'] == orcamento['id'] else o
                for o in st.session_state['db_orcamentos']
            ]
            st.rerun()


def render_historico():
    st.header("Histórico")
    db = st.session_state['db_orcamentos']

    if not db:
        st.info("Nenhum orçamento.")
        return

    c_f1, c_f2 = st.columns(2)
    busca = c_f1.text_input("🔍 Buscar Cliente")
    filtro_st = c_f2.multiselect("Status",
                                 ["Aguardando", "Reserva Confirmada", "Evento Realizado", "Finalizado", "Cancelado",
                                  "Reprovado"])

    lista = sorted(db, key=lambda x: str(x['id']), reverse=True)
    if busca: lista = [x for x in lista if busca.lower() in x['cliente'].lower()]
    if filtro_st: lista = [x for x in lista if x['status'] in filtro_st]

    for orc in lista:
        with st.container():
            status = orc['status']

            # Cores dinâmicas para novos status
            mapa_cores = {
                "Aguardando": "🟡",
                "Reserva Confirmada": "🔵",
                "Evento Realizado": "🟣",
                "Finalizado": "🟢",
                "Cancelado": "🔴",
                "Reprovado": "⚫"
            }
            cor = mapa_cores.get(status, "⚪")

            c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
            c1.markdown(f"**#{orc['id']} - {orc['cliente']}**")
            c1.caption(f"{orc['data_evento']} | {orc.get('tema', 'N/A')}")
            c2.write(f"R$ {orc.get('total', 0):.2f}")
            c3.markdown(f"{cor} **{status}**")

            bts = c4.columns([1, 1, 1])

            def _carregar(oid=orc['id'], dados=orc['dados_form']):
                st.session_state['edit_id'] = oid
                for k, v in dados.items():
                    if k == 'in_data':
                        try:
                            v = datetime.datetime.strptime(v, '%Y-%m-%d').date()
                        except:
                            pass
                    st.session_state[k] = v
                st.session_state['navegacao_atual'] = "📝 Novo Orçamento"

            # Botão Editar
            bts[0].button("✏️" if status in ["Aguardando", "Novo"] else "👁️", key=f"e_{orc['id']}", on_click=_carregar)

            # Botão Gerenciar Status (Substitui os antigos ✅ ❌)
            if bts[1].button("🔄", key=f"st_{orc['id']}", help="Gerenciar Status"):
                dialog_gerenciar_status(orc)

            st.markdown("---")


# ==========================================
# MAIN APP LOOP
# ==========================================

def main():
    init_session_state()
    acervo, categorias, kits, detalhes, estoque_dict = GoogleSheetsService.carregar_catalogo()
    handle_feedback()

    render_sidebar()

    opcoes_menu = ["📝 Novo Orçamento", "📂 Histórico de Orçamentos", "💰 Financeiro", "⚙️ Gestão de Acervo"]
    nav = st.radio("Menu", opcoes_menu, horizontal=True, key="navegacao_atual", label_visibility="collapsed")
    st.divider()

    if nav == "📝 Novo Orçamento":
        render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict)
    elif nav == "📂 Histórico de Orçamentos":
        render_historico()
    elif nav == "💰 Financeiro":
        render_financeiro(acervo)
    elif nav == "⚙️ Gestão de Acervo":
        render_gestao()


if __name__ == "__main__":
    main()