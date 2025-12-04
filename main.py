import streamlit as st
from fpdf import FPDF
import requests
import os
import json
import datetime


# ==========================================
# 1. FUNÇÕES DE BACKEND
# ==========================================

def gerar_pdf(cliente, data_evento, cidade, itens, total, sinal, restante, texto_retirada, texto_devolucao):
    """
    Gera o PDF com contrato jurídico, janelas de horários e cláusula de flexibilidade.
    """
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        def clean_text(text):
            if not text: return ""
            text = text.replace("✅", "").replace("•", "-").replace("⚠️", "[OBS]").replace("🎁", "").replace("💰", "")
            return str(text).encode('latin-1', 'replace').decode('latin-1')

        # --- CABEÇALHO ---
        pdf.set_font("Arial", style="B", size=16)
        pdf.cell(190, 10, txt="CONTRATO DE LOCACAO - NT FESTAS", ln=True, align='C')
        pdf.ln(5)

        # --- DADOS DO CLIENTE E EVENTO ---
        pdf.set_font("Arial", size=11)
        pdf.cell(190, 8, txt=clean_text(f"LOCADOR: NT Festas Decorações"), ln=True)
        pdf.cell(190, 8, txt=clean_text(f"LOCATÁRIO: {cliente}"), ln=True)
        pdf.cell(190, 8, txt=clean_text(f"DATA DO EVENTO: {data_evento} | LOCAL: {cidade}"), ln=True)
        pdf.ln(2)

        # --- PRAZOS (EM DESTAQUE - COM JANELA DE HORÁRIO) ---
        pdf.set_fill_color(240, 240, 240)  # Cinza claro
        pdf.set_font("Arial", style="B", size=10)

        pdf.cell(190, 8, txt="AGENDAMENTO (JANELA DE HORÁRIOS):", border=1, ln=True, fill=True, align='C')

        pdf.set_font("Arial", size=10)
        pdf.cell(95, 8, txt=clean_text(f"RETIRADA: {texto_retirada}"), border=1, fill=True)
        pdf.cell(95, 8, txt=clean_text(f"DEVOLUÇÃO: {texto_devolucao}"), border=1, ln=True, fill=True)
        pdf.ln(5)

        # --- LISTA DE ITENS ---
        pdf.set_font("Arial", style="B", size=12)
        pdf.cell(190, 10, txt="ITENS CONTRATADOS:", ln=True)
        pdf.set_font("Arial", size=10)

        for linha in itens.split('\n'):
            if linha.strip():
                pdf.multi_cell(0, 5, txt=clean_text(linha))
        pdf.ln(5)

        # --- VALORES ---
        pdf.set_font("Arial", style="B", size=12)
        pdf.cell(190, 8, txt=clean_text(f"VALOR TOTAL: R$ {total:.2f}"), ln=True)
        pdf.set_font("Arial", size=11)
        pdf.cell(190, 6, txt=clean_text(f"Sinal para Reserva (30%): R$ {sinal:.2f}"), ln=True)
        pdf.cell(190, 6, txt=clean_text(f"Restante (Dia do Evento): R$ {restante:.2f}"), ln=True)

        # --- CLÁUSULAS JURÍDICAS ---
        pdf.ln(8)
        pdf.set_font("Arial", style="B", size=10)
        pdf.cell(190, 8, txt="TERMOS E CONDICOES GERAIS:", ln=True)

        pdf.set_font("Arial", size=8)
        clausulas = """
        1. DO OBJETO: O presente contrato tem como objeto a locação dos itens de decoração descritos acima, de propriedade da LOCADORA.

        2. DA RETIRADA E DEVOLUÇÃO: O LOCATÁRIO compromete-se a respeitar a janela de horários estipulada neste contrato para retirada e devolução.
           Parágrafo Único: Alterações nos horários de coleta e entrega podem ocorrer mediante combinado e aviso prévio. Atrasos não comunicados e não justificados poderão acarretar cobrança de nova diária.

        3. DA CONSERVAÇÃO E DANOS: O LOCATÁRIO assume total responsabilidade pela guarda e conservação das peças durante o período locado.
           3.1. Em caso de perda, quebra, rasgos ou manchas irreversíveis, o LOCATÁRIO deverá pagar o valor de reposição (preço de mercado) da peça imediatamente.

        4. DO PAGAMENTO E DESISTÊNCIA: A reserva só é garantida mediante pagamento do sinal. Em caso de cancelamento por parte do LOCATÁRIO, o valor do sinal NÃO será devolvido, retido a título de multa contratual para cobrir custos operacionais e reserva de data.

        5. DA LOGÍSTICA: Se a modalidade for "Pegue e Monte", o LOCATÁRIO deve prover transporte adequado (carro fechado/seguro). A LOCADORA não se responsabiliza por danos causados no transporte feito pelo cliente.

        6. FORO: As partes elegem o foro da comarca local para dirimir quaisquer dúvidas oriundas deste contrato.
        """
        pdf.multi_cell(0, 4, txt=clean_text(clausulas))

        # Assinaturas
        pdf.ln(15)
        pdf.cell(90, 0, "", "T")
        pdf.cell(10, 0, "")
        pdf.cell(90, 0, "", "T")
        pdf.ln(2)
        pdf.cell(90, 5, "NT FESTAS", align='C')
        pdf.cell(10, 5, "")
        pdf.cell(90, 5, clean_text(cliente), align='C')

        nome_arquivo = f"contrato_{cliente.replace(' ', '_')}.pdf"
        pdf.output(nome_arquivo)
        return nome_arquivo

    except Exception as e:
        print(f"--- ERRO PDF: {e} ---")
        raise e


