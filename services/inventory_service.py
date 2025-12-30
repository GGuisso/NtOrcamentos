# services/inventory_service.py
import streamlit as st
import time
from datetime import date
from typing import Dict, List, Tuple
from .database_service import SupabaseService

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
    def verificar_disponibilidade_rapida(item_nome: str, data_evento: str, estoque_total: int, mapa_ocupacao: Dict) -> Tuple[int, int]:
        uso = mapa_ocupacao.get(str(data_evento), {}).get(item_nome, 0)
        return uso, estoque_total - uso

    @staticmethod
    def atualizar_picking_status(orcamento_id, novo_status_dict):
        supabase = SupabaseService.get_client()
        try:
            supabase.table("orcamentos").update({"picking_status": novo_status_dict}).eq("id", orcamento_id).execute()
            return True
        except Exception as e:
            print(f"Erro picking: {e}")
            return False

    @staticmethod
    def gerar_picking_list(orcamentos_filtrados, tenant_id):
        supabase = SupabaseService.get_client()
        res_kits = supabase.table("kit_itens").select("kit_id, quantidade, acervo(nome), kits(nome)").eq("tenant_id", tenant_id).execute()
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
                    for comp in mapa_composicao_kits[nome_kit_vendido]: itens_brutos.extend([comp['item']] * comp['qtd'])
                itens_brutos.extend(dados_form.get('in_itens_add', []))
                itens_brutos.extend(dados_form.get('in_itens_pers', []))

            contagem_cliente = {}
            for i in itens_brutos:
                contagem_cliente[i] = contagem_cliente.get(i, 0) + 1
                resumo_total[i] = resumo_total.get(i, 0) + 1

            detalhe_por_cliente.append({
                "id": orc['id'], "cliente": orc['cliente'], "data": orc['data_evento'],
                "logistica": orc.get('logistica_tipo', 'Pegue e Monte'),
                "endereco": f"{orc.get('endereco_evento_rua', '')}, {orc.get('endereco_evento_numero', '')}",
                "itens": contagem_cliente, "picking_saved": orc.get('picking_status', {})
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
                SupabaseService.registrar_transacao({"id": ts, "data": data_hoje, "tipo": "Despesa", "categoria": "Reposição/Avaria", "descricao": f"Avaria: {qtd_avariada}x {item_nome} (Ped #{orcamento_id}) - {obs}", "valor": custo_prejuizo, "quem": "Estoque", "forma_pagto": "Interno", "status": "Pago", "loja": "", "link": ""})
            if cobrar_cliente and valor_cobrado > 0:
                SupabaseService.registrar_transacao({"id": ts + 1, "data": data_hoje, "tipo": "Receita", "categoria": "Indenização Avaria", "descricao": f"Multa Avaria - Cliente Ped #{orcamento_id}", "valor": valor_cobrado, "quem": "Cliente", "forma_pagto": "A Definir", "status": "A Receber", "loja": "", "link": ""})
            return True, "Avaria registrada e estoque atualizado."
        except Exception as e:
            return False, str(e)