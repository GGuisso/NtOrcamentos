import streamlit as st

st.set_page_config(page_title="Orçamento NT Festas", page_icon="🎈", layout="wide")

# --- 1. BANCO DE DADOS INTELIGENTE ---

# Categorias e seus Temas
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

# Definição do que vem em cada Nível de Kit
ESTRUTURA_KITS = {
    "Básico": {
        "preco": 280.00,
        "descricao": [
            "1 Mesa Principal ou 3 Cilindros com Capas do Tema",
            "1 Painel Redondo com Capa do Tema",
            "10 Peças de Mesa (Boleiras/Bandejas nas cores do tema)",
            "1 Tapete Simples"
        ]
    },
    "Premium": {
        "preco": 450.00,
        "descricao": [
            "Trio de Cilindros + 1 Mesa Auxiliar",
            "Painel Duplo (Romano + Redondo com Capas)",
            "Displayers de Chão e Mesa (Personagens)",
            "20 Peças de Mesa (Louças, Vasos com flores permanentes)",
            "Iluminação Cênica (Símbolo ou Neon simples)",
            "Tapete Premium ou Grama Sintética"
        ]
    },
    "Personalizado": {
        "preco": 0.00,  # Valor será definido manualmente ou por soma de itens
        "descricao": ["Montagem exclusiva conforme itens selecionados abaixo."]
    }
}

# Detalhes Específicos dos Temas
DETALHES_TEMAS = {
    "Vingadores": "Cores: Vermelho/Azul. Itens: Bonecos Feltro (Thor, Hulk), Prédios, Escudo Capitão América.",
    "Moranguinho": "Cores: Vermelho/Verde/Rosa. Itens: Bonecas Moranguinho, Cestinha de Morangos, Painel Jardim.",
    "Grêmio": "Cores: Azul/Preto/Branco. Itens: Taças, Lobo, Bandeira.",
    "Barbie": "Cores: Rosa Pink/Branco. Itens: Silhueta Barbie, Caixa Boneca, Bolsas decorativas."
}

