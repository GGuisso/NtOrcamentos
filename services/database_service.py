# services/database_service.py
import streamlit as st
import time
import pandas as pd
from datetime import datetime, date, time as dt_time
from supabase import create_client, Client, ClientOptions
from typing import Dict, List, Tuple, Optional
from .config import SUPA_URL, SUPA_KEY


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
        if not tenant_id:
            return {"custo_km": 2.0, "custo_hora": 50.0, "taxa_higienizacao": 20.0}

        try:
            res = supabase.table("configuracoes").select("*").eq("tenant_id", tenant_id).execute()

            if res.data:
                return res.data[0]
            else:
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
            dados['tenant_id'] = tenant_id
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
    def _montar_objeto_orcamento(row: Dict) -> Dict:
        """Helper para padronizar a montagem do objeto orçamento."""
        dados_form = row.get('dados_form_snapshot') or {}
        tema_salvo = dados_form.get('in_tema', row.get('tema', '?'))

        lista_itens_reais = []
        if row.get('orcamento_itens'):
            for oi in row['orcamento_itens']:
                if oi.get('acervo') and oi.get('quantidade'):
                    nome_item = oi['acervo']['nome']
                    qtd = oi['quantidade']
                    lista_itens_reais.extend([nome_item] * qtd)

        return {
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

    @staticmethod
    def carregar_orcamentos() -> List[Dict]:
        supabase = SupabaseService.get_client()
        tenant = st.session_state.get('tenant_id')
        if not tenant: return []

        res = supabase.table("orcamentos").select(
            "*, clientes(nome), orcamento_itens(quantidade, acervo(nome))"
        ).eq("tenant_id", tenant).execute()

        return [SupabaseService._montar_objeto_orcamento(row) for row in res.data]

    @staticmethod
    def listar_orcamentos_paginado(page: int, page_size: int, busca: str = None, status_filtro: List[str] = None) -> \
    Tuple[List[Dict], int]:
        """Nova função com Paginação e Filtros via Banco de Dados."""
        supabase = SupabaseService.get_client()
        tenant = st.session_state.get('tenant_id')
        if not tenant: return [], 0

        query = supabase.table("orcamentos").select(
            "*, clientes!inner(nome), orcamento_itens(quantidade, acervo(nome))", count="exact"
        ).eq("tenant_id", tenant)

        if status_filtro and len(status_filtro) > 0:
            query = query.in_("status", status_filtro)

        if busca:
            if busca.isdigit():
                query = query.eq("id", int(busca))
            else:
                query = query.ilike("clientes.nome", f"%{busca}%")

        start = (page - 1) * page_size
        end = start + page_size - 1

        res = query.order("id", desc=True).range(start, end).execute()

        lista_final = [SupabaseService._montar_objeto_orcamento(row) for row in res.data]
        total_items = res.count if res.count is not None else 0

        return lista_final, total_items

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