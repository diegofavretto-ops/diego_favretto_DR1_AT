from datetime import date, time

import altair as alt
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import seaborn as sns
import streamlit as st
from mplsoccer import Pitch
from plotly.subplots import make_subplots
from statsbombpy import sb

try:
    from streamlit_extras.metric_cards import style_metric_cards
except ImportError:
    style_metric_cards = None


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================
st.set_page_config(
    page_title="Brasil nas Copas - Sport Analytics",
    page_icon="⚽",
    layout="wide",
)

BRASIL = "Brazil"
COPA = "FIFA World Cup"

# Coordenadas aproximadas apenas para contextualizar as sedes no mapa PyDeck.
SEDES_COPAS = pd.DataFrame(
    {
        "Temporada": ["1958", "1962", "1970", "1974", "1986", "1990", "2018", "2022"],
        "Sede": ["Suécia", "Chile", "México", "Alemanha Ocidental", "México", "Itália", "Rússia", "Catar"],
        "lat": [59.33, -33.45, 19.43, 51.16, 19.43, 41.90, 55.75, 25.28],
        "lon": [18.07, -70.66, -99.13, 10.45, -99.13, 12.50, 37.62, 51.53],
    }
)


# ============================================================
# FUNÇÕES DE DADOS - STATSBOMBPY
# ============================================================
@st.cache_data(show_spinner=False, ttl=3600)
def carregar_competicoes():
    """Carrega as competições disponíveis no StatsBomb Open Data."""
    return sb.competitions()


@st.cache_data(show_spinner=False, ttl=3600)
def carregar_partidas(competition_id, season_id):
    """Carrega as partidas de uma competição e temporada."""
    return sb.matches(
        competition_id=int(competition_id),
        season_id=int(season_id),
    )


@st.cache_data(show_spinner=False, ttl=3600)
def carregar_eventos(match_id):
    """Carrega os eventos de uma partida."""
    return sb.events(match_id=int(match_id))


def copas_disponiveis():
    """Filtra as Copas do Mundo masculinas existentes no Open Data."""
    df = carregar_competicoes().copy()

    filtro = df["competition_name"].eq(COPA)
    if "competition_gender" in df.columns:
        filtro = filtro & df["competition_gender"].eq("male")

    colunas = ["competition_id", "season_id", "competition_name", "season_name"]
    copas = df.loc[filtro, colunas].copy()
    copas["ano"] = pd.to_numeric(copas["season_name"], errors="coerce")
    copas = copas.sort_values("ano").drop(columns="ano")

    return copas.reset_index(drop=True)


def partidas_do_brasil(competition_id, season_id):
    """Mantém somente partidas em que o Brasil aparece."""
    partidas = carregar_partidas(competition_id, season_id).copy()
    filtro = partidas["home_team"].eq(BRASIL) | partidas["away_team"].eq(BRASIL)
    return partidas.loc[filtro].sort_values("match_date").reset_index(drop=True)


def placar_brasil(partida):
    """Retorna gols do Brasil e do adversário."""
    if partida["home_team"] == BRASIL:
        return int(partida["home_score"]), int(partida["away_score"])
    return int(partida["away_score"]), int(partida["home_score"])


def adversario_da_partida(partida):
    if partida["home_team"] == BRASIL:
        return partida["away_team"]
    return partida["home_team"]


def rotulo_partida(partida):
    return (
        f"{partida['match_date']} | "
        f"{partida['home_team']} {int(partida['home_score'])} x "
        f"{int(partida['away_score'])} {partida['away_team']}"
    )


def resumo_edicao(partidas, temporada):
    """Resumo coletivo simples do Brasil em uma edição disponível."""
    jogos = len(partidas)
    vitorias = empates = derrotas = 0
    gols_pro = gols_contra = 0

    for _, partida in partidas.iterrows():
        gp, gc = placar_brasil(partida)
        gols_pro += gp
        gols_contra += gc

        if gp > gc:
            vitorias += 1
        elif gp == gc:
            empates += 1
        else:
            derrotas += 1

    return {
        "Temporada": str(temporada),
        "Jogos disponíveis": jogos,
        "Vitórias": vitorias,
        "Empates": empates,
        "Derrotas": derrotas,
        "Gols pró": gols_pro,
        "Gols contra": gols_contra,
        "Saldo": gols_pro - gols_contra,
    }


