import streamlit as st
import pandas as pd
import time
from services import SupabaseService


def render_gestao():
    st.header("📦 Gestão de Acervo e Catálogo Inteligente")

    # --- CORREÇÃO DO ERRO: Passando tenant_id para o serviço ---
    tenant_id = st.session_state.get('tenant_id')
    acervo, categorias, kits, detalhes, estoque_dict = SupabaseService.carregar_catalogo(tenant_id)
    # -----------------------------------------------------------

    tab_itens, tab_kits_builder, tab_temas_builder = st.tabs(
        ["🧩 Acervo (Itens)", "🎁 Construtor de Kits", "🎨 Construtor de Temas"])

    # ---------------------------------------------------------
    # ABA 1: ACERVO (ITENS)
    # ---------------------------------------------------------
    with tab_itens:
        st.subheader("Gerenciar Estoque e Preços")

        if "df_itens_cache" not in st.session_state:
            st.session_state["df_itens_cache"] = SupabaseService.get_dataframe("Itens")

        df_itens = st.session_state["df_itens_cache"]

        if df_itens.empty:
            df_itens = pd.DataFrame(columns=["id", "Item", "Imagem", "Preco", "Tipo", "Qtd_Estoque",
                                             "Custo_Unitario", "Link_Referencia"])

        if "Imagem" not in df_itens.columns: df_itens["Imagem"] = ""
        if "Tipo" not in df_itens.columns: df_itens["Tipo"] = "Acervo"
        if "id" not in df_itens.columns: df_itens["id"] = None

        cols_audit = ["created_at", "updated_at"]
        df_itens = df_itens.drop(columns=[c for c in cols_audit if c in df_itens.columns], errors='ignore')

        colunas_prioridade = ["id", "Imagem", "Item", "Tipo", "Preco", "Qtd_Estoque"]
        colunas_restantes = [c for c in df_itens.columns if c not in colunas_prioridade]
        df_itens = df_itens[colunas_prioridade + colunas_restantes]

        with st.expander("📸 Enviar Nova Foto e Vincular Automaticamente"):
            if not df_itens.empty:
                c_up1, c_up2 = st.columns([2, 1])

                lista_opcoes = df_itens["Item"].unique().tolist()
                lista_opcoes.sort()

                item_selecionado = c_up1.selectbox("Selecione o item do acervo:", options=lista_opcoes)
                nome_arquivo_sugerido = item_selecionado.strip() if item_selecionado else ""
                nome_item_img = c_up2.text_input("Nome base do arquivo:", value=nome_arquivo_sugerido)

                uploaded_file = st.file_uploader("Escolha a imagem", type=['png', 'jpg', 'jpeg'])

                if uploaded_file and item_selecionado:
                    if st.button("☁️ Subir Foto e Atualizar Item"):
                        with st.spinner("Enviando para o Supabase..."):
                            extensao = uploaded_file.name.split('.')[-1].lower()
                            nome_limpo_input = nome_item_img.replace(" ", "_")
                            nome_final = f"{nome_limpo_input}.{extensao}"

                            link_gerado = SupabaseService.upload_imagem(uploaded_file, nome_final)

                            if link_gerado:
                                idx = df_itens.index[df_itens['Item'] == item_selecionado].tolist()
                                if idx:
                                    df_temp = df_itens.iloc[[idx[0]]].copy()
                                    df_temp.at[idx[0], 'Imagem'] = link_gerado
                                    SupabaseService.salvar_dataframe("Itens", df_temp)

                                    del st.session_state["df_itens_cache"]
                                    st.cache_data.clear()
                                    st.success(f"✅ Foto vinculada ao item '{item_selecionado}'!")
                                    st.caption(f"Link gerado: {link_gerado}")
                                    time.sleep(2)
                                    st.rerun()
                            else:
                                st.error("Erro no upload.")
            else:
                st.info("Cadastre itens na tabela abaixo primeiro.")

        st.markdown("---")

        col_config = {
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "Item": st.column_config.TextColumn("Nome do Item", required=True),
            "Imagem": st.column_config.ImageColumn("Foto", help="Preview"),
            "Preco": st.column_config.NumberColumn("Preço Aluguel", format="%.2f", min_value=0.0),
            "Qtd_Estoque": st.column_config.NumberColumn("Estoque", step=1, min_value=0),
            "Custo_Unitario": st.column_config.NumberColumn("Custo Compra", format="%.2f"),
            "Link_Referencia": st.column_config.LinkColumn("Link Reposição"),
            "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Acervo", "Consumível", "Móvel"], required=True,
                                                     default="Acervo"),
            "ativo": st.column_config.CheckboxColumn("Ativo?", default=True)
        }

        st.info("💡 Edite os valores diretamente na tabela abaixo.")

        # AJUSTE DE WARNING: use_container_width -> width="stretch"
        df_editado = st.data_editor(
            df_itens,
            column_config=col_config,
            width="stretch",
            num_rows="dynamic",
            key="editor_itens_estoque",
            hide_index=True
        )

        if st.button("💾 Salvar Alterações no Acervo", type="primary"):
            with st.spinner("Salvando..."):
                SupabaseService.salvar_dataframe("Itens", df_editado)
                del st.session_state["df_itens_cache"]
                st.cache_data.clear()
                st.toast("Estoque atualizado!", icon="✅")
                time.sleep(1)
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
            st.session_state["df_kits_cache"] = SupabaseService.get_dataframe("Kits")

        df_kits_raw = st.session_state["df_kits_cache"]

        with st.expander("📋 Visualizar Kits Existentes"):
            if not df_kits_raw.empty:
                df_kits_show = df_kits_raw.drop(columns=["created_at", "updated_at"], errors='ignore')
                # AJUSTE DE WARNING: use_container_width -> width="stretch"
                st.dataframe(df_kits_show, width="stretch", hide_index=True)
            else:
                st.info("Nenhum kit cadastrado.")
        st.markdown("---")

        lista_kits_existentes = df_kits_raw['Nome'].tolist() if not df_kits_raw.empty else []
        st.write("### 🏗️ Construtor")
        modo_kit = st.radio("Ação:", ["Criar Novo Kit", "Editar Existente"], horizontal=True)

        kit_nome = ""
        kit_preco = 0.0
        itens_pre_selecionados = {}
        kit_id_atual = None

        if modo_kit == "Editar Existente" and lista_kits_existentes:
            kit_selecionado = st.selectbox("Selecione o Kit", lista_kits_existentes)
            dados_kit = df_kits_raw[df_kits_raw['Nome'] == kit_selecionado].iloc[0]

            kit_nome = dados_kit['Nome']
            kit_preco = float(dados_kit['Preco'])
            if 'id' in dados_kit: kit_id_atual = int(dados_kit['id'])

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

        # AJUSTE DE WARNING: use_container_width -> width="stretch"
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
                    with st.spinner("Salvando kit..."):
                        desc_list = [f"{row['Qtd_No_Kit']}x {row['Item']}" for _, row in itens_selecionados.iterrows()]

                        novo_dict = {
                            "Nome": kit_nome,
                            "Preco": kit_preco,
                            "Descricao": "; ".join(desc_list)
                        }
                        if kit_id_atual: novo_dict['id'] = kit_id_atual

                        df_unico = pd.DataFrame([novo_dict])
                        SupabaseService.salvar_dataframe("Kits", df_unico)

                        del st.session_state["df_kits_cache"]
                        st.cache_data.clear()

                        st.success(f"Kit '{kit_nome}' salvo com sucesso!")
                        time.sleep(1.5)
                        st.rerun()

    # ---------------------------------------------------------
    # ABA 3: TEMAS
    # ---------------------------------------------------------
    with tab_temas_builder:
        st.subheader("🎨 Gestão de Temas")
        if not acervo: st.warning("Acervo vazio."); st.stop()

        if "df_temas_cache" not in st.session_state:
            st.session_state["df_temas_cache"] = SupabaseService.get_dataframe("Temas")
        df_temas = st.session_state["df_temas_cache"]

        with st.expander("Lista de Temas"):
            if not df_temas.empty:
                df_temas_show = df_temas.drop(columns=["created_at", "updated_at"], errors='ignore')
                # AJUSTE DE WARNING: use_container_width -> width="stretch"
                st.dataframe(df_temas_show, width="stretch", hide_index=True)

        c1, c2 = st.columns(2)
        cat = c1.text_input("Categoria", placeholder="Ex: Infantil")
        nome = c2.text_input("Nome Tema", placeholder="Ex: Safari")
        itens = st.multiselect("Itens Base", list(acervo.keys()))
        detalhes = st.text_area("Detalhes")

        if st.button("💾 Salvar Tema"):
            if not nome or not cat:
                st.error("Preencha Categoria e Nome.")
            else:
                with st.spinner("Salvando tema..."):
                    desc = f"{detalhes} | Base: {', '.join(itens)}" if itens else detalhes

                    df_unico = pd.DataFrame([{"Categoria": cat, "Tema": nome, "Detalhes": desc}])
                    SupabaseService.salvar_dataframe("Temas", df_unico)

                    del st.session_state["df_temas_cache"]
                    st.cache_data.clear()

                    st.success(f"Tema '{nome}' salvo com sucesso!")
                    time.sleep(1.5)
                    st.rerun()