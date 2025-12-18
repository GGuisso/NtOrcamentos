import streamlit as st
import datetime
import time
import os
import urllib.parse
from datetime import date
from collections import Counter
from services import SupabaseService, InventoryService, CepService, PDFGenerator, EmailService
from views.componentes import reset_form_state


def render_area_contrato(dados_cli, dados_evt, itens, total, sinal, restante):
    st.header("📝 Contrato e Documentação")

    # --- ÁREA DO LINK PÚBLICO ---
    orc_id = st.session_state.get('edit_id')

    if orc_id:
        orc_atual = next((x for x in st.session_state.get('db_orcamentos', []) if x['id'] == orc_id), None)

        if orc_atual:
            uuid_str = orc_atual.get('link_uuid')
            status_atual = orc_atual.get('status')

            if uuid_str:
                with st.container(border=True):
                    st.subheader("🔗 Link de Aprovação Online (Novo)")
                    st.caption("Envie este link para o cliente ver as fotos, aprovar os termos e pagar o Pix.")

                    base_url = st.secrets.get("BASE_URL", "http://localhost:8501")
                    link_final = f"{base_url}/?proposta_id={uuid_str}"

                    st.code(link_final, language="text")

                    primeiro_nome = dados_cli['nome'].split()[0] if dados_cli['nome'] else "Cliente"
                    msg_zap = f"Olá {primeiro_nome}! 🎈\nSegue o link do seu orçamento para aprovação e pagamento do sinal:\n\n{link_final}"

                    celular = st.session_state.get('in_telefone', '')
                    if celular:
                        nums = "".join([c for c in celular if c.isdigit()])
                        link_zap_btn = f"https://api.whatsapp.com/send?phone=55{nums}&text={urllib.parse.quote(msg_zap)}"
                        st.link_button("🚀 Enviar Link no WhatsApp", link_zap_btn, type="primary",
                                       use_container_width=True)
                    else:
                        st.warning("Preencha o WhatsApp do cliente para habilitar o envio.")

                    if status_atual == "Aguardando Pagamento":
                        st.info("🕒 O cliente já aprovou os termos! Aguardando Pix.")
                    elif status_atual == "Reserva Confirmada":
                        st.success("✅ Tudo certo! Reserva confirmada.")
            else:
                st.info("Salve o orçamento novamente para gerar o Link Público.")

    st.markdown("---")

    # --- PDF LEGACY ---
    with st.expander("📄 Gerar PDF Clássico (Legacy)"):
        # Garante que a data seja um objeto date para formatação
        try:
            raw_date = dados_evt['data']
            if isinstance(raw_date, str):
                d_evt_obj = datetime.datetime.strptime(raw_date[:10], '%Y-%m-%d').date()
            else:
                d_evt_obj = raw_date
        except:
            d_evt_obj = date.today()

        txt_ret = st.session_state.get('txt_retirada_final', f"{d_evt_obj.strftime('%d/%m/%Y')} (Horário a combinar)")
        txt_dev = st.session_state.get('txt_devolucao_final', f"Dia seguinte (Horário a combinar)")

        st.write(f"**Retirada:** {txt_ret}")
        st.write(f"**Devolução:** {txt_dev}")

        b_down, b_send = st.columns(2)
        with b_down:
            if st.button("💾 Baixar PDF Local"):
                if not dados_cli['nome']:
                    st.error("Nome obrigatório")
                else:
                    f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret, txt_dev)
                    with open(f_path, "rb") as f:
                        st.download_button("📥 Download", f, file_name=f"Contrato_{dados_cli['nome']}.pdf")
                    os.remove(f_path)
        with b_send:
            email_cadastro = st.session_state.get('in_email', '')
            st.text_input("E-mail do Cliente (Do Cadastro):", value=email_cadastro, disabled=True)

            if st.button("📧 Enviar via Autentique"):
                if not email_cadastro or not dados_cli['nome']:
                    st.error("Preencha o e-mail no formulário.")
                else:
                    with st.spinner("Enviando..."):
                        f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret,
                                                    txt_dev)
                        ok, res = EmailService.enviar_contrato(f_path, email_cadastro)
                        if ok:
                            st.success("Enviado!" if res == "EMAIL_ENVIADO" else "Enviado! Link gerado.")
                            if "http" in res: st.code(res)
                            if os.path.exists(f_path): os.remove(f_path)
                        else:
                            st.error(res)