def estatisticas_eventos(eventos, equipe):
    """Calcula estatísticas simples com base nos eventos da StatsBomb."""
    ev = eventos[eventos["team"].eq(equipe)].copy()

    passes = ev[ev["type"].eq("Pass")]
    chutes = ev[ev["type"].eq("Shot")]

    if "pass_outcome" in passes.columns:
        passes_certos = int(passes["pass_outcome"].isna().sum())
    else:
        passes_certos = len(passes)

    if "shot_outcome" in chutes.columns:
        gols_eventos = int(chutes["shot_outcome"].eq("Goal").sum())
    else:
        gols_eventos = 0

    if "duel_type" in ev.columns:
        desarmes = int((ev["type"].eq("Duel") & ev["duel_type"].eq("Tackle")).sum())
    else:
        desarmes = 0

    return {
        "passes": int(len(passes)),
        "passes_certos": passes_certos,
        "chutes": int(len(chutes)),
        "gols_eventos": gols_eventos,
        "desarmes": desarmes,
        "interceptacoes": int(ev["type"].eq("Interception").sum()),
    }


def eventos_para_tabela(eventos):
    """Seleciona colunas mais fáceis de ler no dashboard."""
    colunas = [
        "minute",
        "second",
        "team",
        "player",
        "type",
        "play_pattern",
        "location",
        "pass_end_location",
        "pass_outcome",
        "shot_outcome",
        "shot_statsbomb_xg",
        "duel_type",
    ]
    existentes = [coluna for coluna in colunas if coluna in eventos.columns]
    return eventos[existentes].copy()


# ============================================================
# FUNÇÕES DE VISUALIZAÇÃO
# ============================================================
def coordenadas(valor):
    if isinstance(valor, (list, tuple)) and len(valor) >= 2:
        return valor[0], valor[1]
    return None, None


def mapa_passes(eventos, jogador="Todos", cor="#009C3B"):
    passes = eventos[(eventos["team"] == BRASIL) & (eventos["type"] == "Pass")].copy()

    if jogador != "Todos":
        passes = passes[passes["player"] == jogador]

    pitch = Pitch(pitch_type="statsbomb", pitch_color="#F4F4F4", line_color="#555555")
    fig, ax = pitch.draw(figsize=(10, 6))

    for _, passe in passes.iterrows():
        x, y = coordenadas(passe.get("location"))
        fim_x, fim_y = coordenadas(passe.get("pass_end_location"))

        if None in (x, y, fim_x, fim_y):
            continue

        incompleto = pd.notna(passe.get("pass_outcome"))
        transparencia = 0.25 if incompleto else 0.70

        pitch.arrows(
            x,
            y,
            fim_x,
            fim_y,
            ax=ax,
            color=cor,
            alpha=transparencia,
            width=1.4,
            headwidth=4,
        )

    titulo = "Brasil" if jogador == "Todos" else jogador
    ax.set_title(f"Mapa de passes - {titulo}")
    fig.text(
        0.5,
        0.02,
        "Passes mais transparentes representam tentativas não concluídas.",
        ha="center",
        fontsize=9,
    )
    return fig


def mapa_chutes(eventos, jogador="Todos", cor="#009C3B"):
    chutes = eventos[(eventos["team"] == BRASIL) & (eventos["type"] == "Shot")].copy()

    if jogador != "Todos":
        chutes = chutes[chutes["player"] == jogador]

    pitch = Pitch(pitch_type="statsbomb", pitch_color="#F4F4F4", line_color="#555555")
    fig, ax = pitch.draw(figsize=(10, 6))

    for _, chute in chutes.iterrows():
        x, y = coordenadas(chute.get("location"))
        if None in (x, y):
            continue

        xg = chute.get("shot_statsbomb_xg")
        xg = float(xg) if pd.notna(xg) else 0.08
        gol = chute.get("shot_outcome") == "Goal"
        tamanho = 180 if gol else max(35, xg * 450)
        marcador = "*" if gol else "o"

        ax.scatter(
            x,
            y,
            s=tamanho,
            c=cor,
            marker=marcador,
            alpha=0.75,
            edgecolors="black",
            linewidths=0.5,
        )

    titulo = "Brasil" if jogador == "Todos" else jogador
    ax.set_title(f"Mapa de chutes - {titulo}")
    fig.text(
        0.5,
        0.02,
        "O tamanho acompanha o xG quando disponível; estrela representa gol.",
        ha="center",
        fontsize=9,
    )
    return fig


