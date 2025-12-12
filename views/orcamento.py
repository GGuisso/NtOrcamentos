# ARQUIVO: views/orcamento.py
import streamlit as st
import datetime
import time
import os
import urllib.parse
from datetime import date
from services import GoogleSheetsService, InventoryService, CepService, PDFGenerator, EmailService
from views.componentes import reset_form_state


def render_area_contrato(dados_cli, dados_evt, itens, total, sinal, restante):
    st.header("📝 Contrato e Documentação")
    with st.expander("Gerenciar Contrato (Baixar ou Enviar)"):
        st.info("Janela de horários:")
        c1, c2, c3 = st.columns([2, 1, 1])
        d_ret = c1.date_input("Retirada", value=datetime.datetime.strptime(dados_evt['data'], '%Y-%m-%d').date())
        h_ret_i = c2.time_input("Das", value=datetime.time(10, 0))
        h_ret_f = c3.time_input("Até", value=datetime.time(11, 0))

        c4, c5, c6 = st.columns([2, 1, 1])
        d_dev = c4.date_input("Devolução", value=datetime.datetime.strptime(dados_evt['data'],
                                                                            '%Y-%m-%d').date() + datetime.timedelta(
            days=1))
        h_dev_i = c5.time_input("Das ", value=datetime.time(8, 0))
        h_dev_f = c6.time_input("Até ", value=datetime.time(10, 0))

        txt_ret = f"{d_ret.strftime('%d/%m/%Y')} entre {h_ret_i.strftime('%H:%M')} e {h_ret_f.strftime('%H:%M')}"
        txt_dev = f"{d_dev.strftime('%d/%m/%Y')} entre {h_dev_i.strftime('%H:%M')} e {h_dev_f.strftime('%H:%M')}"

        st.markdown("---")
        b_down, b_send = st.columns(2)
        with b_down:
            if st.button("📄 Gerar PDF Local"):
                if not dados_cli['nome']:
                    st.error("Nome obrigatório")
                else:
                    f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret, txt_dev)
                    with open(f_path, "rb") as f:
                        st.download_button("💾 Baixar PDF", f, file_name=f_path)
                    os.remove(f_path)
        with b_send:
            email = st.text_input("E-mail do Cliente:")
            if st.button("📧 Enviar via Autentique"):
                if not email or not dados_cli['nome']:
                    st.error("Preencha e-mail e nome.")
                else:
                    with st.spinner("Enviando..."):
                        f_path = PDFGenerator.gerar(dados_cli, dados_evt, itens, total, sinal, restante, txt_ret,
                                                    txt_dev)
                        ok, res = EmailService.enviar_contrato(f_path, email)
                        if ok:
                            st.success("Enviado!" if res == "EMAIL_ENVIADO" else "Enviado! Link gerado.")
                            if "http" in res: st.code(res)
                            if os.path.exists(f_path): os.remove(f_path)
                        else:
                            st.error(res)


