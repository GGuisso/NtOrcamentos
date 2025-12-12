import streamlit as st
import pandas as pd
import time
from services import GoogleSheetsService


def render_gestao():
    st.header("📦 Gestão de Acervo e Catálogo Inteligente")

    # Carrega dados atuais
    acervo, categorias, kits, detalhes, estoque_dict = GoogleSheetsService.carregar_catalogo()

    tab_itens, tab_kits_builder, tab_temas_builder = st.tabs(
        ["🧩 Acervo (Itens)", "🎁 Construtor de Kits", "🎨 Construtor de Temas"])

    # ---------------------------------------------------------
    # ABA 1: ACERVO (ITENS)
    # ---------------------------------------------------------
    with tab_itens:
        st.subheader("Gerenciar Estoque e Preços")

        # 1. Carrega DataFrame
        if "df_itens_cache" not in st.session_state:
            st.session_state["df_itens_cache"] = GoogleSheetsService.get_dataframe("Itens")

        df_itens = st.session_state["df_itens_cache"]

        if df_itens.empty:
            df_itens = pd.DataFrame(columns=["Item", "Imagem", "Preco", "Tipo", "Qtd_Estoque",
                                             "Custo_Unitario", "Loja_Ultima_Compra", "Link_Referencia"])

        if "Imagem" not in df_itens.columns:
            df_itens["Imagem"] = ""

        # 2. Uploader Inteligente
        with st.expander("📸 Enviar Nova Foto e Vincular Automaticamente"):
            if not df_itens.empty:
                c_up1, c_up2 = st.columns([2, 1])

                # Lista ordenada
                lista_opcoes = df_itens["Item"].unique().tolist()
                lista_opcoes.sort()

                item_selecionado = c_up1.selectbox("Selecione o item do acervo:", options=lista_opcoes)

                # Sugestão de nome limpo
                nome_arquivo_sugerido = item_selecionado.strip() if item_selecionado else ""
                nome_item_img = c_up2.text_input("Nome base do arquivo:", value=nome_arquivo_sugerido)

                uploaded_file = st.file_uploader("Escolha a imagem", type=['png', 'jpg', 'jpeg'])

                if uploaded_file and item_selecionado:
                    if st.button("☁️ Subir Foto e Atualizar Item"):
                        with st.spinner("Enviando para o Supabase..."):
                            # --- AJUSTE: Detecta extensão real e não gera timestamp aqui (o service já faz isso) ---
                            extensao = uploaded_file.name.split('.')[-1].lower()
                            nome_limpo_input = nome_item_img.replace(" ", "_")
                            # Envia apenas "Nome.jpg", o service transformará em "Tenant/Timestamp_Nome.jpg"
                            nome_final = f"{nome_limpo_input}.{extensao}"

                            link_gerado = GoogleSheetsService.upload_imagem(uploaded_file, nome_final)

                            if link_gerado:
                                # Atualiza DataFrame Local
                                idx = df_itens.index[df_itens['Item'] == item_selecionado].tolist()
                                if idx:
                                    df_itens.at[idx[0], 'Imagem'] = link_gerado

                                    # Salva no Sheets
                                    GoogleSheetsService.salvar_dataframe("Itens", df_itens)

                                    # Limpa Cache
                                    del st.session_state["df_itens_cache"]
                                    st.cache_data.clear()

                                    st.success(f"✅ Foto vinculada ao item '{item_selecionado}'!")
                                    st.caption(f"Link gerado: {link_gerado}")
                                    time.sleep(2)
                                    st.rerun()
                            else:
                                st.error("Erro no upload. Verifique logs.")
            else:
                st.info("Cadastre itens na tabela abaixo primeiro.")

        st.markdown("---")

        # 3. Tabela de Edição
        if not df_itens.empty:
            col_config = {
                "Item": st.column_config.TextColumn("Nome do Item", required=True),
                "Imagem": st.column_config.ImageColumn("Foto", help="Preview"),
                "Preco": st.column_config.NumberColumn("Preço Aluguel", format="%.2f", min_value=0.0),
                "Qtd_Estoque": st.column_config.NumberColumn("Estoque", step=1, min_value=0),
                "Custo_Unitario": st.column_config.NumberColumn("Custo Compra", format="%.2f"),
                "Link_Referencia": st.column_config.LinkColumn("Link Reposição"),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Acervo", "Consumível", "Móvel"])
            }

            st.info("💡 Edite os valores diretamente na tabela abaixo.")

            df_editado = st.data_editor(
                df_itens,
                column_config=col_config,
                width="stretch",
                num_rows="dynamic",
                key="editor_itens_estoque"
            )

            if st.button("💾 Salvar Alterações no Acervo", type="primary"):
                with st.spinner("Salvando..."):
                    GoogleSheetsService.salvar_dataframe("Itens", df_editado)
                    del st.session_state["df_itens_cache"]
                    st.cache_data.clear()
                    st.toast("Estoque atualizado!", icon="✅")
                    time.sleep(1)
                    st.rerun()
        else:
            st.warning("Tabela vazia.")
            df_editado = st.data_editor(df_itens, num_rows="dynamic", key="editor_itens_vazio")
            if st.button("💾 Salvar Primeiro Item", type="primary"):
                GoogleSheetsService.salvar_dataframe("Itens", df_editado)
                st.cache_data.clear()
                st.rerun()

    # ---------------------------------------------------------
    # ABA 2: CONSTRUTOR DE KITS
    # ---------------------------------------------------------
    with tab_kits_builder:
        st.subheader("🛠️ Gestão de Kits")
        if not acervo:
            st.warning("⚠️ Seu acervo está vazio.")
            st.stop()

        if "df_kits_cache" not in st.session_state:
            st.session_state["df_kits_cache"] = GoogleSheetsService.get_dataframe("Kits")

        df_kits_raw = st.session_state["df_kits_cache"]

        with st.expander("📋 Visualizar Kits Existentes"):
            if not df_kits_raw.empty:
                st.dataframe(df_kits_raw, width="stretch")
            else:
                st.info("Nenhum kit cadastrado.")
        st.markdown("---")

        lista_kits_existentes = df_kits_raw['Nome'].tolist() if not df_kits_raw.empty else []
        st.write("### 🏗️ Construtor")
        modo_kit = st.radio("Ação:", ["Criar Novo Kit", "Editar Existente"], horizontal=True)

        kit_nome = ""
        kit_preco = 0.0
        itens_pre_selecionados = {}

        if modo_kit == "Editar Existente" and lista_kits_existentes:
            kit_selecionado = st.selectbox("Selecione o Kit", lista_kits_existentes)
            dados_kit = df_kits_raw[df_kits_raw['Nome'] == kit_selecionado].iloc[0]
            kit_nome = dados_kit['Nome']
            kit_preco = float(dados_kit['Preco'])
            desc = str(dados_kit['Descricao'])
            try:
                partes = desc.split(';')
                for p in partes:
                    if "x " in p:
                        qtd_str, nome_item = p.split("x ", 1)
                        if qtd_str.strip().isdigit():
                            itens_pre_selecionados[nome_item.strip()] = int(qtd_str)
                    else:
                        for item_acervo in acervo.keys():
                            if item_acervo in p: itens_pre_selecionados[item_acervo] = 1
            except:
                pass
        else:
            kit_nome = st.text_input("Nome do Novo Kit", placeholder="Ex: Kit Pegue e Monte - Sereia")

        st.markdown("---")

        lista_itens_builder = []
        for item, preco in acervo.items():
            qtd_atual = itens_pre_selecionados.get(item, 0)
            lista_itens_builder.append({
                "Item": item, "Preco_Unit": preco,
                "Qtd_No_Kit": int(qtd_atual), "Subtotal": preco * qtd_atual
            })

        df_builder = pd.DataFrame(lista_itens_builder)
        df_kit_config = st.data_editor(
            df_builder,
            column_config={
                "Item": st.column_config.TextColumn("Item", disabled=True),
                "Preco_Unit": st.column_config.NumberColumn("Unit.", format="R$ %.2f", disabled=True),
                "Qtd_No_Kit": st.column_config.NumberColumn("Qtd", min_value=0, step=1),
                "Subtotal": st.column_config.ProgressColumn("Custo", format="R$ %.2f", min_value=0, max_value=200)
            },
            hide_index=True, width="stretch", height=300, key="builder_kit_editor"
        )

        itens_selecionados = df_kit_config[df_kit_config['Qtd_No_Kit'] > 0]
        if not itens_selecionados.empty:
            custo_sugerido = (itens_selecionados['Preco_Unit'] * itens_selecionados['Qtd_No_Kit']).sum()
            c1, c2 = st.columns(2)
            c1.info(f"Soma avulsa: **R$ {custo_sugerido:.2f}**")
            kit_preco = c2.number_input("Preço Kit", value=kit_preco if kit_preco > 0 else custo_sugerido)

            if st.button("💾 Salvar Kit", type="primary"):
                if not kit_nome:
                    st.error("Defina um nome.")
                else:
                    desc_list = [f"{row['Qtd_No_Kit']}x {row['Item']}" for _, row in itens_selecionados.iterrows()]
                    novo = {"Nome": kit_nome, "Preco": kit_preco, "Descricao": "; ".join(desc_list)}

                    df_final = df_kits_raw.copy()
                    if modo_kit == "Editar Existente": df_final = df_final[df_final['Nome'] != kit_nome]
                    df_final = pd.concat([df_final, pd.DataFrame([novo])], ignore_index=True)

                    GoogleSheetsService.salvar_dataframe("Kits", df_final)
                    del st.session_state["df_kits_cache"]
                    st.cache_data.clear()
                    st.rerun()

    # ---------------------------------------------------------
    # ABA 3: TEMAS
    # ---------------------------------------------------------
    with tab_temas_builder:
        st.subheader("🎨 Gestão de Temas")
        if not acervo: st.warning("Acervo vazio."); st.stop()

        if "df_temas_cache" not in st.session_state:
            st.session_state["df_temas_cache"] = GoogleSheetsService.get_dataframe("Temas")
        df_temas = st.session_state["df_temas_cache"]

        with st.expander("Lista de Temas"):
            if not df_temas.empty: st.dataframe(df_temas, width="stretch")

        c1, c2 = st.columns(2)
        cat = c1.text_input("Categoria", placeholder="Ex: Infantil")
        nome = c2.text_input("Nome Tema", placeholder="Ex: Safari")
        itens = st.multiselect("Itens Base", list(acervo.keys()))
        detalhes = st.text_area("Detalhes")

        if st.button("💾 Salvar Tema"):
            if not nome or not cat:
                st.error("Preencha Categoria e Nome.")
            else:
                desc = f"{detalhes} | Base: {', '.join(itens)}" if itens else detalhes
                novo = pd.DataFrame([{"Categoria": cat, "Tema": nome, "Detalhes": desc}])
                df_final = pd.concat([df_temas, novo], ignore_index=True)
                GoogleSheetsService.salvar_dataframe("Temas", df_final)
                del st.session_state["df_temas_cache"]
                st.cache_data.clear()
                st.rerun()