def mapa_calor(eventos):
    eventos_brasil = eventos[(eventos["team"] == BRASIL) & eventos["location"].notna()].copy()

    xs = []
    ys = []
    for local in eventos_brasil["location"]:
        x, y = coordenadas(local)
        if x is not None and y is not None:
            xs.append(x)
            ys.append(y)

    pitch = Pitch(pitch_type="statsbomb", pitch_color="#F4F4F4", line_color="#555555")
    fig, ax = pitch.draw(figsize=(10, 6))

    if xs:
        estatistica = pitch.bin_statistic(xs, ys, statistic="count", bins=(12, 8))
        pitch.heatmap(estatistica, ax=ax, cmap="YlGn", edgecolors="#F4F4F4")

    ax.set_title("Mapa de calor das ações do Brasil")
    return fig


def grafico_seaborn(adversario, brasil, oponente):
    dados = pd.DataFrame(
        {
            "Métrica": ["Passes", "Chutes", "Desarmes"] * 2,
            "Valor": [
                brasil["passes"],
                brasil["chutes"],
                brasil["desarmes"],
                oponente["passes"],
                oponente["chutes"],
                oponente["desarmes"],
            ],
            "Equipe": ["Brasil"] * 3 + [adversario] * 3,
        }
    )

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.barplot(data=dados, x="Métrica", y="Valor", hue="Equipe", ax=ax)
    ax.set_title("Brasil x adversário - comparação de eventos")
    ax.set_xlabel("")
    ax.set_ylabel("Quantidade")
    return fig


def heatmap_altair(eventos):
    tipos = ["Pass", "Shot", "Duel", "Interception", "Ball Recovery"]
    df = eventos[(eventos["team"] == BRASIL) & eventos["type"].isin(tipos)].copy()

    if df.empty:
        return None

    df["Faixa"] = (df["minute"] // 15 * 15).astype(int)
    resumo = df.groupby(["Faixa", "type"]).size().reset_index(name="Quantidade")
    resumo["Faixa de minutos"] = resumo["Faixa"].astype(str) + "-" + (resumo["Faixa"] + 14).astype(str)

    return (
        alt.Chart(resumo)
        .mark_rect()
        .encode(
            x=alt.X("Faixa de minutos:N", title="Minutos"),
            y=alt.Y("type:N", title="Tipo de evento"),
            color=alt.Color("Quantidade:Q", title="Eventos"),
            tooltip=["Faixa de minutos", "type", "Quantidade"],
        )
        .properties(height=300)
    )


def plotly_comparacao(adversario, brasil, oponente):
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=("Passes e chutes", "Ações defensivas"),
    )

    fig.add_trace(
        go.Bar(name="Brasil", x=["Passes", "Chutes"], y=[brasil["passes"], brasil["chutes"]]),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(name=adversario, x=["Passes", "Chutes"], y=[oponente["passes"], oponente["chutes"]]),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Bar(
            name="Brasil",
            x=["Desarmes", "Interceptações"],
            y=[brasil["desarmes"], brasil["interceptacoes"]],
            showlegend=False,
        ),
        row=1,
        col=2,
    )
    fig.add_trace(
        go.Bar(
            name=adversario,
            x=["Desarmes", "Interceptações"],
            y=[oponente["desarmes"], oponente["interceptacoes"]],
            showlegend=False,
        ),
        row=1,
        col=2,
    )

    fig.update_layout(barmode="group", title="Comparação interativa da partida")
    return fig


def plotly_rosca(eventos):
    df = eventos[eventos["team"].eq(BRASIL)]["type"].value_counts().head(6).reset_index()
    df.columns = ["Evento", "Quantidade"]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=df["Evento"],
                values=df["Quantidade"],
                hole=0.45,
            )
        ]
    )
    fig.update_layout(title="Eventos mais frequentes do Brasil")
    return fig


