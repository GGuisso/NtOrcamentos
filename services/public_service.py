# services/public_service.py
from typing import Optional, Dict
from datetime import datetime
from .admin_service import AdminService

class PublicService:
    @staticmethod
    def buscar_orcamento_uuid(uuid_str: str) -> Optional[Dict]:
        admin_client = AdminService.get_admin_client()
        try:
            res = admin_client.table("orcamentos").select("*, clientes(nome, cpf, telefone), orcamento_itens(quantidade, acervo(nome, foto_url, preco_aluguel))").eq("link_uuid", uuid_str).execute()
            if not res.data: return None
            row = res.data[0]
            itens_formatados = []
            if row.get('orcamento_itens'):
                for oi in row['orcamento_itens']:
                    if oi.get('acervo'):
                        itens_formatados.append({"nome": oi['acervo']['nome'], "foto": oi['acervo'].get('foto_url', ''), "qtd": oi['quantidade'], "preco": oi['acervo'].get('preco_aluguel', 0)})
            return {
                "id": row['id'], "uuid": row['link_uuid'], "cliente_nome": row['clientes']['nome'],
                "cliente_cpf": row['clientes'].get('cpf', ''), "cliente_whats": row['clientes']['telefone'],
                "data_evento": row['data_evento'], "status": row['status'], "total": float(row['valor_total'] or 0),
                "itens": itens_formatados, "aceite_dados": row.get('aceite_dados', {}), "dados_form": row.get('dados_form_snapshot') or {}
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
            admin_client.table("orcamentos").update({"status": "Aguardando Pagamento", "aceite_dados": payload}).eq("id", orc_id).execute()
            return True, "Sucesso"
        except Exception as e:
            print(f"ERRO DE ACEITE: {e}")
            return False, str(e)