def enviar_autentique(caminho_pdf, email_cliente):
    """Envia o PDF para a API e trata retorno com segurança."""

    # --- SEGURANÇA: Token vem das configurações ocultas ---
    try:
        TOKEN = st.secrets["AUTENTIQUE_TOKEN"]
    except:
        return False, "ERRO CONFIG: Token não encontrado no secrets.toml ou Settings do Streamlit."

    URL_API = "https://api.autentique.com.br/v2/graphql"

    query = """
    mutation CreateDocument($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {
      createDocument(document: $document, signers: $signers, file: $file) {
        signatures {
          link { short_link }
        }
      }
    }
    """
    variables = {
        "document": {"name": "Contrato de Locação - NT Festas"},
        "signers": [{"email": email_cliente, "action": "SIGN"}]
    }
    operations = {"query": query, "variables": variables}
    map_file = {"0": ["variables.file"]}

    try:
        with open(caminho_pdf, "rb") as f:
            response = requests.post(
                URL_API,
                data={"operations": json.dumps(operations), "map": json.dumps(map_file)},
                files={"0": f},
                headers={"Authorization": f"Bearer {TOKEN}"}
            )

        if response.status_code == 200:
            dados = response.json()
            if "errors" in dados and dados["errors"]:
                return False, f"Erro na API: {dados['errors'][0]['message']}"

            doc_data = dados.get("data", {}).get("createDocument")
            if doc_data:
                signatures = doc_data.get("signatures", [])
                link_encontrado = None
                for sig in signatures:
                    if sig.get("link") and sig["link"].get("short_link"):
                        link_encontrado = sig["link"]["short_link"]
                        break

                if link_encontrado:
                    return True, link_encontrado
                else:
                    return True, "EMAIL_ENVIADO"
            else:
                return False, "Erro: API não retornou confirmação."
        else:
            return False, f"Erro HTTP {response.status_code}"
    except Exception as e:
        return False, f"Erro Técnico: {e}"


# ==========================================
# 2. APLICAÇÃO STREAMLIT (FRONTEND)
# ==========================================

st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")

# --- DADOS ---
CATEGORIAS_TEMAS = {
    "Infantil Masculino": ["Vingadores", "Homem Aranha", "Grêmio", "Inter", "Futebol", "Patrulha Canina",
                           "Personalizado"],
    "Infantil Feminino": ["Moranguinho", "Branca de Neve", "Barbie", "Frozen", "Minnie", "Personalizado"],
    "Adulto Feminino": ["Floral", "Rose Gold", "De Repente 30", "Tardezinha", "Personalizado"],
    "Adulto Masculino": ["Boteco", "Preto e Prata", "Times", "Personalizado"],
    "Chá de Fralda": ["Ursinho Baloeiro", "Chuva de Amor", "Safári Baby", "Personalizado"],
    "Chá de Casa Nova": ["Coração", "Utensílios", "Personalizado"],
    "Corporativo": ["Cores da Empresa", "Natal", "Halloween", "Personalizado"]
}

