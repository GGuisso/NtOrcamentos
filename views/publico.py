# views/publico.py
import streamlit as st
import io
import urllib.parse
import os
from datetime import datetime
import segno

# Importa serviços da nova pasta modularizada
from services import PublicService, PixService, PDFGenerator
# Importa as configurações centralizadas (Novo padrão)
from services.config import PIX_KEY, PIX_NAME, PIX_CITY, get_secret


def render_view_publica():
    # 1. Pega o UUID da URL
    try:
        uuid_param = st.query_params.get("proposta_id")
    except:
        uuid_param = None

    if not uuid_param:
        st.error("Link inválido ou expirado.")
        return

    # 2. Busca dados (Sem Login)
    dados = PublicService.buscar_orcamento_uuid(uuid_param)

    if not dados:
        st.error("Orçamento não encontrado.")
        return

    form = dados.get('dados_form', {})

    # CSS para esconder a sidebar e deixar visual limpo (Mobile First)
    st.markdown("""
        <style>
            #MainMenu {visibility: hidden;}
            header {visibility: hidden;}
            [data-testid="stSidebar"] {display: none;}
            .block-container {padding-top: 2rem; padding-bottom: 5rem;}
            .stButton button {width: 100%; border-radius: 25px; font-weight: bold; height: 3em;}
        </style>
    """, unsafe_allow_html=True)

    # --- CABEÇALHO ---
    c_logo, c_info = st.columns([1, 3])
    with c_logo:
        st.write("🎈 **NT Festas**")
    with c_info:
        st.caption(f"Olá, {dados['cliente_nome'].split()[0]}!")
        st.subheader(f"Sua Festa: {datetime.strptime(dados['data_evento'], '%Y-%m-%d').strftime('%d/%m/%Y')}")

    st.divider()

    # --- STATUS ---
    status = dados['status']
    if status == "Aguardando Pagamento":
        st.success("✅ Orçamento Aprovado! Aguardando Sinal.")
    elif status == "Reserva Confirmada":
        st.balloons()
        st.success("🎉 Reserva Confirmada! Tudo certo para sua festa.")
        # Opcional: retornar aqui se quiser esconder os detalhes após confirmado
        # return

    # --- LOCAL E LOGÍSTICA ---
    st.markdown("### 📍 Dados do Evento")
    rua = form.get('in_evt_rua', '')
    num = form.get('in_evt_num', '')
    bairro = form.get('in_evt_bairro', '')
    cidade = form.get('in_evt_cidade', '')
    st.info(f"**Local:** {rua}, {num} - {bairro}, {cidade}")

    with st.container(border=True):
        st.markdown("**🗓️ AGENDAMENTO**")

        tipo_log = form.get('in_entrega', 'Pegue e Monte')
        try:
            data_evt_fmt = datetime.strptime(dados['data_evento'], '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            data_evt_fmt = "Data a definir"

        if tipo_log == "Pegue e Monte":
            d_ret = form.get('in_data_retirada', dados['data_evento'])
            h_ret_i = form.get('in_hora_ret_i')
            h_ret_f = form.get('in_hora_ret_f')

            d_dev = form.get('in_data_devolucao')
            h_dev_i = form.get('in_hora_dev_i')
            h_dev_f = form.get('in_hora_dev_f')

            # Helpers de formatação
            def fmt_date(d):
                try:
                    return datetime.strptime(str(d)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
                except:
                    return data_evt_fmt

            def clean_time(t):
                return str(t)[:5] if t else "??"

            c_ag1, c_ag2 = st.columns(2)

            txt_ret = f"{fmt_date(d_ret)} entre {clean_time(h_ret_i)} e {clean_time(h_ret_f)}" if h_ret_i else "A combinar"
            txt_dev = f"{fmt_date(d_dev)} entre {clean_time(h_dev_i)} e {clean_time(h_dev_f)}" if h_dev_i else "A combinar"

            c_ag1.write(f"**📤 Retirada:**\n{txt_ret}")
            c_ag2.write(f"**📥 Devolução:**\n{txt_dev}")
            st.warning("⚠️ Transporte e montagem por conta do cliente.")
        else:
            st.metric("Logística", "Entrega e Montagem pela NT Festas")
            st.caption("Horários a combinar com a equipe.")
            txt_ret = f"{data_evt_fmt} (Horário a combinar)"
            txt_dev = "Dia seguinte (Horário a combinar)"

    # --- GALERIA DE ITENS ---
    st.markdown("### 🎁 Itens Selecionados")
    for item in dados['itens']:
        with st.container(border=True):
            ci1, ci2 = st.columns([1, 3])
            with ci1:
                if item['foto']:
                    st.image(item['foto'], use_container_width=True)
                else:
                    st.write("🖼️")
            with ci2:
                st.write(f"**{item['qtd']}x {item['nome']}**")

    # --- TOTAIS ---
    st.divider()
    subtotal = dados['total']
    sinal = subtotal * 0.30
    restante = subtotal * 0.70

    c_t1, c_t2 = st.columns([2, 1])
    c_t1.write("Valor Total:")
    c_t2.write(f"**R$ {subtotal:.2f}**")
    st.info(f"💰 **Sinal para Reserva (30%): R$ {sinal:.2f}**")

    # --- PDF HELPERS ---
    pdf_dados_cli = {
        "nome": dados['cliente_nome'],
        "cpf": dados.get('cliente_cpf', ''),
        "cep": form.get('in_cli_cep', ''),
        "rua": form.get('in_cli_rua', ''),
        "numero": form.get('in_cli_num', ''),
        "bairro": form.get('in_cli_bairro', ''),
        "cidade": form.get('in_cli_cidade', '')
    }
    pdf_dados_evt = {
        "data": data_evt_fmt,
        "cep": form.get('in_evt_cep', ''),
        "rua": rua, "numero": num, "bairro": bairro, "cidade": cidade
    }
    itens_texto = "\n".join([f"- {i['qtd']}x {i['nome']}" for i in dados['itens']])

    # --- AÇÕES (ACEITE / PIX) ---
    if status in ["Novo", "Aguardando Aprovação", "Rascunho"]:
        st.write("### 📝 Termos e Aceite")
        with st.expander("📄 Ler Contrato de Locação e Regras"):
            st.markdown("""
            **1. DA CONSERVAÇÃO:** O locatário declara receber os itens em perfeito estado.
            **2. DAS AVARIAS:** Em caso de quebra, será cobrado o valor de reposição.
            **3. DO PAGAMENTO:** A reserva só é garantida mediante comprovante do sinal (30%).
            **4. CANCELAMENTO:** O valor do sinal não é reembolsável em caso de desistência a menos de 7 dias.
            """)

        aceite = st.checkbox("Li e concordo com os termos acima.")
        c_btn1, c_btn2 = st.columns(2)

        if c_btn2.button("❌ Pedir Alteração"):
            # Usa get_secret para buscar o ZAP_ADMIN
            zap_admin = get_secret('ZAP_ADMIN')
            msg_zap = f"Olá, vi o orçamento de R$ {subtotal} mas preciso alterar algumas coisas."
            link_zap = f"https://api.whatsapp.com/send?phone=55{zap_admin}&text={urllib.parse.quote(msg_zap)}"
            st.link_button("Falar no WhatsApp", link_zap, use_container_width=True)

        if c_btn1.button("✅ APROVAR AGORA", type="primary", disabled=not aceite):
            with st.spinner("Registrando aceite..."):
                ok, msg_erro = PublicService.registrar_aceite(dados['id'], "IP_VIA_STREAMLIT")
                if ok:
                    st.rerun()
                else:
                    st.error(f"Erro: {msg_erro}")

    elif status == "Aguardando Pagamento":
        st.markdown("---")
        st.subheader("🚀 Falta pouco! Faça o Pix do Sinal")

        # Geração do Pix com as chaves centralizadas
        if not PIX_KEY:
            st.error("Chave Pix não configurada no sistema.")
        else:
            payload_copia_cola = PixService.gerar_payload_pix(
                chave_pix=PIX_KEY,
                beneficiario_nome=PIX_NAME,
                beneficiario_cidade=PIX_CITY,
                valor=sinal
            )

            # QR Code
            qr = segno.make_qr(payload_copia_cola)
            buffer = io.BytesIO()
            qr.save(buffer, kind='png', scale=5)

            c_pix1, c_pix2 = st.columns([1, 2])
            with c_pix1:
                st.image(buffer, caption="Escaneie no App do Banco")
            with c_pix2:
                st.info("Copie o código abaixo e use a opção **'Pix Copia e Cola'**:")
                st.code(payload_copia_cola, language="text")

        st.markdown("---")
        st.write("### 📤 Já pagou?")

        zap_admin = get_secret('ZAP_ADMIN')
        msg_comp = f"Olá! Acabei de pagar o sinal de R$ {sinal:.2f} do orçamento {dados['cliente_nome']}."
        link_zap_comp = f"https://api.whatsapp.com/send?phone=55{zap_admin}&text={urllib.parse.quote(msg_comp)}"
        st.link_button("📱 Enviar Comprovante", link_zap_comp, type="primary", use_container_width=True)

        # Botão PDF (apenas disponível aqui no Streamlit, pois a API removeu essa feature para ficar leve)
        st.markdown("---")
        try:
            pdf_path = PDFGenerator.gerar(
                pdf_dados_cli, pdf_dados_evt, itens_texto, subtotal, sinal, restante, txt_ret, txt_dev
            )
            with open(pdf_path, "rb") as pdf_file:
                st.download_button(
                    label="📄 BAIXAR CONTRATO (PDF)",
                    data=pdf_file,
                    file_name=f"Contrato_{dados['id']}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            os.remove(pdf_path)
        except Exception as e:
            st.warning(f"PDF indisponível no momento: {e}")