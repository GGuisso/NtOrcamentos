import streamlit as st
import requests
import json
import pandas as pd
import time
import tempfile
import segno
from datetime import datetime, date, time as dt_time
from supabase import create_client, Client, ClientOptions
from typing import Tuple, Dict, List, Any, Optional
from fpdf import FPDF

# ==========================================
# CONFIGURAÇÃO E SEGREDOS
# ==========================================
VIACEP_URL = "https://viacep.com.br/ws/{}/json/"
AUTENTIQUE_URL = "https://api.autentique.com.br/v2/graphql"


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
        """Retorna o cliente PADRÃO (Anon Key). Respeita as regras de segurança (RLS)."""
        if not SUPA_URL or not SUPA_KEY:
            st.error("⚠️ Configure SUPABASE_URL e SUPABASE_KEY no secrets.toml")
            st.stop()

        options = ClientOptions(
            postgrest_client_timeout=30,
            storage_client_timeout=30,
            schema="public",
        )
        return create_client(SUPA_URL, SUPA_KEY, options=options)

    @staticmethod
    def carregar_configuracoes(tenant_id: str) -> Dict:
        """Carrega configs do banco. Se não existir, cria uma padrão."""
        supabase = SupabaseService.get_client()
        # Se não tiver tenant, retorna o padrão hardcoded
        if not tenant_id:
            return {"custo_km": 2.0, "custo_hora": 50.0, "taxa_higienizacao": 20.0}

        try:
            res = supabase.table("configuracoes").select("*").eq("tenant_id", tenant_id).execute()

            if res.data:
                return res.data[0]
            else:
                # Se não existe config para este tenant, cria a padrão agora
                payload = {
                    "tenant_id": tenant_id,
                    "custo_km": 2.00,
                    "custo_hora": 50.00,
                    "taxa_higienizacao": 20.00
                }
                res_new = supabase.table("configuracoes").insert(payload).execute()
                return res_new.data[0]
        except Exception as e:
            print(f"Erro Config: {e}")
            return {"custo_km": 2.0, "custo_hora": 50.0, "taxa_higienizacao": 20.0}

    @staticmethod
    def atualizar_configuracoes(tenant_id: str, dados: Dict):
        supabase = SupabaseService.get_client()
        try:
            # ADICIONA O TENANT_ID AO PACOTE DE DADOS
            # Isso é obrigatório para criar a linha nova se ela não existir
            dados['tenant_id'] = tenant_id

            # MUDA DE .update() PARA .upsert()
            # on_conflict="tenant_id" garante que ele sabe qual linha buscar
            supabase.table("configuracoes").upsert(dados, on_conflict="tenant_id").execute()

            return True, "Configurações salvas com sucesso!"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def buscar_clientes(termo: str, por_cpf: bool = False) -> List[Dict]:
        supabase = SupabaseService.get_client()
        termo = termo.strip()
        if not termo: return []

        tenant = st.session_state.get('tenant_id')
        if not tenant: return []

        try:
            query = supabase.table("clientes").select("*").eq("tenant_id", tenant)

            if por_cpf:
                cpf_limpo = "".join([c for c in termo if c.isdigit()])
                if not cpf_limpo: return []
                res = query.eq("cpf", cpf_limpo).execute()
            else:
                res = query.ilike("nome", f"%{termo}%").execute()

            return res.data
        except Exception as e:
            print(f"Erro busca cliente: {e}")
            return []

    @staticmethod
    def upload_imagem(file_obj, nome_arquivo_original: str) -> Optional[str]:
        try:
            supabase = SupabaseService.get_client()
            tenant = st.session_state.get('tenant_id', 'public')

            nome_limpo = "".join(
                [c for c in nome_arquivo_original if c.isalnum() or c in (' ', '_', '.', '-')]).replace(" ", "_")

            path = f"{tenant}/{int(time.time())}_{nome_limpo}"

            file_bytes = file_obj.getvalue()
            supabase.storage.from_("acervo").upload(
                path=path, file=file_bytes, file_options={"content-type": file_obj.type, "upsert": "false"}
            )
            return supabase.storage.from_("acervo").get_public_url(path)
        except Exception as e:
            print(f"Erro Upload: {e}")
            return None

    @staticmethod
    @st.cache_data(ttl=300, show_spinner=False)
    def carregar_catalogo(tenant_id: str) -> Tuple[Dict, Dict, Dict, Dict, Dict]:
        if not tenant_id:
            return {}, {}, {}, {}, {}

        supabase = SupabaseService.get_client()

        res_acervo = supabase.table("acervo").select("*").eq("tenant_id", tenant_id).eq("ativo", True).execute()
        acervo_dict = {}
        estoque_dict = {}
        for item in res_acervo.data:
            acervo_dict[item['nome']] = float(item['preco_aluguel'])
            estoque_dict[item['nome']] = int(item['quantidade_total'])

        res_temas = supabase.table("temas").select("*").eq("tenant_id", tenant_id).execute()
        categorias = {}
        detalhes = {}
        for t in res_temas.data:
            cat = t['categoria']
            tema_nome = t['nome']
            if cat not in categorias: categorias[cat] = []
            categorias[cat].append(tema_nome)
            detalhes[tema_nome] = t['detalhes'] or ""

        res_kits = supabase.table("kits").select("*").eq("tenant_id", tenant_id).execute()
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
        tenant = st.session_state.get('tenant_id')
        if not tenant: return []

        res = supabase.table("orcamentos").select(
            "*, clientes(nome), orcamento_itens(quantidade, acervo(nome))"
        ).eq("tenant_id", tenant).execute()

        lista_final = []
        for row in res.data:
            dados_form = row.get('dados_form_snapshot') or {}
            tema_salvo = dados_form.get('in_tema', row.get('tema', '?'))

            lista_itens_reais = []
            if row.get('orcamento_itens'):
                for oi in row['orcamento_itens']:
                    if oi.get('acervo') and oi.get('quantidade'):
                        nome_item = oi['acervo']['nome']
                        qtd = oi['quantidade']
                        lista_itens_reais.extend([nome_item] * qtd)

            orcamento_obj = {
                "id": row['id'],
                "cliente": row['clientes']['nome'] if row['clientes'] else "Desconhecido",
                "data_evento": row['data_evento'],
                "status": row['status'],
                "total": float(row['valor_total'] or 0.0),
                "tema": tema_salvo,
                "dados_form": dados_form,
                "itens_reais_db": lista_itens_reais,
                "picking_status": row.get('picking_status', {}) or {},
                "link_uuid": row.get('link_uuid'),
                "data_registro": row.get('created_at')
            }
            lista_final.append(orcamento_obj)
        return lista_final

    @staticmethod
    def get_dataframe(tabela_virtual: str) -> pd.DataFrame:
        supabase = SupabaseService.get_client()
        tenant = st.session_state.get('tenant_id')
        if not tenant: return pd.DataFrame()

        if tabela_virtual == "Itens":
            res = supabase.table("acervo").select("*").eq("tenant_id", tenant).order("nome").execute()
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
            res = supabase.table("kits").select("*").eq("tenant_id", tenant).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df.rename(columns={
                    "nome": "Nome", "preco_sugerido": "Preco", "descricao_comercial": "Descricao"
                }, inplace=True)
            return df

        elif tabela_virtual == "Temas":
            res = supabase.table("temas").select("*").eq("tenant_id", tenant).execute()
            df = pd.DataFrame(res.data)
            if not df.empty:
                df.rename(columns={
                    "nome": "Tema", "categoria": "Categoria", "detalhes": "Detalhes"
                }, inplace=True)
            return df

        elif tabela_virtual == "Financeiro":
            res = supabase.table("financeiro").select("*").eq("tenant_id", tenant).order("created_at",
                                                                                         desc=True).execute()
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

    @staticmethod
    def upsert_orcamento(orcamento: Dict):
        supabase = SupabaseService.get_client()
        tenant = st.session_state.get('tenant_id')
        if not tenant:
            st.error("Sessão expirada. Faça login novamente.")
            return

        dados_form = orcamento.get('dados_form', {})
        dados_form_serializable = {}
        for k, v in dados_form.items():
            if isinstance(v, (date, datetime, dt_time)):
                dados_form_serializable[k] = str(v)
            else:
                dados_form_serializable[k] = v

        cli_nome = dados_form.get('in_nome')
        cli_cpf = dados_form.get('in_cpf')
        nasc = dados_form.get('in_nascimento')
        if isinstance(nasc, (date, datetime)):
            nasc = str(nasc)
        else:
            nasc = None

        cliente_payload = {
            "tenant_id": tenant,
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

        res_cli = supabase.table("clientes").select("id").eq("tenant_id", tenant).eq("nome", cli_nome).execute()
        if res_cli.data:
            cliente_id = res_cli.data[0]['id']
            supabase.table("clientes").update(cliente_payload).eq("id", cliente_id).execute()
        else:
            res_new_cli = supabase.table("clientes").insert(cliente_payload).execute()
            cliente_id = res_new_cli.data[0]['id']

        orc_payload = {
            "tenant_id": tenant,
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
            supabase.table("orcamentos").update(orc_payload).eq("id", orc_id).execute()
            final_orc_id = orc_id
        else:
            res_orc = supabase.table("orcamentos").insert(orc_payload).execute()
            final_orc_id = res_orc.data[0]['id']
            orcamento['id'] = final_orc_id

        supabase.table("orcamento_itens").delete().eq("orcamento_id", final_orc_id).execute()

        kit_selecionado_nome = dados_form.get('in_kit')
        kit_id_db = None
        itens_do_kit_map = {}

        if kit_selecionado_nome and kit_selecionado_nome != "Montar Personalizado (Do Zero)":
            res_kit = supabase.table("kits").select("id").eq("tenant_id", tenant).eq("nome",
                                                                                     kit_selecionado_nome).execute()
            if res_kit.data:
                kit_id_db = res_kit.data[0]['id']
                res_comp = supabase.table("kit_itens").select("quantidade, acervo(nome)").eq("kit_id",
                                                                                             kit_id_db).execute()
                for comp in res_comp.data:
                    if comp['acervo']:
                        itens_do_kit_map[comp['acervo']['nome']] = comp['quantidade']

        lista_base = dados_form.get('in_itens_pers', [])
        if kit_id_db:
            for nome_item_kit in itens_do_kit_map.keys():
                if nome_item_kit not in lista_base:
                    lista_base.append(nome_item_kit)

        lista_add = dados_form.get('in_itens_add', [])
        todos_itens_nomes = list(set(lista_base + lista_add))

        if todos_itens_nomes:
            res_ids = supabase.table("acervo").select("id, nome, preco_aluguel").eq("tenant_id", tenant).in_("nome",
                                                                                                             todos_itens_nomes).execute()
            mapa_acervo = {i['nome']: i for i in res_ids.data}

            itens_insert = []
            for nome_item in lista_base:
                if nome_item in mapa_acervo:
                    dados_db = mapa_acervo[nome_item]
                    eh_do_kit = (kit_id_db is not None and nome_item in itens_do_kit_map)
                    origem_kit = kit_id_db if eh_do_kit else None
                    qtd = itens_do_kit_map[nome_item] if eh_do_kit else 1

                    itens_insert.append({
                        "tenant_id": tenant,
                        "orcamento_id": final_orc_id,
                        "item_acervo_id": dados_db['id'],
                        "quantidade": qtd,
                        "preco_unitario_cobrado": dados_db['preco_aluguel'],
                        "origem_kit_id": origem_kit
                    })

            for nome_item in lista_add:
                if nome_item in mapa_acervo:
                    dados_db = mapa_acervo[nome_item]
                    itens_insert.append({
                        "tenant_id": tenant,
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
        tenant = st.session_state.get('tenant_id')
        if not tenant: return

        records = df.to_dict(orient="records")

        if tabela_virtual == "Itens":
            for row in records:
                tipo_valor = row.get('Tipo') or 'Acervo'
                try:
                    qtd = int(float(row.get('Qtd_Estoque', 1) or 1))
                except:
                    qtd = 1

                payload = {
                    "tenant_id": tenant,
                    "nome": row['Item'], "categoria": "Geral", "tipo": tipo_valor,
                    "preco_aluguel": row.get('Preco', 0), "quantidade_total": qtd,
                    "custo_aquisicao": row.get('Custo_Unitario', 0), "link_reposicao": row.get('Link_Referencia', ''),
                    "foto_url": row.get('Imagem', ''), "ativo": row.get('ativo', True)
                }
                if row.get('id') and pd.notna(row.get('id')):
                    supabase.table("acervo").update(payload).eq("id", int(row['id'])).execute()
                else:
                    res = supabase.table("acervo").select("id").eq("tenant_id", tenant).eq("nome",
                                                                                           row['Item']).execute()
                    if res.data:
                        supabase.table("acervo").update(payload).eq("id", res.data[0]['id']).execute()
                    else:
                        supabase.table("acervo").insert(payload).execute()

        elif tabela_virtual == "Kits":
            for row in records:
                kit_nome = row['Nome']
                kit_desc = row['Descricao']
                payload = {"tenant_id": tenant, "nome": kit_nome, "preco_sugerido": row['Preco'],
                           "descricao_comercial": kit_desc}

                kit_id = None
                if 'id' in row and pd.notna(row['id']):
                    kit_id = int(row['id'])
                    supabase.table("kits").update(payload).eq("id", kit_id).execute()
                else:
                    res = supabase.table("kits").select("id").eq("tenant_id", tenant).eq("nome", kit_nome).execute()
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

                        res_item = supabase.table("acervo").select("id").eq("tenant_id", tenant).eq("nome",
                                                                                                    nome_item).execute()
                        if res_item.data:
                            item_id = res_item.data[0]['id']
                            itens_para_inserir.append({
                                "tenant_id": tenant,
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
                payload = {"tenant_id": tenant, "nome": tema_nome, "categoria": row['Categoria'], "detalhes": tema_desc}

                tema_id = None
                if 'id' in row and pd.notna(row['id']):
                    tema_id = int(row['id'])
                    supabase.table("temas").update(payload).eq("id", tema_id).execute()
                else:
                    res = supabase.table("temas").select("id").eq("tenant_id", tenant).eq("nome", tema_nome).execute()
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
                            res_it = supabase.table("acervo").select("id").eq("tenant_id", tenant).eq("nome",
                                                                                                      nm).execute()
                            if res_it.data:
                                inserts.append({
                                    "tenant_id": tenant,
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
        tenant = st.session_state.get('tenant_id')
        if not tenant: return

        try:
            d_venc = str(transacao['data'])
        except:
            d_venc = str(date.today())

        payload = {
            "tenant_id": tenant,
            "descricao": transacao['descricao'], "tipo": transacao['tipo'],
            "categoria": transacao['categoria'], "valor": transacao['valor'],
            "data_vencimento": d_venc,
            "data_pagamento": d_venc if transacao['status'] in ['Pago', 'Recebido'] else None,
            "quem_pagou_recebeu": transacao['quem'], "forma_pagamento": transacao['forma_pagto']
        }

        supabase.table("financeiro").insert(payload).execute()

        if update_estoque:
            item_payload = {
                "tenant_id": tenant,
                "nome": update_estoque['item'], "quantidade_total": update_estoque['qtd'],
                "custo_aquisicao": update_estoque['custo'], "link_reposicao": update_estoque['link'],
                "categoria": "Novo", "tipo": "Acervo", "ativo": True
            }
            res = supabase.table("acervo").select("*").eq("tenant_id", tenant).eq("nome",
                                                                                  update_estoque['item']).execute()
            if res.data:
                nova_qtd = res.data[0]['quantidade_total'] + update_estoque['qtd']
                supabase.table("acervo").update({"quantidade_total": nova_qtd}).eq("id", res.data[0]['id']).execute()
            else:
                supabase.table("acervo").insert(item_payload).execute()


# ==========================================
# SERVIÇOS AUXILIARES (AUTH)
# ==========================================
class AuthService:
    @staticmethod
    def login(email, senha):
        supabase = SupabaseService.get_client()
        try:
            # 1. Login Auth padrão
            response = supabase.auth.sign_in_with_password({"email": email, "password": senha})

            if response.user and response.session:
                # 2. Busca qual é a empresa (tenant) desse usuário
                res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id",
                                                                                            response.user.id).execute()

                tenant_id = None
                role = 'vendedor'

                if res_profile.data:
                    tenant_id = res_profile.data[0]['tenant_id']
                    role = res_profile.data[0]['role']

                # Salva na sessão
                st.session_state['tenant_id'] = tenant_id

                return True, {
                    "user_auth": response.user,
                    "tenant_id": tenant_id,
                    "role": role,
                    "email": email,
                    "access_token": response.session.access_token
                }
            return False, "Credenciais inválidas."
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_user_by_token(token):
        """Recupera sessão via Token (Cookie)"""
        supabase = SupabaseService.get_client()
        try:
            # Tenta pegar o usuário usando o token do cookie
            response = supabase.auth.get_user(token)

            if response and response.user:
                user = response.user

                # Busca perfil (Tenant/Role)
                res_profile = supabase.table("profiles").select("tenant_id, role, nome").eq("id", user.id).execute()

                tenant_id = None
                role = 'vendedor'

                if res_profile.data:
                    tenant_id = res_profile.data[0]['tenant_id']
                    role = res_profile.data[0]['role']

                # Restaura sessão
                st.session_state['tenant_id'] = tenant_id

                return {
                    "user_auth": user,
                    "tenant_id": tenant_id,
                    "role": role,
                    "email": user.email,
                    "access_token": token
                }
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


# ==========================================
# 4. ADMINISTRAÇÃO E SEGURANÇA
# ==========================================

class AdminService:
    @staticmethod
    def get_admin_client() -> Client:
        """
        Cria um cliente especial usando a SUPABASE_SERVICE_KEY.
        Este cliente BYPASSA o RLS e tem permissões de Admin.
        Use apenas para operações administrativas.
        """
        service_key = get_secret("SUPABASE_SERVICE_KEY")
        if not service_key:
            st.error("⚠️ Configuração de segurança ausente: SUPABASE_SERVICE_KEY")
            st.stop()

        # Cria um cliente novo com poderes administrativos
        return create_client(SUPA_URL, service_key)

    @staticmethod
    def criar_usuario_equipe(email, senha, nome, role, tenant_id):
        """
        Cria usuário no Auth e insere na tabela profiles usando a chave Service Role.
        """
        admin_supabase = AdminService.get_admin_client()

        try:
            # 1. Cria o usuário no Sistema de Autenticação (Auth)
            user_response = admin_supabase.auth.admin.create_user({
                "email": email,
                "password": senha,
                "email_confirm": True,  # Já nasce confirmado
                "user_metadata": {"nome": nome}
            })

            new_user_id = user_response.user.id

            # 2. Cria o Perfil vinculado à empresa (Tenant)
            profile_payload = {
                "id": new_user_id,
                "tenant_id": tenant_id,
                "email": email,
                "nome": nome,
                "role": role
            }

            # Insere no banco com poderes de admin (ignorando RLS)
            admin_supabase.table("profiles").insert(profile_payload).execute()

            return True, "Usuário criado com sucesso!"

        except Exception as e:
            msg_erro = str(e)
            if "already registered" in msg_erro:
                return False, "Este e-mail já está cadastrado."
            return False, f"Erro ao criar usuário: {msg_erro}"

    @staticmethod
    def listar_equipe():
        """
        Lista usuários.
        """
        admin_supabase = AdminService.get_admin_client()

        tenant = st.session_state.get('tenant_id')
        if not tenant: return []

        res = admin_supabase.table("profiles").select("*").eq("tenant_id", tenant).execute()
        return res.data

    @staticmethod
    def excluir_usuario(user_id_alvo, tenant_atual):
        """
        Remove o usuário.
        Segurança Crítica: Verifica se o usuario alvo pertence ao mesmo tenant
        antes de deletar.
        """
        admin_supabase = AdminService.get_admin_client()

        if not tenant_atual:
            return False, "Sessão inválida."

        try:
            # 1. Verificar se o alvo pertence ao mesmo tenant
            res = admin_supabase.table("profiles") \
                .select("id") \
                .eq("id", user_id_alvo) \
                .eq("tenant_id", tenant_atual) \
                .execute()

            if not res.data:
                return False, "Usuário não encontrado ou não pertence à sua equipe."

            # 2. Se validou o tenant, pode deletar do Auth
            admin_supabase.auth.admin.delete_user(user_id_alvo)
            return True, "Usuário removido."
        except Exception as e:
            return False, str(e)


# ==========================================
# SERVIÇOS AUXILIARES (INVENTORY & PDF)
# ==========================================
class InventoryService:
    @staticmethod
    def calcular_mapa_ocupacao(orcamentos: List[Dict]) -> Dict[str, Dict[str, int]]:
        mapa = {}
        for orc in orcamentos:
            if orc.get('status') in ['Cancelado', 'Reprovado']: continue
            d_evt = orc.get('data_evento')
            if not d_evt: continue

            itens = orc.get('itens_reais_db', [])
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

    @staticmethod
    def atualizar_picking_status(orcamento_id, novo_status_dict):
        """Salva o checklist de separação no banco (JSONB)"""
        supabase = SupabaseService.get_client()
        try:
            supabase.table("orcamentos").update({
                "picking_status": novo_status_dict
            }).eq("id", orcamento_id).execute()
            return True
        except Exception as e:
            print(f"Erro picking: {e}")
            return False

    @staticmethod
    def gerar_picking_list(orcamentos_filtrados, tenant_id):
        """
        Gera a lista de separação.
        Se os itens já estiverem salvos no banco (itens_reais_db), usa eles.
        Caso contrário, tenta reconstruir baseado no Kit do formulário.
        """
        supabase = SupabaseService.get_client()

        res_kits = supabase.table("kit_itens").select("kit_id, quantidade, acervo(nome), kits(nome)").eq("tenant_id",
                                                                                                         tenant_id).execute()

        mapa_composicao_kits = {}
        for k in res_kits.data:
            if k['kits'] and k['acervo']:
                nome_kit = k['kits']['nome']
                nome_item = k['acervo']['nome']
                qtd_item = k['quantidade']
                if nome_kit not in mapa_composicao_kits: mapa_composicao_kits[nome_kit] = []
                mapa_composicao_kits[nome_kit].append({"item": nome_item, "qtd": qtd_item})

        resumo_total = {}
        detalhe_por_cliente = []

        for orc in orcamentos_filtrados:
            itens_brutos = []

            if orc.get('itens_reais_db') and len(orc['itens_reais_db']) > 0:
                itens_brutos.extend(orc['itens_reais_db'])
            else:
                dados_form = orc.get('dados_form', {})
                nome_kit_vendido = dados_form.get('in_kit')

                if nome_kit_vendido and nome_kit_vendido in mapa_composicao_kits:
                    componentes = mapa_composicao_kits[nome_kit_vendido]
                    for comp in componentes:
                        itens_brutos.extend([comp['item']] * comp['qtd'])

                itens_add = dados_form.get('in_itens_add', [])
                itens_pers = dados_form.get('in_itens_pers', [])
                itens_brutos.extend(itens_add)
                itens_brutos.extend(itens_pers)

            contagem_cliente = {}
            for i in itens_brutos:
                contagem_cliente[i] = contagem_cliente.get(i, 0) + 1
                resumo_total[i] = resumo_total.get(i, 0) + 1

            detalhe_por_cliente.append({
                "id": orc['id'],
                "cliente": orc['cliente'],
                "data": orc['data_evento'],
                "logistica": orc.get('logistica_tipo', 'Pegue e Monte'),
                "endereco": f"{orc.get('endereco_evento_rua', '')}, {orc.get('endereco_evento_numero', '')}",
                "itens": contagem_cliente,
                "picking_saved": orc.get('picking_status', {})
            })

        return resumo_total, detalhe_por_cliente

    @staticmethod
    def registrar_avaria(item_nome, qtd_avariada, custo_prejuizo, cobrar_cliente, valor_cobrado, orcamento_id, obs):
        supabase = SupabaseService.get_client()
        tenant = st.session_state.get('tenant_id')

        try:
            res_item = supabase.table("acervo").select("*").eq("tenant_id", tenant).eq("nome", item_nome).execute()
            if res_item.data:
                item_db = res_item.data[0]
                nova_qtd = max(0, item_db['quantidade_total'] - qtd_avariada)
                supabase.table("acervo").update({"quantidade_total": nova_qtd}).eq("id", item_db['id']).execute()

            data_hoje = str(date.today())
            ts = int(time.time())

            if custo_prejuizo > 0:
                SupabaseService.registrar_transacao({
                    "id": ts, "data": data_hoje, "tipo": "Despesa",
                    "categoria": "Reposição/Avaria",
                    "descricao": f"Avaria: {qtd_avariada}x {item_nome} (Ped #{orcamento_id}) - {obs}",
                    "valor": custo_prejuizo, "quem": "Estoque", "forma_pagto": "Interno", "status": "Pago",
                    "loja": "", "link": ""
                })

            if cobrar_cliente and valor_cobrado > 0:
                SupabaseService.registrar_transacao({
                    "id": ts + 1, "data": data_hoje, "tipo": "Receita",
                    "categoria": "Indenização Avaria",
                    "descricao": f"Multa Avaria - Cliente Ped #{orcamento_id}",
                    "valor": valor_cobrado, "quem": "Cliente", "forma_pagto": "A Definir", "status": "A Receber",
                    "loja": "", "link": ""
                })

            return True, "Avaria registrada e estoque atualizado."
        except Exception as e:
            return False, str(e)


class PixService:
    @staticmethod
    def gerar_payload_pix(chave_pix: str, beneficiario_nome: str, beneficiario_cidade: str, valor: float,
                          txid: str = "***") -> str:
        """
        Gera a string 'Copia e Cola' do Pix (Padrão EMV QRCPS) - CORRIGIDO.
        """
        try:
            chave_pix = chave_pix.strip()
            beneficiario_nome = beneficiario_nome[:25].strip().upper()
            beneficiario_cidade = beneficiario_cidade[:15].strip().upper()
            valor_str = f"{valor:.2f}"

            # 1. Campos
            gui = "0014br.gov.bcb.pix"

            # CORREÇÃO: O tamanho do campo 01 (chave) é calculado baseado na chave fornecida
            key_content = f"01{len(chave_pix):02}{chave_pix}"

            # Campo 26: Merchant Account Info
            merchant_content = f"{gui}{key_content}"
            merchant_account = f"26{len(merchant_content):02}{merchant_content}"

            merchant_category = "52040000"
            currency = "5303986"
            amount = f"54{len(valor_str):02}{valor_str}"
            country = "5802BR"
            name = f"59{len(beneficiario_nome):02}{beneficiario_nome}"
            city = f"60{len(beneficiario_cidade):02}{beneficiario_cidade}"

            txid_content = f"05{len(txid):02}{txid}"
            additional_data = f"62{len(txid_content):02}{txid_content}"

            # 2. Payload sem CRC
            payload = f"000201{merchant_account}{merchant_category}{currency}{amount}{country}{name}{city}{additional_data}6304"

            # 3. CRC Calculation
            def crc16(data: str) -> str:
                crc = 0xFFFF
                poly = 0x1021
                for char in data:
                    crc ^= (ord(char) << 8)
                    for _ in range(8):
                        if crc & 0x8000:
                            crc = (crc << 1) ^ poly
                        else:
                            crc <<= 1
                    crc &= 0xFFFF
                return f"{crc:04X}"

            return payload + crc16(payload)
        except Exception as e:
            print(f"Erro Pix: {e}")
            return ""


class PublicService:
    @staticmethod
    def buscar_orcamento_uuid(uuid_str: str) -> Optional[Dict]:
        """Busca orçamento usando a chave de ADMIN para bypassar o RLS"""
        admin_client = AdminService.get_admin_client()
        try:
            res = admin_client.table("orcamentos").select(
                "*, clientes(nome, cpf, telefone), orcamento_itens(quantidade, acervo(nome, foto_url, preco_aluguel))"
            ).eq("link_uuid", uuid_str).execute()

            if not res.data: return None

            row = res.data[0]

            itens_formatados = []
            if row.get('orcamento_itens'):
                for oi in row['orcamento_itens']:
                    if oi.get('acervo'):
                        itens_formatados.append({
                            "nome": oi['acervo']['nome'],
                            "foto": oi['acervo'].get('foto_url', ''),
                            "qtd": oi['quantidade'],
                            "preco": oi['acervo'].get('preco_aluguel', 0)
                        })

            return {
                "id": row['id'],
                "uuid": row['link_uuid'],
                "cliente_nome": row['clientes']['nome'],
                "cliente_cpf": row['clientes'].get('cpf', ''),
                "cliente_whats": row['clientes']['telefone'],
                "data_evento": row['data_evento'],
                "status": row['status'],
                "total": float(row['valor_total'] or 0),
                "itens": itens_formatados,
                "aceite_dados": row.get('aceite_dados', {}),
                "dados_form": row.get('dados_form_snapshot') or {}
            }
        except Exception as e:
            print(f"Erro Public: {e}")
            return None

    @staticmethod
    def registrar_aceite(orc_id: int, ip_cliente: str):
        admin_client = AdminService.get_admin_client()
        timestamp = str(datetime.now())
        try:
            payload = {"aceite_em": timestamp, "ip": ip_cliente, "versao_termos": "v1.0"}
            admin_client.table("orcamentos").update({
                "status": "Aguardando Pagamento",
                "aceite_dados": payload
            }).eq("id", orc_id).execute()
            return True, "Sucesso"
        except Exception as e:
            print(f"ERRO DE ACEITE: {e}")
            return False, str(e)


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

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                pdf.output(tmp_file.name)
                return tmp_file.name
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