ACERVO_COMPLETO = {
    "Trio de Cilindros (com capas)": 120.00,
    "Mesa Principal Retangular/Carroça": 150.00,
    "Trio de Mesas Sextavadas/Cubos": 120.00,
    "Mesa Auxiliar Pequena": 40.00,
    "Painel Redondo (Estrutura + Capa)": 80.00,
    "Painel Romano / Ripado": 100.00,
    "Painel Retangular / Muro Inglês": 90.00,
    "Arco de Ferro para Balões": 30.00,
    "Tapete Simples (Cor Única)": 30.00,
    "Tapete Premium (Sublimado/Grama/Pelúcia)": 50.00,
    "Display de Chão (Personagem MDF)": 20.00,
    "Kit Boleiras e Bandejas (10 peças)": 60.00,
    "Kit Boleiras e Bandejas (20 peças)": 100.00,
    "Vaso com Arranjo de Flores (Permanente)": 35.00,
    "Personagens de Mesa (Feltro/Biscoito/Resina) - Unid": 15.00,
    "Bolo Fake": 30.00,
    "Neon LED (Happy Birthday/Idade/Asas)": 80.00,
    "Iluminação Cênica (Refletor)": 25.00,
    "Número Led de Chão": 50.00
}

ESTRUTURA_KITS = {
    "Básico": {
        "preco": 280.00,
        "descricao": ["1 Mesa Principal ou 3 Cilindros com Capas", "1 Painel Redondo com Capa",
                      "10 Peças de Mesa (Boleiras/Bandejas)", "1 Tapete Simples"]
    },
    "Premium": {
        "preco": 450.00,
        "descricao": ["Trio de Cilindros + 1 Mesa Auxiliar", "Painel Duplo (Romano + Redondo)",
                      "Displayers de Chão e Mesa", "20 Peças de Mesa (Louças, Vasos, Flores)",
                      "Iluminação (Neon ou Refletor)", "Tapete Premium"]
    }
}

DETALHES_TEMAS = {
    "Vingadores": "Cores: Vermelho/Azul. Itens: Bonecos Feltro (Thor, Hulk), Prédios.",
    "Moranguinho": "Cores: Vermelho/Verde. Itens: Bonecas, Cestinha.",
    "Grêmio": "Cores: Azul/Preto/Branco. Itens: Taças, Bandeira.",
    "Barbie": "Cores: Rosa Pink. Itens: Silhueta Barbie, Bolsas."
}

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Custos Operacionais")
    preco_km = st.number_input("Custo KM", value=2.00, step=0.10)
    valor_hora = st.number_input("Valor Hora Técnica", value=50.00, step=5.00)
    taxa_higienizacao = st.number_input("Taxa Higienização", value=20.00)

# --- HEADER ---
st.title("🎈 Novo Orçamento: NT Festas")
st.markdown("---")

# --- INPUTS ---
col_cli1, col_cli2, col_cli3 = st.columns(3)
nome_cliente = col_cli1.text_input("Nome do Cliente")
data_evento = col_cli2.date_input("Data do Evento")
cidade = col_cli3.selectbox("Cidade", ["Esteio", "Canoas", "Sapucaia", "POA", "Outra"])

# --- TEMA ---
st.header("1. Estilo e Tema")
col_tema1, col_tema2 = st.columns(2)
categoria_sel = col_tema1.selectbox("Tipo de Festa", list(CATEGORIAS_TEMAS.keys()))
temas_disponiveis = CATEGORIAS_TEMAS[categoria_sel]
tema_sel = col_tema2.selectbox("Qual o Tema?", temas_disponiveis)

# --- KIT ---
st.header("2. Composição do Kit")
nivel_kit = st.radio("Selecione o Nível do Kit:", ["Básico", "Premium", "Montar Personalizado (Do Zero)"],
                     horizontal=True)

if nivel_kit == "Montar Personalizado (Do Zero)":
    st.markdown("### 🛠️ Monte o Kit Item por Item:")
    itens_selecionados_pers = st.multiselect("Acervo Completo:", options=list(ACERVO_COMPLETO.keys()))
    preco_base = sum([ACERVO_COMPLETO[i] for i in itens_selecionados_pers])
    itens_kit_descricao = itens_selecionados_pers
    valor_adicionais = 0.0
    itens_adicionais = []
