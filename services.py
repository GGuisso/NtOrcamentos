import streamlit as st
import requests
import json
import pandas as pd
import time
from datetime import datetime, date, time as dt_time
from supabase import create_client, Client, ClientOptions
from typing import Tuple, Dict, List, Any, Optional
from fpdf import FPDF

# ==========================================
# CONFIGURAÇÃO E SEGREDOS
# ==========================================
VIACEP_URL = "https://viacep.com.br/ws/{}/json/"
AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"

# ID DA EMPRESA (TENANT)
TENANT_ID = "nt_festas_01"


def get_secret(key_name):
    """Busca segura de chaves no secrets.toml."""
    if key_name in st.secrets:
        return st.secrets[key_name]
    if "GCP_SERVICE_ACCOUNT" in st.secrets and key_name in st.secrets["GCP_SERVICE_ACCOUNT"]:
        return st.secrets["GCP_SERVICE_ACCOUNT"][key_name]
    return ""


SUPA_URL = get_secret("SUPABASE_URL")
SUPA_KEY = get_secret("SUPABASE_KEY")


# ==========================================
# CAMADA DE SERVIÇOS (BACKEND)
# ==========================================

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


class SupabaseService:
    @staticmethod
    @st.cache_resource
    def get_client() -> Client:
        if not SUPA_URL or not SUPA_KEY:
            st.error("⚠️ Configure SUPABASE_URL e SUPABASE_KEY no secrets.toml")
            st.stop()

        options = ClientOptions(
            postgrest_client_timeout=30,
            storage_client_timeout=30,
            schema="public",
        )
        return create_client(SUPA_URL, SUPA_KEY, options=options)

    # ------------------------------------------------------------------
    # 0. BUSCA DE CLIENTES (NOVO)
    # ------------------------------------------------------------------
    @staticmethod
    def buscar_clientes(termo: str, por_cpf: bool = False) -> List[Dict]:
        """
        Busca clientes por CPF exato ou Nome parcial (ilike).
        """
        supabase = SupabaseService.get_client()
        termo = termo.strip()
        if not termo: return []

        try:
            query = supabase.table("clientes").select("*")

            if por_cpf:
                # Remove pontuação se houver, busca exata
                cpf_limpo = "".join([c for c in termo if c.isdigit()])
                if not cpf_limpo: return []
                res = query.eq("cpf", cpf_limpo).execute()
            else:
                # Busca parcial por nome (case insensitive)
                res = query.ilike("nome", f"%{termo}%").execute()

            return res.data
        except Exception as e:
            print(f"Erro busca cliente: {e}")
            return []

    # ------------------------------------------------------------------
    # 1. GESTÃO DE ARQUIVOS
    # ------------------------------------------------------------------
    @staticmethod
    def upload_imagem(file_obj, nome_arquivo_original: str) -> Optional[str]:
        try:
            supabase = SupabaseService.get_client()
            nome_limpo = "".join(
                [c for c in nome_arquivo_original if c.isalnum() or c in (' ', '_', '.', '-')]).replace(" ", "_")
            path = f"{TENANT_ID}/{int(time.time())}_{nome_limpo}"

            file_bytes = file_obj.getvalue()
            supabase.storage.from_("acervo").upload(
                path=path, file=file_bytes, file_options={"content-type": file_obj.type, "upsert": "false"}
            )
            return supabase.storage.from_("acervo").get_public_url(path)
        except Exception as e:
            print(f"Erro Upload: {e}")
            return None

    # ------------------------------------------------------------------
    # 2. LEITURA DE DADOS
    # ------------------------------------------------------------------
    @staticmethod
    def carregar_catalogo() -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        supabase = SupabaseService.get_client()

        # A. Acervo
        res_acervo = supabase.table("acervo").select("*").eq("ativo", True).execute()
        acervo_dict = {}
        estoque_dict = {}
        for item in res_acervo.data:
            acervo_dict[item['nome']] = float(item['preco_aluguel'])
            estoque_dict[item['nome']] = int(item['quantidade_total'])

        # B. Temas
        res_temas = supabase.table("temas").select("*").execute()
        categorias = {}
        detalhes = {}
        for t in res_temas.data:
            cat = t['categoria']
            tema_nome = t['nome']
            if cat not in categorias: categorias[cat] = []
            categorias[cat].append(tema_nome)
            detalhes[tema_nome] = t['detalhes'] or ""

        # C. Kits
        res_kits = supabase.table("kits").select("*").execute()
        kits_dict = {}
        for k in res_kits.data:
            items_desc = [x.strip() for x in str(k.get('descricao_comercial', '')).split(';') if x.strip()]
            kits_dict[k['nome']] = {
                "id": k['id'],
                "preco": float(k['preco_sugerido']),
                "descricao": items_desc
            }

        return acervo_dict, categorias, kits_dict, detalhes, estoque_dict

    @staticmethod
    def carregar_orcamentos() -> List[Dict]:
        supabase = SupabaseService.get_client()

        # JOIN para trazer os itens reais (orcamento_itens -> acervo)
        res = supabase.table("orcamentos").select(
            "*, clientes(nome), orcamento_itens(quantidade, acervo(nome))"
        ).execute()

        lista_final = []
        for row in res.data:
            dados_form = row.get('dados_form_snapshot') or {}
            tema_salvo = dados_form.get('in_tema', row.get('tema', '?'))

            # Processa itens reais do banco para cálculo de estoque
            lista_itens_reais = []
            if row.get('orcamento_itens'):
                for oi in row['orcamento_itens']:
                    if oi.get('acervo') and oi.get('quantidade'):
                        nome_item = oi['acervo']['nome']
                        qtd = oi['quantidade']
                        # Adiciona N vezes à lista para facilitar contagem simples no InventoryService
                        lista_itens_reais.extend([nome_item] * qtd)

            orcamento_obj = {
                "id": row['id'],
                "cliente": row['clientes']['nome'] if row['clientes'] else "Desconhecido",
                "data_evento": row['data_evento'],
                "status": row['status'],
                "total": float(row['valor_total'] or 0.0),
                "tema": tema_salvo,
                "dados_form": dados_form,
                "itens_reais_db": lista_itens_reais
            }
            lista_final.append(orcamento_obj)
        return lista_final

    @staticmethod
    def get_dataframe(tabela_virtual: str) -> pd.DataFrame:
        supabase = SupabaseService.get_client()

        if tabela_virtual == "Itens":
            res = supabase.table("acervo").select("*").order("nome").execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df.rename(columns={
                    "nome": "Item", "foto_url": "Imagem", "preco_aluguel": "Preco",
                    "quantidade_total": "Qtd_Estoque", "custo_aquisicao": "Custo_Unitario",
                    "link_reposicao": "Link_Referencia", "tipo": "Tipo"
                }, inplace=True)
                if "Tipo" not in df.columns: df["Tipo"] = "Acervo"
                df["Tipo"] = df["Tipo"].fillna("Acervo")
            return df

        elif tabela_virtual == "Kits":
            res = supabase.table("kits").select("*").execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df.rename(columns={
                    "nome": "Nome", "preco_sugerido": "Preco", "descricao_comercial": "Descricao"
                }, inplace=True)
            return df

        elif tabela_virtual == "Temas":
            res = supabase.table("temas").select("*").execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df.rename(columns={
                    "nome": "Tema", "categoria": "Categoria", "detalhes": "Detalhes"
                }, inplace=True)
            return df

        elif tabela_virtual == "Financeiro":
            res = supabase.table("financeiro").select("*").order("created_at", desc=True).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                col_map = {
                    "descricao": "Descrição", "tipo": "Tipo", "categoria": "Categoria",
                    "valor": "Valor", "data_pagamento": "Data", "quem_pagou_recebeu": "Quem",
                    "forma_pagamento": "Forma Pagto"
                }
                df.rename(columns=col_map, inplace=True)
            return df

        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 3. GRAVAÇÃO (UPSERT INTELIGENTE COM RELACIONAMENTOS)
    # ------------------------------------------------------------------
    @staticmethod
    def upsert_orcamento(orcamento: Dict):
        supabase = SupabaseService.get_client()
        dados_form = orcamento.get('dados_form', {})

        # Sanitiza Datas do form
        dados_form_serializable = {}
        for k, v in dados_form.items():
            if isinstance(v, (date, datetime, dt_time)):
                dados_form_serializable[k] = str(v)
            else:
                dados_form_serializable[k] = v

        # A. Cliente - INCLUINDO EMAIL E DATA NASCIMENTO
        cli_nome = dados_form.get('in_nome')
        cli_cpf = dados_form.get('in_cpf')

        # Tratamento da data de nascimento para string (Postgres Date)
        nasc = dados_form.get('in_nascimento')
        if isinstance(nasc, (date, datetime)):
            nasc = str(nasc)
        else:
            nasc = None

        cliente_payload = {
            "nome": cli_nome,
            "cpf": cli_cpf if cli_cpf else None,
            "telefone": dados_form.get('in_telefone'),
            "email": dados_form.get('in_email'),
            "data_nascimento": nasc,
            "cep": dados_form.get('in_cli_cep'),
            "logradouro": dados_form.get('in_cli_rua'),
            "numero": dados_form.get('in_cli_num'),
            "bairro": dados_form.get('in_cli_bairro'),
            "cidade": dados_form.get('in_cli_cidade')
        }

        res_cli = supabase.table("clientes").select("id").eq("nome", cli_nome).execute()
        if res_cli.data:
            cliente_id = res_cli.data[0]['id']
            # Atualiza o cliente existente
            supabase.table("clientes").update(cliente_payload).eq("id", cliente_id).execute()
        else:
            # Cria novo cliente
            res_new_cli = supabase.table("clientes").insert(cliente_payload).execute()
            cliente_id = res_new_cli.data[0]['id']

        # B. Orçamento Header
        orc_payload = {
            "cliente_id": cliente_id,
            "data_evento": str(orcamento['data_evento']),
            "status": orcamento['status'],
            "logistica_tipo": dados_form.get('in_entrega', 'Pegue e Monte'),
            "endereco_evento_rua": dados_form.get('in_evt_rua'),
            "endereco_evento_numero": dados_form.get('in_evt_num'),
            "endereco_evento_bairro": dados_form.get('in_evt_bairro'),
            "endereco_evento_cidade": dados_form.get('in_evt_cidade'),
            "valor_total": orcamento['total'],
            "valor_itens": orcamento.get('valor_itens', 0),
            "valor_servicos": orcamento.get('valor_servicos', 0),
            "valor_desconto": orcamento.get('valor_desconto', 0),
            "dados_form_snapshot": dados_form_serializable
        }

        orc_id = orcamento.get('id')
        if orc_id and isinstance(orc_id, int) and orc_id < 1000000000:
            res_orc = supabase.table("orcamentos").update(orc_payload).eq("id", orc_id).execute()
            final_orc_id = orc_id
        else:
            res_orc = supabase.table("orcamentos").insert(orc_payload).execute()
            final_orc_id = res_orc.data[0]['id']
            orcamento['id'] = final_orc_id

        # C. Salvar Itens (Explode kit para itens reais)
        supabase.table("orcamento_itens").delete().eq("orcamento_id", final_orc_id).execute()

        # 1. Identificar se foi selecionado um KIT
        kit_selecionado_nome = dados_form.get('in_kit')
        kit_id_db = None
        itens_do_kit_map = {}  # {nome: quantidade}

        if kit_selecionado_nome and kit_selecionado_nome != "Montar Personalizado (Do Zero)":
            res_kit = supabase.table("kits").select("id").eq("nome", kit_selecionado_nome).execute()
            if res_kit.data:
                kit_id_db = res_kit.data[0]['id']
                # Busca composição: IDs e Qtds dos itens que compõem o kit
                res_comp = supabase.table("kit_itens").select("quantidade, acervo(nome)").eq("kit_id",
                                                                                             kit_id_db).execute()
                for comp in res_comp.data:
                    if comp['acervo']:
                        itens_do_kit_map[comp['acervo']['nome']] = comp['quantidade']

        # 2. Preparar lista consolidada de nomes de itens
        lista_base = dados_form.get('in_itens_pers', [])

        # Garante que itens do kit estejam na lista
        if kit_id_db:
            for nome_item_kit in itens_do_kit_map.keys():
                if nome_item_kit not in lista_base:
                    lista_base.append(nome_item_kit)

        lista_add = dados_form.get('in_itens_add', [])
        todos_itens_nomes = list(set(lista_base + lista_add))  # Remove duplicatas

        if todos_itens_nomes:
            # Busca todos os IDs e preços no acervo
            res_ids = supabase.table("acervo").select("id, nome, preco_aluguel").in_("nome",
                                                                                     todos_itens_nomes).execute()
            mapa_acervo = {i['nome']: i for i in res_ids.data}

            itens_insert = []

            # Processa Itens da Base (Kit ou Personalizado)
            for nome_item in lista_base:
                if nome_item in mapa_acervo:
                    dados_db = mapa_acervo[nome_item]

                    eh_do_kit = (kit_id_db is not None and nome_item in itens_do_kit_map)
                    origem_kit = kit_id_db if eh_do_kit else None
                    qtd = itens_do_kit_map[nome_item] if eh_do_kit else 1

                    itens_insert.append({
                        "orcamento_id": final_orc_id,
                        "item_acervo_id": dados_db['id'],
                        "quantidade": qtd,
                        "preco_unitario_cobrado": dados_db['preco_aluguel'],
                        "origem_kit_id": origem_kit
                    })

            # Processa Itens Adicionais (Sempre avulsos)
            for nome_item in lista_add:
                if nome_item in mapa_acervo:
                    dados_db = mapa_acervo[nome_item]
                    itens_insert.append({
                        "orcamento_id": final_orc_id,
                        "item_acervo_id": dados_db['id'],
                        "quantidade": 1,
                        "preco_unitario_cobrado": dados_db['preco_aluguel'],
                        "origem_kit_id": None
                    })

            if itens_insert:
                supabase.table("orcamento_itens").insert(itens_insert).execute()

    @staticmethod
    def salvar_dataframe(tabela_virtual: str, df: pd.DataFrame):
        supabase = SupabaseService.get_client()
        records = df.to_dict(orient="records")

        if tabela_virtual == "Itens":
            for row in records:
                tipo_valor = row.get('Tipo')
                if not tipo_valor or pd.isna(tipo_valor): tipo_valor = 'Acervo'
                try:
                    qtd = int(float(row.get('Qtd_Estoque', 1) or 1))
                except:
                    qtd = 1

                payload = {
                    "nome": row['Item'], "categoria": "Geral", "tipo": tipo_valor,
                    "preco_aluguel": row.get('Preco', 0), "quantidade_total": qtd,
                    "custo_aquisicao": row.get('Custo_Unitario', 0), "link_reposicao": row.get('Link_Referencia', ''),
                    "foto_url": row.get('Imagem', ''), "ativo": row.get('ativo', True)
                }
                if row.get('id') and pd.notna(row.get('id')):
                    supabase.table("acervo").update(payload).eq("id", int(row['id'])).execute()
                else:
                    res = supabase.table("acervo").select("id").eq("nome", row['Item']).execute()
                    if res.data:
                        supabase.table("acervo").update(payload).eq("id", res.data[0]['id']).execute()
                    else:
                        supabase.table("acervo").insert(payload).execute()

        elif tabela_virtual == "Kits":
            for row in records:
                kit_nome = row['Nome']
                kit_desc = row['Descricao']
                payload = {"nome": kit_nome, "preco_sugerido": row['Preco'], "descricao_comercial": kit_desc}

                kit_id = None
                if 'id' in row and pd.notna(row['id']):
                    kit_id = int(row['id'])
                    supabase.table("kits").update(payload).eq("id", kit_id).execute()
                else:
                    res = supabase.table("kits").select("id").eq("nome", kit_nome).execute()
                    if res.data:
                        kit_id = res.data[0]['id']
                        supabase.table("kits").update(payload).eq("id", kit_id).execute()
                    else:
                        res_new = supabase.table("kits").insert(payload).execute()
                        kit_id = res_new.data[0]['id']

                if kit_id and kit_desc:
                    supabase.table("kit_itens").delete().eq("kit_id", kit_id).execute()
                    itens_para_inserir = []
                    partes = str(kit_desc).split(';')

                    for p in partes:
                        p = p.strip()
                        if not p: continue
                        qtd = 1
                        nome_item = p

                        if "x " in p:
                            try:
                                q_str, n_str = p.split("x ", 1)
                                if q_str.strip().isdigit():
                                    qtd = int(q_str)
                                    nome_item = n_str.strip()
                            except:
                                pass

                        res_item = supabase.table("acervo").select("id").eq("nome", nome_item).execute()
                        if res_item.data:
                            item_id = res_item.data[0]['id']
                            itens_para_inserir.append({
                                "kit_id": kit_id,
                                "item_acervo_id": item_id,
                                "quantidade": qtd
                            })

                    if itens_para_inserir:
                        supabase.table("kit_itens").insert(itens_para_inserir).execute()

        elif tabela_virtual == "Temas":
            for row in records:
                tema_nome = row['Tema']
                tema_desc = row['Detalhes']
                payload = {"nome": tema_nome, "categoria": row['Categoria'], "detalhes": tema_desc}

                tema_id = None
                if 'id' in row and pd.notna(row['id']):
                    tema_id = int(row['id'])
                    supabase.table("temas").update(payload).eq("id", tema_id).execute()
                else:
                    res = supabase.table("temas").select("id").eq("nome", tema_nome).execute()
                    if res.data:
                        tema_id = res.data[0]['id']
                        supabase.table("temas").update(payload).eq("id", tema_id).execute()
                    else:
                        res_new = supabase.table("temas").insert(payload).execute()
                        tema_id = res_new.data[0]['id']

                if tema_id and tema_desc and "Base:" in tema_desc:
                    try:
                        _, parte_itens = tema_desc.split("Base:", 1)
                        nomes = [x.strip() for x in parte_itens.split(',')]
                        supabase.table("tema_itens").delete().eq("tema_id", tema_id).execute()
                        inserts = []
                        for nm in nomes:
                            res_it = supabase.table("acervo").select("id").eq("nome", nm).execute()
                            if res_it.data:
                                inserts.append({
                                    "tema_id": tema_id,
                                    "item_acervo_id": res_it.data[0]['id']
                                })
                        if inserts:
                            supabase.table("tema_itens").insert(inserts).execute()
                    except:
                        pass

    @staticmethod
    def registrar_transacao(transacao: Dict, update_estoque: Dict = None):
        supabase = SupabaseService.get_client()
        try:
            d_venc = str(transacao['data'])
        except:
            d_venc = str(date.today())

        payload = {
            "descricao": transacao['descricao'], "tipo": transacao['tipo'],
            "categoria": transacao['categoria'], "valor": transacao['valor'],
            "data_vencimento": d_venc,
            "data_pagamento": d_venc if transacao['status'] in ['Pago', 'Recebido'] else None,
            "quem_pagou_recebeu": transacao['quem'], "forma_pagamento": transacao['forma_pagto']
        }

        supabase.table("financeiro").insert(payload).execute()

        if update_estoque:
            item_payload = {
                "nome": update_estoque['item'], "quantidade_total": update_estoque['qtd'],
                "custo_aquisicao": update_estoque['custo'], "link_reposicao": update_estoque['link'],
                "categoria": "Novo", "tipo": "Acervo", "ativo": True
            }
            res = supabase.table("acervo").select("*").eq("nome", update_estoque['item']).execute()
            if res.data:
                nova_qtd = res.data[0]['quantidade_total'] + update_estoque['qtd']
                supabase.table("acervo").update({"quantidade_total": nova_qtd}).eq("id", res.data[0]['id']).execute()
            else:
                supabase.table("acervo").insert(item_payload).execute()


