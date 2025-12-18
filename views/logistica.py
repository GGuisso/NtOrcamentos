import streamlit as st
import pandas as pd
from datetime import date, timedelta
from services import InventoryService, SupabaseService


def render_logistica():
    st.header("🚚 Logística & Expedição")

    # Mantém estado da seleção (apenas para o Picking List Geral que é rascunho)
    if "picking_state" not in st.session_state:
        st.session_state["picking_state"] = {}

    tab_exp, tab_dev = st.tabs(["📤 Separação (Picking List)", "📥 Retorno & Avarias"])

    db_orcamentos = st.session_state.get('db_orcamentos', [])
    tenant = st.session_state.get('tenant_id')

    # ==============================================================================
    # ABA 1: EXPEDIÇÃO
    # ==============================================================================
    with tab_exp:
        c1, c2 = st.columns([2, 2])
        d_inicio = c1.date_input("De:", value=date.today())
        d_fim = c2.date_input("Até:", value=date.today() + timedelta(days=3))

        orcamentos_periodo = [
            o for o in db_orcamentos
            if o.get('status') in ['Reserva Confirmada', 'Itens Retirados']
               and d_inicio <= pd.to_datetime(o['data_evento']).date() <= d_fim
        ]

        if not orcamentos_periodo:
            st.info("Nenhuma festa confirmada para este período.")
        else:
            resumo_total, lista_clientes = InventoryService.gerar_picking_list(orcamentos_periodo, tenant)

            # --- RESUMO TOTAL (Apenas visualização para coleta no galpão) ---
            st.markdown("---")
            st.subheader(f"📦 Resumo Total ({len(orcamentos_periodo)} Festas)")
            st.caption("Lista consolidada para retirar do estoque (Rascunho).")

            if resumo_total:
                df_resumo = pd.DataFrame(list(resumo_total.items()), columns=["Item", "Qtd Total"])
                df_resumo = df_resumo.sort_values(by="Item")

                # Checkbox apenas visual (não salva no banco o resumo, pois ele é dinâmico)
                df_resumo["Coletado?"] = df_resumo["Item"].map(
                    lambda x: st.session_state["picking_state"].get(x, False)
                )

                df_editado = st.data_editor(
                    df_resumo,
                    column_config={
                        "Coletado?": st.column_config.CheckboxColumn(required=True),
                        "Qtd Total": st.column_config.NumberColumn(format="%d un")
                    },
                    hide_index=True,
                    width="stretch",
                    disabled=["Item", "Qtd Total"],
                    key="editor_picking_total"
                )

                if not df_editado.empty:
                    novos_status = dict(zip(df_editado["Item"], df_editado["Coletado?"]))
                    st.session_state["picking_state"].update(novos_status)

            # --- ROMANEIO INDIVIDUAL (SALVO NO BANCO) ---
            st.markdown("---")
            st.subheader("👤 Separação por Cliente (Romaneio)")
            st.caption("As marcações abaixo são salvas automaticamente no banco de dados.")

            for pedido in lista_clientes:
                cor_log = "🔵" if "Levamos" in pedido['logistica'] else "🟠"

                # Verifica progresso
                total_itens = len(pedido['itens'])
                itens_marcados = sum(
                    1 for k, v in pedido['picking_saved'].items() if v is True and k in pedido['itens'])
                progresso = f"({itens_marcados}/{total_itens})"
                check_icon = "✅" if itens_marcados == total_itens and total_itens > 0 else "⏳"

                titulo = f"{check_icon} {pedido['data']} | {pedido['cliente']} {progresso}"

                with st.expander(titulo):
                    st.write(f"**Logística:** {pedido['logistica']}")
                    if "Levamos" in pedido['logistica']:
                        st.write(f"📍 **Endereço:** {pedido['endereco']}")
                        st.link_button("🗺️ Abrir no Maps",
                                       f"https://www.google.com/maps/search/?api=1&query={pedido['endereco']}")

                    st.markdown("#### Checklist:")

                    # Layout em colunas
                    cols = st.columns(3)
                    idx = 0

                    # Função de callback para salvar imediatamente ao clicar
                    def atualizar_db(oid=pedido['id'], current_dict=pedido['picking_saved']):
                        # Recria o dict com base nos session_states dos checkboxes
                        novo_estado = current_dict.copy()
                        for key in st.session_state:
                            if key.startswith(f"chk_{oid}_"):
                                item_name = key.replace(f"chk_{oid}_", "")
                                novo_estado[item_name] = st.session_state[key]

                        InventoryService.atualizar_picking_status(oid, novo_estado)

                        # Atualiza o cache local para refletir na UI instantaneamente
                        for o in st.session_state['db_orcamentos']:
                            if o['id'] == oid:
                                o['picking_status'] = novo_estado

                    for item, qtd in pedido['itens'].items():
                        # Recupera estado do banco
                        ja_marcado = pedido['picking_saved'].get(item, False)

                        cols[idx % 3].checkbox(
                            f"{qtd}x {item}",
                            value=ja_marcado,
                            key=f"chk_{pedido['id']}_{item}",
                            on_change=atualizar_db
                        )
                        idx += 1

    # ==============================================================================
    # ABA 2: RETORNO
    # ==============================================================================
    with tab_dev:
        st.subheader("Conferência de Devolução")
        st.info("Listando eventos ocorridos nos últimos 7 dias.")

        data_corte = date.today() - timedelta(days=7)
        orcamentos_retorno = [
            o for o in db_orcamentos
            if pd.to_datetime(o['data_evento']).date() >= data_corte
               and pd.to_datetime(o['data_evento']).date() <= date.today()
               and o.get('status') in ['Itens Retirados', 'Reserva Confirmada']
        ]

        for orc in orcamentos_retorno:
            with st.container(border=True):
                c_head1, c_head2 = st.columns([3, 1])
                c_head1.markdown(f"**{orc['cliente']}** (Evento: {orc['data_evento']})")

                if c_head2.button("⚠️ Reportar Avaria", key=f"btn_avaria_{orc['id']}", type="secondary"):
                    dialog_reportar_avaria(orc)


# ==============================================================================
# DIALOGS (MODAIS)
# ==============================================================================
@st.dialog("Registrar Avaria / Quebra")
def dialog_reportar_avaria(orcamento):
    st.warning(f"Registrando avaria para o pedido #{orcamento['id']} - {orcamento['cliente']}")

    item_avaria = st.text_input("Nome do Item Quebrado/Perdido", placeholder="Ex: Vaso Dourado G")

    c1, c2 = st.columns(2)
    qtd_quebra = c1.number_input("Quantidade Perdida", min_value=1, value=1)
    custo_peca = c2.number_input("Custo de Reposição (Prejuízo)", min_value=0.0, value=0.0,
                                 help="Quanto custa para você comprar outro?")

    st.markdown("---")
    cobrar = st.checkbox("Cobrar do Cliente?", value=True)
    valor_cobranca = 0.0
    if cobrar:
        valor_cobranca = st.number_input("Valor a Cobrar do Cliente (Multa)", min_value=0.0, value=custo_peca * 2)

    obs = st.text_area("Observação / Causa")

    if st.button("🚨 Confirmar Baixa e Lançar Financeiro"):
        if not item_avaria:
            st.error("Digite o nome do item.")
        else:
            with st.spinner("Processando..."):
                ok, msg = InventoryService.registrar_avaria(
                    item_avaria, qtd_quebra, custo_peca, cobrar, valor_cobranca, orcamento['id'], obs
                )
                if ok:
                    st.success(msg)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(f"Erro: {msg}")