else:
    dados_kit = ESTRUTURA_KITS[nivel_kit]
    preco_base = dados_kit["preco"]
    itens_kit_descricao = dados_kit["descricao"]
    st.info(f"📦 **Itens inclusos no {nivel_kit}:**")
    for item in itens_kit_descricao: st.markdown(f"- {item}")

    st.markdown("---")
    itens_adicionais = st.multiselect("Selecione itens avulsos:", list(ACERVO_COMPLETO.keys()))
    valor_adicionais = sum([ACERVO_COMPLETO[i] for i in itens_adicionais])

obs_alteracao = ""
if nivel_kit != "Montar Personalizado (Do Zero)":
    if st.checkbox("🔄 Houve troca de itens do padrão?"):
        obs_alteracao = st.text_input("Descreva a alteração:")

# --- LOGÍSTICA ---
st.header("3. Logística e Serviços")
tipo_entrega = st.radio("Logística:", ["Pegue e Monte", "Nós Levamos e Montamos"])
custo_frete = 0.0
custo_mao_obra = 0.0
custo_baloes = 0.0
desc_balao = ""

if tipo_entrega == "Nós Levamos e Montamos":
    c1, c2 = st.columns(2)
    dist = c1.number_input("Distância Ida (KM)", value=5)
    custo_frete = (dist * 4) * preco_km
    horas = c2.number_input("Horas Totais", value=3.0)
    custo_mao_obra = horas * valor_hora

if st.checkbox("Adicionar Balões ao Pedido?"):
    tipo_balao = st.selectbox("Tipo", ["Arco Simples", "Orgânico", "Orgânico Premium"])
    metros = st.slider("Metros", 2.0, 5.0, 2.5)
    tab_balao = {"Arco Simples": 40, "Orgânico": 80, "Orgânico Premium": 120}
    custo_baloes = metros * tab_balao[tipo_balao]
    desc_balao = f"Arte com Balões: {tipo_balao} ({metros}m)"

# --- TOTAIS ---
st.header("4. Fechamento e Valores")
total_bruto = preco_base + valor_adicionais + custo_frete + custo_mao_obra + custo_baloes + taxa_higienizacao
col_desc1, col_desc2 = st.columns([1, 3])
percentual_desconto = col_desc1.number_input("Aplicar Desconto (%)", 0.0, 100.0, 0.0, step=1.0)
valor_desconto = total_bruto * (percentual_desconto / 100)
total_liquido = total_bruto - valor_desconto
valor_sinal = total_liquido * 0.30
valor_restante = total_liquido - valor_sinal

# --- TEXTOS ---
detalhe_visual = DETALHES_TEMAS.get(tema_sel, f"Tema: {tema_sel}")
lista_final_texto = ""
if nivel_kit == "Montar Personalizado (Do Zero)":
    lista_final_texto += "- KIT PERSONALIZADO:\n"
    for i in itens_kit_descricao: lista_final_texto += f"  • {i}\n"
else:
    lista_final_texto += f"- ESTRUTURA {nivel_kit.upper()}:\n"
    for i in itens_kit_descricao: lista_final_texto += f"  • {i}\n"
    if obs_alteracao: lista_final_texto += f"⚠️ OBS: {obs_alteracao}\n"
    if itens_adicionais:
        lista_final_texto += "\n- ITENS ADICIONAIS:\n"
        for i in itens_adicionais: lista_final_texto += f"  • {i}\n"

texto_whats = f"""
*ORÇAMENTO NT FESTAS* 🎈
Olá *{nome_cliente}*!
Segue o orçamento para o tema *{tema_sel}*.
📅 Data: {data_evento} | 📍 {cidade}

*COMPOSIÇÃO:*
{detalhe_visual}
{lista_final_texto}
{f"- {desc_balao}" if custo_baloes > 0 else ""}

*SERVIÇOS:*
- Higienização e Embalagem
{f"- Frete e Logística" if custo_frete > 0 else "- Cliente retira e devolve (Pegue e Monte)"}
{f"- Montagem Profissional" if custo_mao_obra > 0 else ""}

-----------------------------
*VALOR TOTAL: R$ {total_liquido:.2f}*
{f"🎁 Desconto: - R$ {valor_desconto:.2f}" if valor_desconto > 0 else ""}
-----------------------------
💰 *PAGAMENTO:*
✅ Sinal (30%): R$ {valor_sinal:.2f}
✅ Restante: R$ {valor_restante:.2f}
"""

st.divider()
col_res1, col_res2 = st.columns([3, 2])
with col_res1:
    st.subheader("📲 Mensagem WhatsApp")
    st.code(texto_whats)