# ==========================================
# SERVIÇOS AUXILIARES
# ==========================================
class InventoryService:
    @staticmethod
    def calcular_mapa_ocupacao(orcamentos: List[Dict]) -> Dict[str, Dict[str, int]]:
        mapa = {}
        for orc in orcamentos:
            if orc.get('status') in ['Cancelado', 'Reprovado']: continue
            d_evt = orc.get('data_evento')
            if not d_evt: continue

            # CORREÇÃO: Lê os itens reais carregados do banco (campo auxiliar)
            itens = orc.get('itens_reais_db', [])

            # Fallback para o modo antigo (JSON)
            if not itens:
                dados = orc.get('dados_form', {})
                itens = dados.get('in_itens_pers', []) + dados.get('in_itens_add', [])

            if str(d_evt) not in mapa: mapa[str(d_evt)] = {}

            for i in itens:
                mapa[str(d_evt)][i] = mapa[str(d_evt)].get(i, 0) + 1

        return mapa

    @staticmethod
    def verificar_disponibilidade_rapida(item_nome: str, data_evento: str, estoque_total: int, mapa_ocupacao: Dict) -> \
            Tuple[int, int]:
        uso = mapa_ocupacao.get(str(data_evento), {}).get(item_nome, 0)
        return uso, estoque_total - uso