def render_form_orcamento(acervo, categorias, kits, detalhes, estoque_dict):
    bloqueado = False
    status_atual = "Novo"

    if st.session_state['edit_id']:
        orc_atual = next(
            (x for x in st.session_state['db_orcamentos'] if str(x['id']) == str(st.session_state['edit_id'])), None)
        if orc_atual:
            status_atual = orc_atual['status']
            if status_atual not in ["Aguardando", "Novo"]:
                bloqueado = True
                st.warning(f"🔒 Este orçamento está **{status_atual.upper()}** e não pode ser editado.")
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

    def _buscar_cep_cli():
        res = CepService.consultar(st.session_state.get("in_cli_cep", ""))
        if res:
            st.session_state["in_cli_rua"] = res.get("logradouro", "")
            st.session_state["in_cli_bairro"] = res.get("bairro", "")
            st.session_state["in_cli_cidade"] = res.get("localidade", "")
            st.toast("Endereço do cliente encontrado!", icon="📍")
        elif st.session_state.get("in_cli_cep"):
            st.toast("CEP inválido.", icon="⚠️")

    def _buscar_cep_evt():
        res = CepService.consultar(st.session_state.get("in_evt_cep", ""))
        if res:
            st.session_state["in_evt_rua"] = res.get("logradouro", "")
            st.session_state["in_evt_bairro"] = res.get("bairro", "")
            st.session_state["in_evt_cidade"] = res.get("localidade", "")
            st.toast("Endereço do evento encontrado!", icon="📍")
        elif st.session_state.get("in_evt_cep"):
            st.toast("CEP inválido.", icon="⚠️")

    def _copiar_endereco():
        if st.session_state.get("chk_mesmo_end"):
            st.session_state["in_evt_cep"] = st.session_state.get("in_cli_cep", "")
            st.session_state["in_evt_rua"] = st.session_state.get("in_cli_rua", "")
            st.session_state["in_evt_num"] = st.session_state.get("in_cli_num", "")
            st.session_state["in_evt_bairro"] = st.session_state.get("in_cli_bairro", "")
            st.session_state["in_evt_cidade"] = st.session_state.get("in_cli_cidade", "")

    st.subheader("👤 Dados do Cliente")
    col_c1, col_c2, col_c3 = st.columns([2, 1, 1])
    nome = col_c1.text_input("Nome Completo", key="in_nome", disabled=bloqueado)
    cpf = col_c2.text_input("CPF", key="in_cpf", disabled=bloqueado)
    celular = col_c3.text_input("WhatsApp (com DDD)", key="in_telefone", disabled=bloqueado)

    col_ce1, col_ce2, col_ce3, col_ce4, col_ce5 = st.columns([1, 2, 1, 1.5, 1.5])
    cep_cli = col_ce1.text_input("CEP Cli.", key="in_cli_cep", on_change=_buscar_cep_cli, disabled=bloqueado)
    rua_cli = col_ce2.text_input("Rua", key="in_cli_rua", disabled=bloqueado)
    num_cli = col_ce3.text_input("Nº", key="in_cli_num", disabled=bloqueado)
    bairro_cli = col_ce4.text_input("Bairro", key="in_cli_bairro", disabled=bloqueado)
    cid_cli = col_ce5.text_input("Cidade", key="in_cli_cidade", disabled=bloqueado)

    st.subheader("📍 Local do Evento")
    col_ev0, col_ev_dup = st.columns([2, 1])
    data_evt = col_ev0.date_input("Data do Evento", value=date.today(), key="in_data", disabled=bloqueado)
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
        st.markdown("### 🛠️ Monte o Kit Item por Item:")
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

    if not bloqueado:
        itens_verificar = itens_pers + itens_add
        avisos_estoque = []

        # --- OTIMIZAÇÃO: Geração única do mapa de ocupação ---
        mapa_ocupacao = InventoryService.calcular_mapa_ocupacao(st.session_state['db_orcamentos'])

        for it in itens_verificar:
            qtd_total = estoque_dict.get(it, 0)

            # Uso da verificação rápida via mapa
            usados_dia, saldo = InventoryService.verificar_disponibilidade_rapida(
                it, str(data_evt), qtd_total, mapa_ocupacao
            )

            # Ajuste se estiver editando o próprio orçamento
            if st.session_state['edit_id']:
                saldo += 1
                usados_dia = max(0, usados_dia - 1)

            if saldo <= 0:
                avisos_estoque.append(
                    f"⚠️ **{it}:** Você tem {qtd_total}, mas {usados_dia} já estão alugados neste dia.")
        if avisos_estoque:
            st.warning("🚨 **ALERTA DE ESTOQUE (Overbooking):**\n" + "\n".join(avisos_estoque))

    obs_alt = ""
    if nivel != "Montar Personalizado (Do Zero)" and st.checkbox("🔄 Houve troca de itens?", key="in_check_obs",
                                                                 disabled=bloqueado):
        obs_alt = st.text_input("Descreva a alteração:", key="in_obs", disabled=bloqueado)

    st.subheader("3. Logística e Serviços")
    frete, mao_obra, dist, horas = 0.0, 0.0, 0.0, 0.0
    tipo_entrega = st.radio("Logística:", ["Pegue e Monte", "Nós Levamos e Montamos"], key="in_entrega",
                            disabled=bloqueado)
    if tipo_entrega == "Nós Levamos e Montamos":
        c1, c2 = st.columns(2)
        dist = c1.number_input("Distância Ida (KM)", value=5.0, key="in_dist", disabled=bloqueado)
        horas = c2.number_input("Horas Totais", value=3.0, key="in_horas", disabled=bloqueado)
        frete = (dist * 4) * st.session_state['cfg_km']
        mao_obra = horas * st.session_state['cfg_hora']

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

    txt_itens = f"- KIT PERSONALIZADO:\n" if nivel == "Montar Personalizado (Do Zero)" else f"- ESTRUTURA {nivel.upper()}:\n"
    for i in itens_desc: txt_itens += f"  • {i}\n"
    if obs_alt: txt_itens += f"⚠️ OBS: {obs_alt}\n"
    if itens_add:
        txt_itens += "\n- ITENS ADICIONAIS:\n"
        for i in itens_add: txt_itens += f"  • {i}\n"

    texto_whats = f"""
*ORÇAMENTO NT FESTAS* 🎈
Olá *{nome}*! Segue o orçamento para o tema *{tema_sel}*.
📅 Data: {data_evt}
📍 Local: {rua_evt}, {num_evt} - {cid_evt}

*COMPOSIÇÃO:*
{detalhes.get(tema_sel, f"Tema: {tema_sel}")}
{txt_itens}
{f"- {desc_balao}" if custo_baloes > 0 else ""}

*SERVIÇOS:*
- Higienização e Embalagem
{f"- Frete e Logística" if frete > 0 else "- Cliente retira e devolve (Pegue e Monte)"}
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
            st.link_button("🚀 Enviar no WhatsApp", link_zap, type="secondary")
        else:
            st.warning("Preencha o WhatsApp do cliente para habilitar o envio.")

        if not bloqueado:
            def _salvar():
                if not nome:
                    st.session_state['feedback_msg'] = ("error", "Preencha o nome do cliente.")
                    return
                novo_id = int(time.time())
                orcamento = {
                    "id": st.session_state['edit_id'] or novo_id,
                    "data_registro": str(datetime.date.today()),
                    "status": "Aguardando Aprovação" if not st.session_state['edit_id'] else status_atual,
                    "cliente": nome,
                    "data_evento": str(data_evt),
                    "cidade": cid_evt,
                    "tema": tema_sel,
                    "total": liquido,
                    "dados_form": {k: st.session_state[k] for k in st.session_state if
                                   k.startswith('in_') or k == 'in_data'}
                }
                with st.spinner("Salvando na nuvem..."):
                    GoogleSheetsService.upsert_orcamento(orcamento)

                db = st.session_state['db_orcamentos']
                if st.session_state['edit_id']:
                    db = [orcamento if str(o['id']) == str(orcamento['id']) else o for o in db]
                    msg = "Orçamento atualizado!"
                else:
                    db.append(orcamento)
                    msg = "Novo orçamento criado!"

                st.session_state['db_orcamentos'] = db
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