with col_res2:
    st.subheader("📋 Resumo")
    st.write(f"Kit: R$ {preco_base + valor_adicionais:.2f}")
    if custo_baloes > 0: st.write(f"Balões: R$ {custo_baloes:.2f}")
    st.success(f"### TOTAL: R$ {total_liquido:.2f}")

# ==========================================
# 3. GERAÇÃO E ENVIO DE CONTRATO
# ==========================================
st.markdown("---")
st.header("📝 Contrato e Documentação")

with st.expander("Gerenciar Contrato (Baixar ou Enviar)", expanded=True):
    st.info("Defina a janela de horários acordada com o cliente:")

    # --- JANELA DE RETIRADA ---
    st.markdown("**1. Retirada / Montagem**")
    c_dt1, c_hr1, c_hr2 = st.columns([2, 1, 1])
    dt_retirada = c_dt1.date_input("Data Retirada", value=data_evento)
    hr_ret_ini = c_hr1.time_input("Das", value=datetime.time(10, 0))
    hr_ret_fim = c_hr2.time_input("Até", value=datetime.time(11, 0))

    # --- JANELA DE DEVOLUÇÃO ---
    st.markdown("**2. Devolução / Coleta**")
    c_dt2, c_hr3, c_hr4 = st.columns([2, 1, 1])
    dt_devolucao = c_dt2.date_input("Data Devolução", value=data_evento + datetime.timedelta(days=1))
    hr_dev_ini = c_hr3.time_input("Das ", value=datetime.time(8, 0))
    hr_dev_fim = c_hr4.time_input("Até ", value=datetime.time(10, 0))

    str_retirada = f"{dt_retirada.strftime('%d/%m/%Y')} entre {hr_ret_ini.strftime('%H:%M')} e {hr_ret_fim.strftime('%H:%M')}"
    str_devolucao = f"{dt_devolucao.strftime('%d/%m/%Y')} entre {hr_dev_ini.strftime('%H:%M')} e {hr_dev_fim.strftime('%H:%M')}"

    st.markdown("---")

    col_btn_down, col_btn_send = st.columns(2)

    # LADO ESQUERDO: APENAS BAIXAR PDF
    with col_btn_down:
        st.subheader("⬇️ Apenas Baixar")
        st.caption("Gera o PDF para você imprimir ou conferir.")

        if st.button("📄 Gerar PDF Local"):
            if not nome_cliente:
                st.error("Preencha o nome do cliente no topo.")
            else:
                path_pdf = gerar_pdf(
                    nome_cliente, str(data_evento), cidade, lista_final_texto,
                    total_liquido, valor_sinal, valor_restante,
                    str_retirada, str_devolucao
                )

                with open(path_pdf, "rb") as f:
                    pdf_bytes = f.read()
                os.remove(path_pdf)

                st.success("PDF Gerado!")
                st.download_button(
                    label="💾 Clique aqui para Salvar o PDF",
                    data=pdf_bytes,
                    file_name=f"Contrato_{nome_cliente.replace(' ', '_')}.pdf",
                    mime="application/pdf"
                )

    # LADO DIREITO: ENVIAR PARA AUTENTIQUE
    with col_btn_send:
        st.subheader("🚀 Enviar para Assinatura")
        st.caption("Envia direto para o e-mail do cliente (Autentique).")
        email_assinatura = st.text_input("E-mail do Cliente:")

        if st.button("📧 Enviar via Autentique"):
            if not email_assinatura:
                st.error("Erro: E-mail obrigatório.")
            elif not nome_cliente:
                st.error("Erro: Preencha o nome do cliente no topo.")
            else:
                with st.spinner("Enviando..."):
                    path_pdf = gerar_pdf(
                        nome_cliente, str(data_evento), cidade, lista_final_texto,
                        total_liquido, valor_sinal, valor_restante,
                        str_retirada, str_devolucao
                    )

                    sucesso, resultado = enviar_autentique(path_pdf, email_assinatura)

                    if sucesso:
                        st.success("✅ Enviado!")
                        if resultado == "EMAIL_ENVIADO":
                            st.info(f"O contrato foi enviado para **{email_assinatura}**.")
                        elif "http" in resultado:
                            st.code(resultado)

                        if os.path.exists(path_pdf): os.remove(path_pdf)
                    else:
                        st.error(f"Falha: {resultado}")