class PDFGenerator:
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
        variables = {"document": {"name": "Contrato de Locação - NT Festas"},
                     "signers": [{"email": email_cliente, "action": "SIGN"}]}
        try:
            with open(caminho_pdf, "rb") as f:
                response = requests.post(AUTENTIQUE_URL,
                                         data={"operations": json.dumps({"query": query, "variables": variables}),
                                               "map": json.dumps({"0": ["variables.file"]})}, files={"0": f},
                                         headers={"Authorization": f"Bearer {token}"})
            if response.status_code == 200:
                dados = response.json()
                if dados.get("errors"): return False, f"Erro API: {dados['errors'][0]['message']}"
                link = next((s["link"]["short_link"] for s in
                             dados.get("data", {}).get("createDocument", {}).get("signatures", []) if s.get("link")),
                            "EMAIL_ENVIADO")
                return True, link
            return False, f"Erro HTTP {response.status_code}"
        except Exception as e:
            return False, f"Erro Técnico: {e}"

class AuthService:
    @staticmethod
    def login(email, senha):
        supabase = SupabaseService.get_client()
        try:
            # Tenta logar usando o Auth do Supabase
            response = supabase.auth.sign_in_with_password({"email": email, "password": senha})
            if response.user:
                return True, response.user
            return False, "Credenciais inválidas."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def logout():
        supabase = SupabaseService.get_client()
        try:
            supabase.auth.sign_out()
            return True
        except:
            return False

    @staticmethod
    def get_current_user():
        # Verifica se existe sessão ativa
        supabase = SupabaseService.get_client()
        session = supabase.auth.get_session()
        if session:
            return session.user
        return None