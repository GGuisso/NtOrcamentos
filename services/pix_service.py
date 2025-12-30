# services/pix_service.py
class PixService:
    @staticmethod
    def gerar_payload_pix(chave_pix: str, beneficiario_nome: str, beneficiario_cidade: str, valor: float, txid: str = "***") -> str:
        try:
            chave_pix = chave_pix.strip()
            beneficiario_nome = beneficiario_nome[:25].strip().upper()
            beneficiario_cidade = beneficiario_cidade[:15].strip().upper()
            valor_str = f"{valor:.2f}"
            gui = "0014br.gov.bcb.pix"
            key_content = f"01{len(chave_pix):02}{chave_pix}"
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
            payload = f"000201{merchant_account}{merchant_category}{currency}{amount}{country}{name}{city}{additional_data}6304"
            def crc16(data: str) -> str:
                crc = 0xFFFF
                poly = 0x1021
                for char in data:
                    crc ^= (ord(char) << 8)
                    for _ in range(8):
                        if crc & 0x8000: crc = (crc << 1) ^ poly
                        else: crc <<= 1
                    crc &= 0xFFFF
                return f"{crc:04X}"
            return payload + crc16(payload)
        except Exception as e:
            print(f"Erro Pix: {e}")
            return ""