def render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict):
    st.header("📝 Novo Orçamento")

    bloqueado = False
    status_atual = "Novo"

    if st.session_state['edit_id']:
        orc_atual = next(
            (x for x in st.session_state.get('db_orcamentos', []) if str(x['id']) == str(st.session_state['edit_id'])),
            None)

        if orc_atual:
            status_atual = orc_atual['status']
            STATUS_EDITAVEIS = ["Novo", "Aguardando Aprovação", "Rascunho", "Aguardando Pagamento"]

            if status_atual not in STATUS_EDITAVEIS:
                bloqueado = True
                st.warning(f"🔒 Este orçamento está **{status_atual.upper()}**.")
            else:
                st.info(f"✏️ Editando orçamento #{st.session_state['edit_id']} (Status: {status_atual})")

        c1, c2 = st.columns(2)
        c1.button("🔙 Voltar ao Histórico",
                  on_click=lambda: (setattr(st.session_state, 'edit_id', None), reset_form_state(),
                                    setattr(st.session_state, 'navegacao_atual', "📂 Histórico de Orçamentos")),
                  use_container_width=True)

        def _duplicar():
            st.session_state['edit_id'] = None
            st.session_state['feedback_msg'] = ("success", "Dados copiados para novo orçamento.")

        c2.button("📑 Usar como base (Duplicar)", on_click=_duplicar, use_container_width=True)
        st.markdown("---")

    # --- HELPERS DE DATA/HORA BLINDADOS (CORREÇÃO DO ERRO) ---
    def safe_date(key, default):
        """
        Garante que o valor na sessão seja um objeto Date.
        Se for String (vindo do banco), converte e ATUALIZA a sessão para evitar erro do Streamlit.
        """
        val = st.session_state.get(key)

        # Se não existe ou é nulo, usa o default
        if not val:
            return default

        # Se já é objeto Date ou Datetime
        if isinstance(val, (datetime.date, datetime.datetime)):
            if isinstance(val, datetime.datetime):
                d = val.date()
                if key in st.session_state: st.session_state[key] = d  # Corrige datetime -> date
                return d
            return val

        # Se for string, converte e salva na sessão
        if isinstance(val, str):
            try:
                # Pega apenas os 10 primeiros chars (YYYY-MM-DD) ignorando hora se houver
                d = datetime.datetime.strptime(val[:10], '%Y-%m-%d').date()
                st.session_state[key] = d  # <--- ISSO CORRIGE O ERRO DE TYPEERROR
                return d
            except:
                return default
        return default

    def safe_time(key, default):
        """Mesma lógica blindada para Time"""
        val = st.session_state.get(key)
        if not val: return default

        if isinstance(val, (datetime.time, datetime.datetime)):
            if isinstance(val, datetime.datetime):
                t = val.time()
                if key in st.session_state: st.session_state[key] = t
                return t
            return val

        if isinstance(val, str):
            try:
                # Tenta HH:MM:SS
                t = datetime.datetime.strptime(val, '%H:%M:%S').time()
                st.session_state[key] = t
                return t
            except:
                try:
                    # Tenta HH:MM
                    t = datetime.datetime.strptime(val, '%H:%M').time()
                    st.session_state[key] = t
                    return t
                except:
                    return default
        return default

    def _buscar_cep_cli():
        res = CepService.consultar(st.session_state.get("in_cli_cep", ""))
        if res:
            st.session_state["in_cli_rua"] = res.get("logradouro", "")
            st.session_state["in_cli_bairro"] = res.get("bairro", "")
            st.session_state["in_cli_cidade"] = res.get("localidade", "")
            st.toast("Endereço encontrado!", icon="📍")

    def _buscar_cep_evt():
        res = CepService.consultar(st.session_state.get("in_evt_cep", ""))
        if res:
            st.session_state["in_evt_rua"] = res.get("logradouro", "")
            st.session_state["in_evt_bairro"] = res.get("bairro", "")
            st.session_state["in_evt_cidade"] = res.get("localidade", "")
            st.toast("Endereço encontrado!", icon="📍")

    def _copiar_endereco():
        if st.session_state.get("chk_mesmo_end"):
            st.session_state["in_evt_cep"] = st.session_state.get("in_cli_cep", "")
            st.session_state["in_evt_rua"] = st.session_state.get("in_cli_rua", "")
            st.session_state["in_evt_num"] = st.session_state.get("in_cli_num", "")
            st.session_state["in_evt_bairro"] = st.session_state.get("in_cli_bairro", "")
            st.session_state["in_evt_cidade"] = st.session_state.get("in_cli_cidade", "")

    def _autocompletar_cliente():
        cpf_input = st.session_state.get('in_cpf', '').strip()
        nome_input = st.session_state.get('in_nome', '').strip()
        clientes_encontrados = []
        if cpf_input:
            clientes_encontrados = SupabaseService.buscar_clientes(cpf_input, por_cpf=True)
        elif nome_input:
            clientes_encontrados = SupabaseService.buscar_clientes(nome_input, por_cpf=False)

        if len(clientes_encontrados) == 1:
            c = clientes_encontrados[0]
            st.session_state['in_nome'] = c.get('nome', '')
            st.session_state['in_cpf'] = c.get('cpf', '')
            st.session_state['in_telefone'] = c.get('telefone', '')
            st.session_state['in_email'] = c.get('email', '')
            nasc_db = c.get('data_nascimento')
            if nasc_db:
                try:
                    st.session_state['in_nascimento'] = datetime.datetime.strptime(nasc_db, '%Y-%m-%d').date()
                except:
                    st.session_state['in_nascimento'] = None
            st.session_state['in_cli_cep'] = c.get('cep', '')
            st.session_state['in_cli_rua'] = c.get('logradouro', '')
            st.session_state['in_cli_num'] = c.get('numero', '')
            st.session_state['in_cli_bairro'] = c.get('bairro', '')
            st.session_state['in_cli_cidade'] = c.get('cidade', '')
            st.toast(f"Cliente {c['nome']} carregado!", icon="✅")

    st.subheader("👤 Dados do Cliente")
    col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
    nome = col_c1.text_input("Nome Completo", key="in_nome", disabled=bloqueado, on_change=_autocompletar_cliente)
    cpf = col_c2.text_input("CPF", key="in_cpf", disabled=bloqueado, on_change=_autocompletar_cliente)
    celular = col_c3.text_input("WhatsApp", key="in_telefone", disabled=bloqueado)

    col_c4, col_c5 = st.columns([2, 1])
    col_c4.text_input("E-mail", key="in_email", placeholder="exemplo@email.com", disabled=bloqueado)
    nasc_val = safe_date('in_nascimento', None)
    col_c5.date_input("Data Nascimento", value=nasc_val, min_value=date(1900, 1, 1), max_value=date.today(),
                      key="in_nascimento", format="DD/MM/YYYY", disabled=bloqueado)

    col_ce1, col_ce2, col_ce3, col_ce4, col_ce5 = st.columns([1, 2, 1, 1.5, 1.5])
    cep_cli = col_ce1.text_input("CEP Cli.", key="in_cli_cep", on_change=_buscar_cep_cli, disabled=bloqueado)
    rua_cli = col_ce2.text_input("Rua", key="in_cli_rua", disabled=bloqueado)
    num_cli = col_ce3.text_input("Nº", key="in_cli_num", disabled=bloqueado)
    bairro_cli = col_ce4.text_input("Bairro", key="in_cli_bairro", disabled=bloqueado)
    cid_cli = col_ce5.text_input("Cidade", key="in_cli_cidade", disabled=bloqueado)

    st.subheader("📍 Local do Evento")
    col_ev0, col_ev_dup = st.columns([2, 1])
    data_evt_val = safe_date('in_data', date.today())
    data_evt = col_ev0.date_input("Data do Evento", value=data_evt_val, key="in_data", disabled=bloqueado)
    usar_mesmo_end = col_ev_dup.checkbox("🏠 Mesmo endereço do cliente?", key="chk_mesmo_end",
                                         on_change=_copiar_endereco, disabled=bloqueado)

    col_ev1, col_ev2, col_ev3, col_ev4, col_ev5 = st.columns([1, 2, 1, 1.5, 1.5])
    cep_evt = col_ev1.text_input("CEP Evt.", key="in_evt_cep", on_change=_buscar_cep_evt, disabled=bloqueado)
    rua_evt = col_ev2.text_input("Rua", key="in_evt_rua", disabled=bloqueado)
    num_evt = col_ev3.text_input("Nº", key="in_evt_num", disabled=bloqueado)
    bairro_evt = col_ev4.text_input("Bairro", key="in_evt_bairro", disabled=bloqueado)
    cid_evt = col_ev5.text_input("Cidade", key="in_evt_cidade", disabled=bloqueado)

    st.markdown("---")
    c_tm1, c_tm2 = st.columns(2)
    cat_sel = c_tm1.selectbox("Tipo de Festa", list(categorias.keys()) if categorias else ["Vazio"], key="in_categoria",
                              disabled=bloqueado)
    tema_sel = c_tm2.selectbox("Qual o Tema?", categorias.get(cat_sel, ["Vazio"]), key="in_tema", disabled=bloqueado)

    st.subheader("Composição do Kit")
    opcoes_kits = list(kits.keys()) + ["Montar Personalizado (Do Zero)"]
    nivel = st.radio("Selecione o Nível do Kit:", opcoes_kits, horizontal=True, key="in_kit", disabled=bloqueado)

    itens_pers, itens_desc, preco_base = [], [], 0.0
    if nivel == "Montar Personalizado (Do Zero)":
        itens_pers = st.multiselect("Acervo Completo:", list(acervo.keys()), key="in_itens_pers", disabled=bloqueado)
        preco_base = sum(acervo.get(i, 0) for i in itens_pers)
        itens_desc = itens_pers
    else:
        dados_kit = kits.get(nivel, {"preco": 0.0, "descricao": ["Kit não encontrado"]})
        preco_base, itens_desc = dados_kit["preco"], dados_kit["descricao"]
        st.info(f"📦 **Itens inclusos no {nivel}:**")
        for i in itens_desc: st.markdown(f"- {i}")
        st.markdown("---")

    itens_add = st.multiselect("Selecione itens avulsos:", list(acervo.keys()), key="in_itens_add", disabled=bloqueado)
    val_add = sum(acervo.get(i, 0) for i in itens_add)

    # --- VERIFICAÇÃO DE ESTOQUE ---
    if not bloqueado:
        itens_para_validar = []
        itens_para_validar.extend(itens_pers)
        itens_para_validar.extend(itens_add)
        if nivel != "Montar Personalizado (Do Zero)" and nivel in kits:
            desc_kit = kits[nivel]["descricao"]
            for d in desc_kit:
                partes_item = d.split('x ', 1)
                if len(partes_item) > 1:
                    try:
                        qtd_k = int(partes_item[0])
                        nome_k = partes_item[1].strip()
                    except:
                        qtd_k = 1
                        nome_k = d.strip()
                else:
                    qtd_k = 1
                    nome_k = d.strip()
                itens_para_validar.extend([nome_k] * qtd_k)

        avisos_estoque = []
        mapa_ocupacao = InventoryService.calcular_mapa_ocupacao(st.session_state.get('db_orcamentos', []))
        contagem_necessaria = Counter(itens_para_validar)

        for it, qtd_nec in contagem_necessaria.items():
            qtd_total = estoque_dict.get(it, 0)
            usados_dia = mapa_ocupacao.get(str(data_evt), {}).get(it, 0)
            disponivel = qtd_total - usados_dia
            if disponivel < 0: disponivel = 0
            if disponivel < qtd_nec:
                avisos_estoque.append(f"⚠️ **{it}:** Precisa de {qtd_nec}, mas só tem {disponivel} livres.")

        if avisos_estoque:
            st.error("🚨 **ALERTA DE ESTOQUE:**\n" + "\n".join(avisos_estoque))

    obs_alt = ""
    if nivel != "Montar Personalizado (Do Zero)" and st.checkbox("🔄 Houve troca de itens?", key="in_check_obs",
                                                                 disabled=bloqueado):
        obs_alt = st.text_input("Descreva a alteração:", key="in_obs", disabled=bloqueado)

    st.subheader("3. Logística e Serviços")

    tipo_entrega = st.radio("Logística:", ["Pegue e Monte", "Nós Levamos e Montamos"], key="in_entrega",
                            disabled=bloqueado)

    frete, mao_obra, dist, horas = 0.0, 0.0, 0.0, 0.0

    # --- LOGICA DE HORARIOS ---
    # Inicializa variáveis
    txt_ret_whats = ""
    txt_dev_whats = ""

    if tipo_entrega == "Pegue e Monte":
        st.info("📅 Agendamento de Retirada e Devolução")

        # Garante que os valores para os componentes sejam OBJETOS DE DATA e HORA, nunca string
        d_ret_val = safe_date('in_data_retirada', data_evt)
        h_ret_i_val = safe_time('in_hora_ret_i', datetime.time(10, 0))
        h_ret_f_val = safe_time('in_hora_ret_f', datetime.time(11, 0))

        d_dev_val = safe_date('in_data_devolucao', data_evt + datetime.timedelta(days=1))
        h_dev_i_val = safe_time('in_hora_dev_i', datetime.time(9, 0))
        h_dev_f_val = safe_time('in_hora_dev_f', datetime.time(10, 0))

        c_r1, c_r2, c_r3 = st.columns([1.5, 1, 1])
        c_r1.date_input("📤 Data Retirada", value=d_ret_val, key="in_data_retirada", disabled=bloqueado)
        c_r2.time_input("Entre", value=h_ret_i_val, key="in_hora_ret_i", disabled=bloqueado)
        c_r3.time_input("E as", value=h_ret_f_val, key="in_hora_ret_f", disabled=bloqueado)

        c_d1, c_d2, c_d3 = st.columns([1.5, 1, 1])
        c_d1.date_input("📥 Data Devolução", value=d_dev_val, key="in_data_devolucao", disabled=bloqueado)
        c_d2.time_input("Entre", value=h_dev_i_val, key="in_hora_dev_i", disabled=bloqueado)
        c_d3.time_input("E as", value=h_dev_f_val, key="in_hora_dev_f", disabled=bloqueado)

        # Formata string apenas para exibição (WhatsApp e PDF)
        txt_retirada = f"{d_ret_val.strftime('%d/%m/%Y')} entre {h_ret_i_val.strftime('%H:%M')} e {h_ret_f_val.strftime('%H:%M')}"
        txt_devolucao = f"{d_dev_val.strftime('%d/%m/%Y')} entre {h_dev_i_val.strftime('%H:%M')} e {h_dev_f_val.strftime('%H:%M')}"

        st.session_state['txt_retirada_final'] = txt_retirada
        st.session_state['txt_devolucao_final'] = txt_devolucao

        txt_ret_whats = f"📤 Retirada: {txt_retirada}"
        txt_dev_whats = f"📥 Devolução: {txt_devolucao}"

    elif tipo_entrega == "Nós Levamos e Montamos":
        c1, c2 = st.columns(2)
        dist = c1.number_input("Distância Ida (KM)", value=5.0, key="in_dist", disabled=bloqueado)
        horas = c2.number_input("Horas Totais", value=3.0, key="in_horas", disabled=bloqueado)
        frete = (dist * 4) * st.session_state['cfg_km']
        mao_obra = horas * st.session_state['cfg_hora']

        st.session_state['txt_retirada_final'] = "Entrega pela NT Festas (Horário a combinar)"
        st.session_state['txt_devolucao_final'] = "Retirada pela NT Festas (Horário a combinar)"
        txt_ret_whats = "🚚 Logística: Entrega e Montagem pela NT Festas"

    custo_baloes, desc_balao = 0.0, ""
    if st.checkbox("Adicionar Balões?", key="in_check_balao", disabled=bloqueado):
        tipo_b = st.selectbox("Tipo", ["Arco Simples", "Orgânico", "Orgânico Premium"], key="in_tipo_balao",
                              disabled=bloqueado)
        metros = st.slider("Metros", 2.0, 5.0, 2.5, key="in_metros", disabled=bloqueado)
        custo_baloes = metros * {"Arco Simples": 40, "Orgânico": 80, "Orgânico Premium": 120}[tipo_b]
        desc_balao = f"Arte com Balões: {tipo_b} ({metros}m)"

    st.subheader("4. Fechamento e Valores")
    taxa_hig = st.session_state['cfg_taxa']
    bruto = preco_base + val_add + frete + mao_obra + custo_baloes + taxa_hig

    c_d1, c_d2 = st.columns([1, 3])
    perc_desc = c_d1.number_input("Aplicar Desconto (%)", 0.0, 100.0, 0.0, step=1.0, key="in_desc_perc",
                                  disabled=bloqueado)
    val_desc = bruto * (perc_desc / 100)
    liquido = bruto - val_desc
    sinal, restante = liquido * 0.30, liquido * 0.70

    # Montagem do Texto de WhatsApp (CORRIGIDO: INCLUI AS DATAS DE LOGÍSTICA)
    txt_itens = f"- KIT {nivel}:\n" if nivel != "Montar Personalizado (Do Zero)" else "- PERSONALIZADO:\n"
    for i in itens_desc: txt_itens += f"  • {i}\n"
    if itens_add: txt_itens += "\n- ITENS ADICIONAIS:\n" + "\n".join([f"  • {i}" for i in itens_add])

    texto_whats = f"""
*ORÇAMENTO NT FESTAS* 🎈
Olá *{nome}*! Segue o orçamento para o tema *{tema_sel}*.
📅 Data do Evento: {data_evt.strftime('%d/%m/%Y')}
📍 Local: {rua_evt}, {num_evt} - {cid_evt}

*LOGÍSTICA E HORÁRIOS:*
{txt_ret_whats}
{txt_dev_whats}

*COMPOSIÇÃO:*
{txt_itens}
{f"- {desc_balao}" if custo_baloes > 0 else ""}

*SERVIÇOS:*
- Higienização e Embalagem
{f"- Frete e Logística" if frete > 0 else ""}
{f"- Montagem Profissional" if mao_obra > 0 else ""}

-----------------------------
*VALOR TOTAL: R$ {liquido:.2f}*
{f"🎁 Desconto: - R$ {val_desc:.2f}" if val_desc > 0 else ""}
-----------------------------
💰 *PAGAMENTO:*
✅ Sinal (30%): R$ {sinal:.2f}
✅ Restante: R$ {restante:.2f}
"""

    c_res1, c_res2 = st.columns([3, 2])
    with c_res1:
        st.subheader("📲 Mensagem WhatsApp")
        st.code(texto_whats)
        if celular:
            nums = "".join([c for c in celular if c.isdigit()])
            msg_encoded = urllib.parse.quote(texto_whats)
            link_zap = f"https://api.whatsapp.com/send?phone=55{nums}&text={msg_encoded}"
            st.link_button("🚀 Enviar Rascunho no WhatsApp", link_zap, type="secondary")

        if not bloqueado:
            def _salvar():
                if not nome:
                    st.session_state['feedback_msg'] = ("error", "Preencha o nome do cliente.")
                    return
                novo_id = int(time.time())
                v_itens = preco_base + val_add + custo_baloes
                v_servicos = frete + mao_obra + taxa_hig

                dados_snapshot = {k: st.session_state[k] for k in st.session_state if
                                  k.startswith('in_') or k == 'in_data'}

                orcamento = {
                    "id": st.session_state['edit_id'] or novo_id,
                    "data_registro": str(datetime.date.today()),
                    "status": status_atual if st.session_state['edit_id'] else "Aguardando Aprovação",
                    "cliente": nome,
                    "data_evento": str(data_evt),
                    "cidade": cid_evt,
                    "tema": tema_sel,
                    "total": liquido,
                    "valor_itens": v_itens,
                    "valor_servicos": v_servicos,
                    "valor_desconto": val_desc,
                    "dados_form": dados_snapshot
                }
                with st.spinner("Salvando na nuvem..."):
                    SupabaseService.upsert_orcamento(orcamento)

                st.session_state['db_orcamentos'] = SupabaseService.carregar_orcamentos()
                msg = "Orçamento atualizado!" if st.session_state['edit_id'] else "Novo orçamento criado!"
                st.session_state['feedback_msg'] = ("success", msg)
                st.session_state['edit_id'] = None
                reset_form_state()

            st.button("💾 SALVAR ORÇAMENTO NO SISTEMA", type="primary", on_click=_salvar)

    with c_res2:
        st.subheader("📋 Demonstrativo")
        with st.container(border=True):
            st.caption("📦 ITENS E KITS")

            def linha_resumo(texto, valor, destaque=False):
                c1, c2 = st.columns([3, 1])
                c1.write(texto)
                if destaque:
                    c2.markdown(f"**R$ {valor:.2f}**")
                else:
                    c2.write(f"R$ {valor:.2f}")

            linha_resumo("Base do Kit", preco_base)
            if val_add: linha_resumo("Itens Extras", val_add)
            if custo_baloes: linha_resumo("Balões", custo_baloes)
            st.markdown("---")
            st.caption("🛠️ TAXAS E SERVIÇOS")
            cs1, cs2, cs3 = st.columns(3)
            cs1.markdown(f"<small>Higienização</small><br>**R$ {taxa_hig:.2f}**", unsafe_allow_html=True)
            cs2.markdown(f"<small>Frete</small><br>**R$ {frete:.2f}**", unsafe_allow_html=True)
            cs3.markdown(f"<small>Montagem</small><br>**R$ {mao_obra:.2f}**", unsafe_allow_html=True)
            st.markdown("---")
            c_tot1, c_tot2 = st.columns([3, 2])
            c_tot1.write("Subtotal:")
            c_tot2.write(f"**R$ {bruto:.2f}**")
            if val_desc:
                c_tot1.write("Desconto:")
                c_tot2.markdown(f":red[- R$ {val_desc:.2f}]")
            st.write("")
            st.success(f"### TOTAL: R$ {liquido:.2f}")

    st.markdown("---")
    dados_cli_pdf = {"nome": nome, "cpf": cpf, "cep": cep_cli, "rua": rua_cli, "numero": num_cli, "bairro": bairro_cli,
                     "cidade": cid_cli}
    dados_evt_pdf = {"data": str(data_evt), "cep": cep_evt, "rua": rua_evt, "numero": num_evt, "bairro": bairro_evt,
                     "cidade": cid_evt}
    render_area_contrato(dados_cli_pdf, dados_evt_pdf, txt_itens, liquido, sinal, restante)