# Itens Avulsos
ITENS_AVULSOS = {
    "Trio de Mesas Sextavadas": 120.00,
    "Neon LED": 80.00,
    "Painel Romano Extra": 100.00,
    "Arranjo de Flores Extra": 40.00,
    "Personagem Extra (Feltro/Resina)": 30.00,
    "Mesa de Madeira Maciça": 150.00
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

# Filtro em Cascata
categoria_sel = col_tema1.selectbox("Tipo de Festa", list(CATEGORIAS_TEMAS.keys()))
temas_disponiveis = CATEGORIAS_TEMAS[categoria_sel]
tema_sel = col_tema2.selectbox("Qual o Tema?", temas_disponiveis)

# --- PASSO 3: ESCOLHA DO KIT ---
st.header("2. Composição do Kit")

# Seleção do Nível
nivel_kit = st.radio("Selecione o Nível do Kit:", ["Básico", "Premium", "Montar Personalizado (Do Zero)"],
                     horizontal=True)

# Lógica de Preço e Descrição Base
if nivel_kit == "Montar Personalizado (Do Zero)":
    kit_base_nome = "Personalizado"
    preco_base = 0.00
    itens_kit_descricao = []
else:
    kit_base_nome = nivel_kit
    dados_kit = ESTRUTURA_KITS[nivel_kit]
    preco_base = dados_kit["preco"]
    itens_kit_descricao = dados_kit["descricao"]

# --- PASSO 4: PERSONALIZAÇÃO E ADICIONAIS ---
st.subheader("3. Personalização e Itens Extras")

col_custom1, col_custom2 = st.columns([2, 1])

with col_custom1:
    st.info(f"📦 **Itens Padrão do Kit {kit_base_nome}:**")

    # Se for personalizado do zero, não mostra lista padrão
    if kit_base_nome != "Personalizado":
        for item in itens_kit_descricao:
            st.markdown(f"- {item}")

    # Checkbox para alterar o padrão
    alterou_padrao = False
    obs_alteracao = ""
    if kit_base_nome != "Personalizado":
        alterar = st.checkbox("🔄 Cliente trocou algum item do padrão? (Ex: Mudou o tecido ou boleira)")
        if alterar:
            alterou_padrao = True
            obs_alteracao = st.text_input("Descreva a troca (Ex: Trocou capa vermelha por azul):")

    st.markdown("---")
    st.write("**Adicionar Itens Extras:**")
    itens_adicionais = st.multiselect("Selecione para somar ao valor:", list(ITENS_AVULSOS.keys()))

# Cálculo dos Adicionais
valor_adicionais = sum([ITENS_AVULSOS[i] for i in itens_adicionais])

with col_custom2:
    st.metric("Valor Base Kit", f"R$ {preco_base:.2f}")
    st.metric("Valor Adicionais", f"R$ {valor_adicionais:.2f}")

# --- PASSO 5: LOGÍSTICA ---
st.header("4. Logística e Serviços")
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

    # Balões
    if st.checkbox("Adicionar Balões?"):
        tipo_balao = st.selectbox("Tipo", ["Arco Simples", "Orgânico", "Orgânico Premium"])
        metros = st.slider("Metros", 2.0, 5.0, 2.5)
        tab_balao = {"Arco Simples": 40, "Orgânico": 80, "Orgânico Premium": 120}
        custo_baloes = metros * tab_balao[tipo_balao]
        desc_balao = f"Arte com Balões: {tipo_balao} ({metros}m)"

# --- CÁLCULO FINAL E PAGAMENTO ---
total_geral = preco_base + valor_adicionais + custo_frete + custo_mao_obra + custo_baloes + taxa_higienizacao

# Cálculos de Sinal e Restante
valor_sinal = total_geral * 0.30
valor_restante = total_geral - valor_sinal

# --- TEXTO INTELIGENTE PARA WHATSAPP ---

# Construindo a descrição detalhada do tema
detalhe_visual = DETALHES_TEMAS.get(tema_sel, f"Itens temáticos e cores do tema {tema_sel}.")

# Construindo a lista final de itens para o texto
lista_final_texto = ""

if kit_base_nome == "Personalizado":
    lista_final_texto += "- Montagem Exclusiva Personalizada\n"
else:
    lista_final_texto += f"- ESTRUTURA {kit_base_nome.upper()}:\n"
    for i in itens_kit_descricao:
        lista_final_texto += f"  • {i}\n"

if alterou_padrao:
    lista_final_texto += f"⚠️ ALTERAÇÃO: {obs_alteracao}\n"

if itens_adicionais:
    lista_final_texto += "\n- ITENS ADICIONAIS:\n"
    for i in itens_adicionais:
        lista_final_texto += f"  • {i}\n"

# Texto Final
texto_whats = f"""
*ORÇAMENTO NT FESTAS* 🎈
Olá *{nome_cliente}*! 
Confira os detalhes da sua festa com o tema *{tema_sel}*.

📅 Data: {data_evento} | 📍 {cidade}
🏷️ Categoria: {categoria_sel}

*COMPOSIÇÃO DO CENÁRIO:*
{detalhe_visual}

{lista_final_texto}
{f"- {desc_balao}" if custo_baloes > 0 else ""}

*SERVIÇOS:*
- Higienização das peças
{f"- Frete e Logística (Entrega/Retirada)" if custo_frete > 0 else "- Cliente retira e devolve (Pegue e Monte)"}
{f"- Montagem e Desmontagem Profissional" if custo_mao_obra > 0 else ""}

-----------------------------
*INVESTIMENTO TOTAL: R$ {total_geral:.2f}*
-----------------------------
💰 *FORMA DE PAGAMENTO:*
✅ Sinal de Reserva (30%): R$ {valor_sinal:.2f}
✅ Restante na data da festa: R$ {valor_restante:.2f}

Ficamos no aguardo!
"""

st.divider()
col_res1, col_res2 = st.columns([3, 2])

with col_res1:
    st.subheader("📲 Visualização da Mensagem")
    st.info("Clique no ícone de 'copiar' no canto superior direito da caixa abaixo 👇")
    # O componente st.code cria automaticamente o botão de copiar
    st.code(texto_whats, language="markdown")

with col_res2:
    st.success(f"TOTAL: R$ {total_geral:.2f}")
    st.write(f"Sinal (30%): R$ {valor_sinal:.2f}")
    st.write(f"Restante (70%): R$ {valor_restante:.2f}")
    st.markdown("---")
    st.caption(f"Lucro Aprox. (desc. var.): R$ {total_geral - (custo_frete/2) - (custo_baloes*0.3):.2f}")