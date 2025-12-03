import streamlit as st

st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")

# --- 1. BANCO DE DADOS INTELIGENTE ---

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

# --- LISTA MESTRA DE PREÇOS ---
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
        "descricao": [
            "1 Mesa Principal ou 3 Cilindros com Capas",
            "1 Painel Redondo com Capa",
            "10 Peças de Mesa (Boleiras/Bandejas)",
            "1 Tapete Simples"
        ]
    },
    "Premium": {
        "preco": 450.00,
        "descricao": [
            "Trio de Cilindros + 1 Mesa Auxiliar",
            "Painel Duplo (Romano + Redondo)",
            "Displayers de Chão e Mesa",
            "20 Peças de Mesa (Louças, Vasos, Flores)",
            "Iluminação (Neon ou Refletor)",
            "Tapete Premium"
        ]
    }
}

DETALHES_TEMAS = {
    "Vingadores": "Cores: Vermelho/Azul. Itens: Bonecos Feltro (Thor, Hulk), Prédios.",
    "Moranguinho": "Cores: Vermelho/Verde. Itens: Bonecas, Cestinha.",
    "Grêmio": "Cores: Azul/Preto/Branco. Itens: Taças, Bandeira.",
    "Barbie": "Cores: Rosa Pink. Itens: Silhueta Barbie, Bolsas."
}

# --- BARRA LATERAL (CUSTOS) ---
with st.sidebar:
    st.header("⚙️ Custos Operacionais")
    preco_km = st.number_input("Custo KM", value=2.00, step=0.10)
    valor_hora = st.number_input("Valor Hora Técnica", value=50.00, step=5.00)
    taxa_higienizacao = st.number_input("Taxa Higienização", value=20.00)

# --- TÍTULO ---
st.title("🎈 Novo Orçamento: NT Festas")
st.markdown("---")

# --- PASSO 1: O CLIENTE ---
col_cli1, col_cli2, col_cli3 = st.columns(3)
nome_cliente = col_cli1.text_input("Nome do Cliente")
data_evento = col_cli2.date_input("Data do Evento")
cidade = col_cli3.selectbox("Cidade", ["Esteio", "Canoas", "Sapucaia", "POA", "Outra"])

# --- PASSO 2: DEFINIÇÃO DO TEMA ---
st.header("1. Estilo e Tema")
col_tema1, col_tema2 = st.columns(2)
categoria_sel = col_tema1.selectbox("Tipo de Festa", list(CATEGORIAS_TEMAS.keys()))
temas_disponiveis = CATEGORIAS_TEMAS[categoria_sel]
tema_sel = col_tema2.selectbox("Qual o Tema?", temas_disponiveis)

# --- PASSO 3: ESCOLHA DO KIT ---
st.header("2. Composição do Kit")

nivel_kit = st.radio("Selecione o Nível do Kit:", ["Básico", "Premium", "Montar Personalizado (Do Zero)"],
                     horizontal=True)

if nivel_kit == "Montar Personalizado (Do Zero)":
    st.markdown("### 🛠️ Monte o Kit Item por Item:")
    itens_selecionados_pers = st.multiselect(
        "Acervo Completo:",
        options=list(ACERVO_COMPLETO.keys()),
        placeholder="Clique para adicionar peças..."
    )
    preco_base = sum([ACERVO_COMPLETO[i] for i in itens_selecionados_pers])
    itens_kit_descricao = itens_selecionados_pers
    valor_adicionais = 0.0
    itens_adicionais = []

else:
    kit_base_nome = nivel_kit
    dados_kit = ESTRUTURA_KITS[nivel_kit]
    preco_base = dados_kit["preco"]
    itens_kit_descricao = dados_kit["descricao"]

    st.info(f"📦 **Itens inclusos no {nivel_kit}:**")
    for item in itens_kit_descricao:
        st.markdown(f"- {item}")

    st.markdown("---")
    st.write("**Deseja adicionar itens extras ao kit padrão?**")
    itens_adicionais = st.multiselect("Selecione itens avulsos:", list(ACERVO_COMPLETO.keys()))
    valor_adicionais = sum([ACERVO_COMPLETO[i] for i in itens_adicionais])

obs_alteracao = ""
if nivel_kit != "Montar Personalizado (Do Zero)":
    if st.checkbox("🔄 Houve troca de itens do padrão? (Ex: Cor da capa)"):
        obs_alteracao = st.text_input("Descreva a alteração:")