# ============================================================
# PÁGINA 1 - VISÃO GERAL
# ============================================================
def pagina_visao_geral():
    st.title("⚽ Brasil nas Copas do Mundo - Sport Analytics")
    st.caption("Assessment de Desenvolvimento Front-End com Python (Streamlit)")

    
    try:
        with st.spinner("Consultando as competições disponíveis na StatsBomb..."):
            copas = copas_disponiveis()

        st.subheader("Copas disponíveis na fonte")
        st.dataframe(
            copas.rename(
                columns={
                    "competition_name": "Competição",
                    "season_name": "Temporada",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        st.info(
            "A StatsBomb Open Data não possui todas as participações históricas do Brasil. "
            "O dashboard usa somente as edições realmente disponíveis na fonte."
        )

        st.subheader("Resumo do Brasil nas edições disponíveis")
        if st.button("Carregar resumo das Copas"):
            linhas = []
            barra = st.progress(0, text="Processando temporadas...")

            for indice, copa in copas.iterrows():
                partidas = partidas_do_brasil(copa["competition_id"], copa["season_id"])
                if not partidas.empty:
                    linhas.append(resumo_edicao(partidas, copa["season_name"]))

                progresso = int(((indice + 1) / len(copas)) * 100)
                barra.progress(progresso, text=f"Processando {copa['season_name']}...")

            barra.empty()

            resumo = pd.DataFrame(linhas)
            st.session_state["resumo_copas"] = resumo

        if "resumo_copas" in st.session_state:
            resumo = st.session_state["resumo_copas"]
            st.dataframe(resumo, use_container_width=True, hide_index=True)

            grafico = resumo.set_index("Temporada")[["Gols pró", "Gols contra"]]
            st.bar_chart(grafico)

            csv = resumo.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Baixar resumo em CSV",
                data=csv,
                file_name="resumo_brasil_copas.csv",
                mime="text/csv",
            )

        st.subheader("Sedes das edições disponíveis - PyDeck")
        sedes = SEDES_COPAS[SEDES_COPAS["Temporada"].isin(copas["season_name"].astype(str))]
        camada = pdk.Layer(
            "ScatterplotLayer",
            data=sedes,
            get_position="[lon, lat]",
            get_radius=250000,
            get_fill_color=[0, 156, 59, 170],
            pickable=True,
        )
        mapa = pdk.Deck(
            layers=[camada],
            initial_view_state=pdk.ViewState(latitude=15, longitude=0, zoom=0.4),
            tooltip={"text": "{Temporada} - {Sede}"},
        )
        st.pydeck_chart(mapa)
        st.caption("O mapa é apenas contextual; as análises esportivas utilizam os eventos da StatsBomb.")

    except Exception as erro:
        st.error("Não foi possível consultar a StatsBomb. Verifique sua conexão com a internet.")
        st.exception(erro)

    with st.expander("Fonte dos dados"):
        st.markdown(
            "Dados: **StatsBomb Open Data**, acessados pela biblioteca `statsbombpy`. "
            "Site do conjunto aberto: https://github.com/statsbomb/open-data"
        )


# ============================================================
# PÁGINA 2 - ANÁLISE DA PARTIDA
# ============================================================
def pagina_partida():
    st.title("📊 Análise de uma partida do Brasil")
    st.caption("Selecione uma Copa e uma partida para explorar os eventos disponíveis.")

    try:
        copas = copas_disponiveis()
        temporadas = copas["season_name"].astype(str).tolist()

        with st.sidebar:
            st.header("Seleção da análise")
            campeonato = st.selectbox("Campeonato", [COPA])

            temporada_anterior = st.session_state.get("temporada", temporadas[-1])
            indice = temporadas.index(temporada_anterior) if temporada_anterior in temporadas else len(temporadas) - 1
            temporada = st.selectbox("Temporada", temporadas, index=indice)
            st.session_state["temporada"] = temporada

        copa = copas[copas["season_name"].astype(str) == temporada].iloc[0]

        with st.spinner("Carregando partidas do Brasil..."):
            partidas = partidas_do_brasil(copa["competition_id"], copa["season_id"])

        if partidas.empty:
            st.warning("Não há partidas do Brasil disponíveis nessa edição.")
            return

        rotulos = {rotulo_partida(linha): int(linha["match_id"]) for _, linha in partidas.iterrows()}

        with st.sidebar:
            partida_rotulo = st.selectbox("Partida", list(rotulos.keys()))
            match_id = rotulos[partida_rotulo]

        partida = partidas[partidas["match_id"] == match_id].iloc[0]
        adversario = adversario_da_partida(partida)
        gols_brasil, gols_adversario = placar_brasil(partida)

        with st.spinner("Carregando os eventos da partida..."):
            eventos = carregar_eventos(match_id)

        jogadores = sorted(
            eventos.loc[eventos["team"].eq(BRASIL), "player"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        with st.sidebar:
            jogador = st.selectbox("Jogador - filtro opcional", ["Todos"] + jogadores)
            tipos_disponiveis = sorted(eventos["type"].dropna().astype(str).unique().tolist())
            tipos_padrao = [x for x in ["Pass", "Shot", "Duel", "Interception"] if x in tipos_disponiveis]
            tipos_eventos = st.multiselect("Tipos de evento", tipos_disponiveis, default=tipos_padrao)

            with st.form("form_filtros"):
                st.subheader("Filtros")
                limite = st.number_input(
                    "Quantidade máxima de eventos",
                    min_value=10,
                    max_value=500,
                    value=80,
                    step=10,
                )
                minuto_maximo = int(max(90, eventos["minute"].max()))
                intervalo = st.slider("Intervalo de minutos", 0, minuto_maximo, (0, minuto_maximo))
                somente_brasil = st.checkbox("Somente eventos do Brasil", value=True)
                cor_mapa = st.color_picker("Cor dos mapas", "#009C3B")
                aplicar = st.form_submit_button("Aplicar filtros")

        if aplicar:
            st.session_state["filtros_aplicados"] = True

        st.header(f"{campeonato} {temporada}")
        st.subheader(
            f"{partida['home_team']} {int(partida['home_score'])} x "
            f"{int(partida['away_score'])} {partida['away_team']}"
        )
        st.write(
            f"**Data:** {partida['match_date']}  |  "
            f"**Fase:** {partida.get('competition_stage', 'Não informado')}"
        )

        brasil = estatisticas_eventos(eventos, BRASIL)
        oponente = estatisticas_eventos(eventos, adversario)
        conversao = (brasil["gols_eventos"] / brasil["chutes"] * 100) if brasil["chutes"] else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Gols", gols_brasil, delta=gols_brasil - gols_adversario)
        c2.metric("Passes", brasil["passes"])
        c3.metric("Passes certos", brasil["passes_certos"])
        c4.metric("Chutes", brasil["chutes"])
        c5.metric("Conversão", f"{conversao:.1f}%")

        if style_metric_cards is not None:
            style_metric_cards(border_left_color="#009C3B", box_shadow=False)

        if jogador != "Todos":
            eventos_jogador = eventos[(eventos["team"] == BRASIL) & (eventos["player"] == jogador)].copy()
            est_jogador = estatisticas_eventos(eventos_jogador.assign(team=BRASIL), BRASIL)
            st.info(
                f"Filtro por jogador: **{jogador}** | "
                f"passes certos: **{est_jogador['passes_certos']}** | "
                f"chutes: **{est_jogador['chutes']}**."
            )

        aba_eventos, aba_mapas, aba_graficos, aba_json = st.tabs(
            ["Eventos", "Mapas no campo", "Comparações", "Metadados"]
        )

        with aba_eventos:
            filtrados = eventos.copy()

            if somente_brasil:
                filtrados = filtrados[filtrados["team"].eq(BRASIL)]
            if jogador != "Todos":
                filtrados = filtrados[filtrados["player"].eq(jogador)]
            if tipos_eventos:
                filtrados = filtrados[filtrados["type"].isin(tipos_eventos)]

            filtrados = filtrados[filtrados["minute"].between(intervalo[0], intervalo[1])]
            tabela = eventos_para_tabela(filtrados).head(int(limite))

            st.subheader("Eventos filtrados")
            st.dataframe(tabela, use_container_width=True, hide_index=True)

            resumo_tipos = filtrados["type"].value_counts().head(10).reset_index()
            resumo_tipos.columns = ["Tipo de evento", "Quantidade"]
            st.write("Resumo dos eventos exibidos:")
            st.table(resumo_tipos)

            csv = tabela.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Baixar eventos filtrados em CSV",
                data=csv,
                file_name=f"eventos_brasil_{temporada}_{match_id}.csv",
                mime="text/csv",
            )

        with aba_mapas:
            st.subheader("Mapa de passes - mplsoccer")
            st.pyplot(mapa_passes(eventos, jogador, cor_mapa), clear_figure=True)

            st.subheader("Mapa de chutes - mplsoccer")
            st.pyplot(mapa_chutes(eventos, jogador, cor_mapa), clear_figure=True)

            st.subheader("Mapa de calor - mplsoccer")
            st.pyplot(mapa_calor(eventos), clear_figure=True)

            st.caption(
                "Os gráficos são atualizados quando o usuário altera Copa, partida, jogador, minutos ou cor."
            )

        with aba_graficos:
            col_esq, col_dir = st.columns(2)

            with col_esq:
                st.subheader("Matplotlib + Seaborn")
                st.pyplot(grafico_seaborn(adversario, brasil, oponente), clear_figure=True)

            with col_dir:
                st.subheader("Altair")
                grafico_altair = heatmap_altair(eventos)
                if grafico_altair is not None:
                    st.altair_chart(grafico_altair, use_container_width=True)
                else:
                    st.info("Não há eventos suficientes para este gráfico.")

            st.subheader("Plotly - subplots interativos")
            st.plotly_chart(
                plotly_comparacao(adversario, brasil, oponente),
                use_container_width=True,
                key=f"comparacao_{match_id}",
            )

            st.subheader("Plotly - gráfico de rosca")
            st.plotly_chart(
                plotly_rosca(eventos),
                use_container_width=True,
                key=f"rosca_{match_id}",
            )

        with aba_json:
            metadados = {
                "match_id": int(match_id),
                "competition": COPA,
                "season": str(temporada),
                "date": str(partida.get("match_date", "")),
                "stage": str(partida.get("competition_stage", "")),
                "home_team": str(partida["home_team"]),
                "away_team": str(partida["away_team"]),
                "score": f"{int(partida['home_score'])}-{int(partida['away_score'])}",
            }
            st.json(metadados)
            st.write("Os metadados acima são exibidos em formato JSON.")

    except Exception as erro:
        st.error("Ocorreu um erro ao carregar os dados da partida.")
        st.exception(erro)


# ============================================================
# PÁGINA 3 - RECURSOS INTERATIVOS
# ============================================================
def pagina_recursos():
    st.title("🧪 Recursos interativos do Streamlit")
    st.caption("Página curta para demonstrar recursos pedidos na avaliação sem poluir a análise principal.")

    with st.expander("Upload opcional"):
        arquivo = st.file_uploader(
            "Envie um CSV, JSON, imagem ou PDF",
            type=["csv", "json", "png", "jpg", "jpeg", "pdf"],
        )

        if arquivo is not None:
            nome = arquivo.name.lower()
            if nome.endswith(".csv"):
                externo = pd.read_csv(arquivo)
                st.dataframe(externo.head(100), use_container_width=True)
            elif nome.endswith(".json"):
                externo = pd.read_json(arquivo)
                st.dataframe(externo.head(100), use_container_width=True)
            elif nome.endswith((".png", ".jpg", ".jpeg")):
                st.image(arquivo, caption=arquivo.name)
            else:
                st.success(f"Arquivo recebido: {arquivo.name}")

    st.subheader("Formulário de observação")
    with st.form("observacao"):
        titulo = st.text_input("Título", "Análise da Seleção Brasileira")
        comentario = st.text_area("Comentário", "Escreva uma interpretação simples dos gráficos.")
        nota = st.number_input("Nota para a clareza do dashboard", 0, 10, 8)
        data_analise = st.date_input("Data da análise", value=date.today())
        horario = st.time_input("Horário", value=time(20, 0))
        enviar = st.form_submit_button("Salvar na sessão")

    if enviar:
        st.session_state["observacao"] = {
            "titulo": titulo,
            "comentario": comentario,
            "nota": int(nota),
            "data": str(data_analise),
            "horario": str(horario),
        }
        st.success("Observação armazenada no Session State.")

    if "observacao" in st.session_state:
        st.write("Conteúdo mantido na sessão:")
        st.json(st.session_state["observacao"])

    st.subheader("Controle de fluxo")
    opcao = st.radio(
        "Escolha uma informação",
        ["Sobre os dados", "Sobre o projeto"],
        horizontal=True,
    )

    if opcao == "Sobre os dados":
        st.info("Os dados principais vêm da StatsBombPy e são carregados com cache.")
    else:
        st.info("O projeto prioriza estatísticas coletivas do Brasil e usa jogadores apenas como filtro opcional.")

    
# ============================================================
# NAVEGAÇÃO - MÚLTIPLAS TELAS
# ============================================================
pagina = st.navigation(
    [
        st.Page(pagina_visao_geral, title="Visão Geral", icon="🏆", default=True),
        st.Page(pagina_partida, title="Análise da Partida", icon="⚽"),
        st.Page(pagina_recursos, title="Recursos Streamlit", icon="🧪"),
    ]
)
pagina.run()
