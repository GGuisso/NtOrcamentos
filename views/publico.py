import streamlit as st
import pandas as pd
import time
import io
import urllib.parse
import os
from datetime import datetime
from services import PublicService, PixService, PDFGenerator
import segno


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
        return  # Para a execução aqui se já estiver tudo 100%

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
        data_evt_fmt = datetime.strptime(dados['data_evento'], '%Y-%m-%d').strftime('%d/%m/%Y')

        if tipo_log == "Pegue e Monte":
            # Tenta recuperar as datas e horas exatas do formulário
            d_ret = form.get('in_data_retirada', dados['data_evento'])
            h_ret_i = form.get('in_hora_ret_i')
            h_ret_f = form.get('in_hora_ret_f')

            d_dev = form.get('in_data_devolucao')
            h_dev_i = form.get('in_hora_dev_i')
            h_dev_f = form.get('in_hora_dev_f')

            # Formatação de datas
            try:
                fmt_d_ret = datetime.strptime(str(d_ret), '%Y-%m-%d').strftime('%d/%m/%Y')
                fmt_d_dev = datetime.strptime(str(d_dev), '%Y-%m-%d').strftime('%d/%m/%Y') if d_dev else "Dia seguinte"
            except:
                fmt_d_ret = data_evt_fmt
                fmt_d_dev = "Dia seguinte"

            # Formatação de horas (corta segundos)
            def clean_time(t):
                return str(t)[:5] if t else "??"

            c_ag1, c_ag2 = st.columns(2)

            txt_retirada_display = f"{fmt_d_ret} entre {clean_time(h_ret_i)} e {clean_time(h_ret_f)}" if h_ret_i else "A combinar"
            txt_devolucao_display = f"{fmt_d_dev} entre {clean_time(h_dev_i)} e {clean_time(h_dev_f)}" if h_dev_i else "A combinar"

            c_ag1.write(f"**📤 Retirada:**\n{txt_retirada_display}")
            c_ag2.write(f"**📥 Devolução:**\n{txt_devolucao_display}")

            st.warning("⚠️ Transporte, montagem e desmontagem por conta do cliente.")
        else:
            st.metric("Logística", "Entrega e Montagem pela NT Festas")
            st.caption("Horários a combinar com a equipe.")
            txt_retirada_display = f"{data_evt_fmt} (Horário a combinar)"
            txt_devolucao_display = "Dia seguinte (Horário a combinar)"

    # --- GALERIA DE ITENS ---
    st.markdown("### 🎁 Itens Selecionados")

    # Cria cards visuais para os itens
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

    # --- PREPARAÇÃO DO PDF ---
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

    # --- FLUXO DE APROVAÇÃO ---
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
            msg_zap = f"Olá, vi o orçamento de R$ {subtotal} mas preciso alterar algumas coisas."
            link_zap = f"https://api.whatsapp.com/send?phone=55{st.secrets.get('ZAP_ADMIN', '')}&text={urllib.parse.quote(msg_zap)}"
            st.link_button("Falar no WhatsApp", link_zap, use_container_width=True)

        if c_btn1.button("✅ APROVAR AGORA", type="primary", disabled=not aceite):
            with st.spinner("Registrando aceite..."):
                # ALTERAÇÃO: Agora desempacota o erro
                ok, msg_erro = PublicService.registrar_aceite(dados['id'], "IP_CLIENTE_MOBILE")
                if ok:
                    st.rerun()  # Recarrega para mostrar o Pix
                else:
                    st.error(f"Erro ao registrar: {msg_erro}")

    # --- TELA DE PAGAMENTO PIX ---
    elif status == "Aguardando Pagamento":
        st.markdown("---")
        st.subheader("🚀 Falta pouco! Faça o Pix do Sinal")

        # Dados do Pix (Pega do Secrets ou usa Default)
        chave_pix = st.secrets.get("PIX_KEY", "seu_email@teste.com")
        nome_pix = st.secrets.get("PIX_NAME", "NT FESTAS")
        cidade_pix = st.secrets.get("PIX_CITY", "Porto Alegre")

        # Gera o Código
        payload_copia_cola = PixService.gerar_payload_pix(chave_pix, nome_pix, cidade_pix, sinal)

        # Gera QR Code Imagem
        qr = segno.make_qr(payload_copia_cola)
        buffer = io.BytesIO()
        qr.save(buffer, kind='png', scale=5)

        c_pix1, c_pix2 = st.columns([1, 2])
        with c_pix1:
            st.image(buffer, caption="Escaneie no App do Banco")

        with c_pix2:
            st.info("Copie o código abaixo e use a opção **'Pix Copia e Cola'** no seu banco:")
            st.code(payload_copia_cola, language="text")

        st.markdown("---")
        st.write("### 📤 Já pagou?")

        msg_comprovante = f"Olá! Acabei de pagar o sinal de R$ {sinal:.2f} do orçamento {dados['cliente_nome']}."
        link_zap_comp = f"https://api.whatsapp.com/send?phone=55{st.secrets.get('ZAP_ADMIN', '')}&text={urllib.parse.quote(msg_comprovante)}"

        st.link_button("📱 Enviar Comprovante no WhatsApp", link_zap_comp, type="primary", use_container_width=True)

        # --- Botão Download PDF ---
        st.markdown("---")
        try:
            pdf_path = PDFGenerator.gerar(pdf_dados_cli, pdf_dados_evt, itens_texto, subtotal, sinal, restante,
                                          txt_retirada_display, txt_devolucao_display)
            with open(pdf_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
            os.remove(pdf_path)

            st.download_button(
                label="📄 BAIXAR CONTRATO (PDF)",
                data=pdf_bytes,
                file_name=f"Contrato_{dados['id']}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao gerar PDF: {e}")