# --- PASSO 5: LOGÍSTICA ---
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

    horas = c2.number_input("Horas Totais (Montar+Desmontar)", value=3.0)
    custo_mao_obra = horas * valor_hora

st.markdown("### 🎈 Arte com Balões")
if st.checkbox("Adicionar Balões ao Pedido?"):
    if tipo_entrega == "Pegue e Monte":
        st.warning("⚠️ Atenção: Certifique-se de que o arco montado cabe no veículo de retirada.")

    tipo_balao = st.selectbox("Tipo", ["Arco Simples", "Orgânico", "Orgânico Premium"])
    metros = st.slider("Metros", 2.0, 5.0, 2.5)
    tab_balao = {"Arco Simples": 40, "Orgânico": 80, "Orgânico Premium": 120}
    custo_baloes = metros * tab_balao[tipo_balao]
    desc_balao = f"Arte com Balões: {tipo_balao} ({metros}m)"

# --- CÁLCULO FINAL E DESCONTO ---
st.header("4. Fechamento e Valores")

# Somatório Bruto
total_bruto = preco_base + valor_adicionais + custo_frete + custo_mao_obra + custo_baloes + taxa_higienizacao

# Campo de Desconto
col_desc1, col_desc2 = st.columns([1, 3])
percentual_desconto = col_desc1.number_input("Aplicar Desconto (%)", 0.0, 100.0, 0.0, step=1.0)
valor_desconto = total_bruto * (percentual_desconto / 100)

total_liquido = total_bruto - valor_desconto
valor_sinal = total_liquido * 0.30
valor_restante = total_liquido - valor_sinal

# --- GERAÇÃO DO TEXTO ---
detalhe_visual = DETALHES_TEMAS.get(tema_sel, f"Tema: {tema_sel}")

lista_final_texto = ""
if nivel_kit == "Montar Personalizado (Do Zero)":
    lista_final_texto += "- KIT PERSONALIZADO (ITENS SELECIONADOS):\n"
    for i in itens_kit_descricao:
        lista_final_texto += f"  • {i}\n"
else:
    lista_final_texto += f"- ESTRUTURA {nivel_kit.upper()}:\n"
    for i in itens_kit_descricao:
        lista_final_texto += f"  • {i}\n"
    if obs_alteracao:
        lista_final_texto += f"⚠️ OBS: {obs_alteracao}\n"
    if itens_adicionais:
        lista_final_texto += "\n- ITENS ADICIONAIS:\n"
        for i in itens_adicionais:
            lista_final_texto += f"  • {i}\n"

# Inserção do Desconto no Texto
linha_desconto = ""
if valor_desconto > 0:
    linha_desconto = f"\n🎁 *Desconto Especial ({percentual_desconto:.0f}%):* - R$ {valor_desconto:.2f}"

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
{f"- Montagem Profissional no Local" if custo_mao_obra > 0 else ""}

-----------------------------
*VALOR TOTAL: R$ {total_liquido:.2f}*
{linha_desconto}
-----------------------------
💰 *PAGAMENTO:*
✅ Sinal Reserva (30%): R$ {valor_sinal:.2f}
✅ Restante na data: R$ {valor_restante:.2f}

Ficamos no aguardo!
"""

st.divider()
col_res1, col_res2 = st.columns([3, 2])

with col_res1:
    st.subheader("📲 Mensagem WhatsApp")
    st.code(texto_whats, language="markdown")

with col_res2:
    st.subheader("📋 Resumo Detalhado")

    # Detalhamento Visual dos Custos
    st.write(f"📦 **Kit e Peças:** R$ {preco_base + valor_adicionais:.2f}")
    if custo_baloes > 0:
        st.write(f"🎈 **Balões:** R$ {custo_baloes:.2f}")

    st.markdown("---")
    st.write("**Serviços Operacionais:**")
    st.write(f"🧹 Higienização: R$ {taxa_higienizacao:.2f}")
    if custo_frete > 0:
        st.write(f"🚚 Frete: R$ {custo_frete:.2f}")
    if custo_mao_obra > 0:
        st.write(f"👷‍♀️ Montagem: R$ {custo_mao_obra:.2f}")

    st.markdown("---")

    if valor_desconto > 0:
        st.write(f"Subtotal: R$ {total_bruto:.2f}")
        st.error(f"Desconto ({percentual_desconto:.0f}%): - R$ {valor_desconto:.2f}")

    st.success(f"### TOTAL FINAL: R$ {total_liquido:.2f}")