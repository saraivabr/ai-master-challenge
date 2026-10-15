"""Lead Scorer: o vendedor abre na segunda e sabe onde focar.  streamlit run app.py"""
import pandas as pd
import streamlit as st

import scoring as sc

st.set_page_config(page_title="Lead Scorer", page_icon="🎯", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1280px;}
  [data-testid="stMetricValue"] {font-size: 1.4rem;}
  .kicker {font-size: .78rem; letter-spacing: .08em; text-transform: uppercase; opacity: .6; margin-bottom: -.4rem;}
  .cmd {font-size: 1.02rem; font-weight: 600; margin: .35rem 0 .1rem;}
  .why {font-size: .9rem; opacity: .75;}
</style>
""", unsafe_allow_html=True)

ACT = {  # ação → (rótulo com ícone, cor do badge)
    sc.ACT_LAST: ("⏳ Revisão próxima", "red"),
    sc.ACT_HOT: ("🔥 Atacar agora", "orange"),
    sc.ACT_WARM: ("🔁 Manter cadência", "blue"),
    sc.ACT_LOW: ("💤 Baixa prioridade", "gray"),
    sc.ACT_STALE: ("🧹 Revisar e requalificar", "violet"),
    sc.ACT_PROSPECT: ("📞 Fazer 1º contato", "green"),
}


@st.cache_data
def data():
    df = sc.load()
    prices = pd.read_csv(sc.DATA / "products.csv").sales_price
    m = sc.fit(df)
    return sc.score(df[df.deal_stage.isin(sc.OPEN)], m, prices=prices), m, sc.backtest(df), df


deals, m, bt, history = data()
usd = lambda v: f"${v:,.0f}"                          # metric e tabela
html = lambda t: str(t).replace("$", "&#36;")        # dentro de HTML/markdown, $ não vira LaTeX


def conta(account):
    return account if isinstance(account, str) else "conta não preenchida"


# ---------------------------------------------------------------- componentes
def diagnosis(d, scoped_history):
    """O fato que muda a semana, ao lado da curva que mostra por quê."""
    ex = sc.exposure(d)
    rates = sc.diagnosis_rates(scoped_history, d)
    share = ex["stale_value"] / max(ex["open_value"], 1)
    left, right = st.columns([5, 4], gap="large")
    with left:
        st.markdown('<p class="kicker">Diagnóstico</p>', unsafe_allow_html=True)
        st.markdown(html(f"### {share:.0%} do valor aberto (${ex['stale_value']:,.0f}) pede revisão."))
        st.markdown(html(
            f"Referência global: maior ciclo de **{m['cliff']} dias** entre {m['n_closed']:,} negociações encerradas. "
            f"No recorte atual, {ex['n_stale']:,} abertos pedem revisão. Idade não comprova perda."))
        if rates["n_closed"]:
            st.markdown(f"**Neste recorte:** {rates['n_closed']:,} encerrados; taxa de ganho "
                        f"**{rates['crm_rate']:.0%}**. Se os {rates['n_stale']} abertos antigos do recorte "
                        f"forem perdas não registradas, a taxa seria **{rates['assumed_rate']:.0%}**.")
        else:
            st.caption("Sem negociações encerradas neste recorte; taxa de ganho indisponível.")
        c1, c2, c3 = st.columns(3)
        c1.metric("Para revisar", f"{ex['n_stale']:,}", border=True,
                  help=f"Engajados há mais de {m['cliff']} dias ou sem data")
        c2.metric("Deals vivos", int(d.acao.isin(sc.ALIVE).sum()), border=True,
                  help=f"Engajados há até {m['cliff']} dias")
        c3.metric("Revisão próxima", int(d.acao.eq(sc.ACT_LAST).sum()), border=True,
                  help=f"Vivos a partir do dia {m['last_call']}: referência de revisão")
    with right:
        st.markdown('<p class="kicker">Por quê</p>', unsafe_allow_html=True)
        st.markdown("**Referência global: taxa por idade sob hipótese** (aberto antigo = perda)")
        curve = pd.DataFrame({"Ganharam (%)": (m["curve"] * 100).round(1)})
        curve.index.name = "Dias desde o engajamento"
        st.area_chart(curve, height=230, color="#E4572E")
        lc = f" · dia {m['last_call']}: {m['curve'].iloc[m['last_call']]:.0%}" if m["last_call"] is not None else ""
        st.caption(f"Dos deals que chegaram abertos ao dia d, quantos ganharam, contando como perda os que passaram "
                   f"de {m['cliff']} dias. Dia 0: {m['curve'].iloc[0]:.0%}{lc} · dia {m['cliff']}: "
                   f"{m['curve'].iloc[m['cliff']]:.0%}. Esta curva é global, não muda com os filtros e não é uma probabilidade comprovada.")


def deal_card(i, r):
    label, color = ACT[r.acao]
    with st.container(border=True):
        top = st.columns([5, 3])
        top[0].markdown(html(f"**{i}. {r.product}** · {conta(r.account)}  \n"
                             f"<span class='why'>{r.opportunity_id} · {r.sales_agent}</span>"),
                        unsafe_allow_html=True)
        with top[1]:
            st.badge(label, color=color)
        k = st.columns(3)
        k[0].metric("Valor sob hipótese", usd(r.valor_esperado),
                    help="Taxa assumida × preço de catálogo. Não é previsão de receita.")
        if r.acao == sc.ACT_PROSPECT:
            k[1].metric("Conversão", "Desconhecida")
            st.caption(f"Proxy não validada: média dos engajados ({r.prob:.0%}) × preço. "
                       "A conversão de Prospecting não é observada; ordem por preço.")
        else:
            k[1].metric("Taxa sob hipótese", f"{r.prob:.0%}")
            st.caption("Hipótese: abertos antigos contam como perda. Taxa não calibrada; "
                       "valor não é receita prevista.")
        if pd.isna(r.deadline):  # Prospecting: sem data para referência por idade
            k[2].metric("Prazo", "Esta semana")
            st.caption("Sem data de engajamento: não há idade observada.")
        else:
            k[2].metric("Referência histórica", f"{r.deadline:%d/%m}", help=f"Dia {m['cliff']} desde o engajamento")
            st.progress(max(r.days_left, 0) / m["cliff"],
                        text=f"{r.days_left:.0f} dias até a referência · {r.age_days:.0f} dias em negociação; não é prazo fatal")
        cmd = r.comando
        st.markdown(html(f"<p class='cmd'>➜ {cmd}</p><p class='why'>{r.por_que}</p>"), unsafe_allow_html=True)


def deal_table(df, key, show_agent=True):
    """Tabela enxuta. Clique numa linha para ver o porquê."""
    if df.empty:
        st.info("Nada nesta fila com esses filtros.")
        return
    view = sc.ranked(df).reset_index(drop=True)
    show = pd.DataFrame({
        "Score": view.score, "Ação": view.acao.map(lambda a: ACT[a][0]),
        "Produto": view["product"], "Conta": view.account.fillna("—"),
        "Valor sob hipótese": view.valor_esperado, "Dias até referência": view.days_left, "Referência": view.deadline,
    })
    if show_agent:
        show["Vendedor"] = view.sales_agent
    show = show.dropna(axis=1, how="all")
    ev = st.dataframe(show, hide_index=True, width="stretch", height=min(38 + 35 * len(show), 420),
                      on_select="rerun", selection_mode="single-row", key=key, column_config={
        "Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d", width="small"),
        "Valor sob hipótese": st.column_config.NumberColumn(format="dollar"),
        "Referência": st.column_config.DateColumn(format="DD/MM/YYYY"),
    })
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        r = view.iloc[rows[0]]
        with st.container(border=True):
            st.markdown(html(f"**{r['product']} · {conta(r.account)}** ({r.opportunity_id}, {r.sales_agent})"))
            a, b, c = st.columns(3)
            a.markdown(html(f"<p class='kicker'>Verdade</p>{r.verdade}"), unsafe_allow_html=True)
            b.markdown(html(f"<p class='kicker'>Por que importa</p>{r.por_que}"), unsafe_allow_html=True)
            c.markdown(html(f"<p class='kicker'>Próximo passo</p><b>{r.comando}</b>"), unsafe_allow_html=True)
    else:
        st.caption("Clique numa linha para ver a explicação completa do deal.")
    st.download_button("Baixar CSV", view.drop(columns=["urgencia"]).to_csv(index=False).encode("utf-8-sig"),
                       f"{key}.csv", mime="text/csv", key=f"dl_{key}")


def how_it_works():
    st.markdown(html(f"""
**Score (0–100)** = escala log do **valor sob hipótese** = taxa por idade × preço de catálogo.
Os limites vêm do catálogo inteiro, então filtrar a tela não muda o score. Zero valor recebe score zero.

- **Engaging:** a curva usa fechamentos observados e a hipótese de abertos acima do maior ciclo
  ({m['cliff']} dias) como perdas não registradas. Não é probabilidade calibrada.
- **Prospecting:** usa a média dos engajados ({m['base']:.0%}) como proxy não validada.
  A conversão de prospecção é desconhecida; a fila é ordenada por preço.
- **Revisão:** acima de {m['cliff']} dias, o deal vai para revisão separada do top 5.
  Esse máximo observado não prova prazo fatal nem perda. Confirmar status e próximo passo com o cliente.
- **Revisão próxima:** a curva sob hipótese cai abaixo da metade da média a partir do dia {m['last_call']}.
  A ação sugerida é revisar, sem encerrar automaticamente.
- **Desempate:** menor distância à referência histórica, depois valor e ID.

**Avaliação retrospectiva.** O histórico rotulado usa fechados até o corte. O fit também usa os abertos
antigos daquele snapshot como pseudo-negativos, inclusive IDs avaliados depois; não usa seus desfechos futuros.
AUC usa apenas os desfechos registrados até 31/12/2017; desconhecidos ficam à parte. Os atributos não separam
ganho de perda de modo estável nesses quatro cortes. Isso não mede a qualidade do top 5 nem ganho causal.
A comparação por vendedor com maior preço e maior idade está em `docs/avaliacao.md`, com cobertura,
receita observada e sensibilidade à hipótese e à exclusão dos antigos.

**Deal sem conta no CRM:** todo deal fechado da base tem conta. Pode ser regra de fechamento do CRM, então isso
não entra na chance: vira o primeiro comando ("preencher a conta").
"""))
    st.dataframe(bt, hide_index=True, width="stretch")


# ---------------------------------------------------------------- telas
def seller_view():
    alive_ev = deals[deals.acao.isin(sc.ALIVE)].groupby("sales_agent").valor_esperado.sum()
    agents = sorted(deals.sales_agent.unique(), key=lambda a: (-alive_ev.get(a, 0), a))
    agent = st.selectbox("Seu nome", agents, help="Ordenado por valor esperado dos deals vivos")
    d = deals[deals.sales_agent == agent]
    alive, stale = d[d.acao.isin(sc.ALIVE)], d[d.acao == sc.ACT_STALE]

    st.markdown(f"## Bom dia, {agent.split()[0]}.")
    k = st.columns(4)
    k[0].metric("Deals vivos", len(alive), border=True)
    k[1].metric("Revisão próxima", int(d.acao.eq(sc.ACT_LAST).sum()), border=True,
                help=f"Vivos a partir do dia {m['last_call']}: referência de revisão")
    k[2].metric("Para revisar", len(stale), border=True, help=f"Mais de {m['cliff']} dias")
    k[3].metric("Valor parado", usd(stale.sales_price.sum()), border=True,
                help="Preço de catálogo somado dos parados")

    dead = len(stale) / max(len(d), 1)
    if dead < 0.25:  # 25% ou mais dos deals abertos (inclui prospecção) dispara o alerta
        st.success("Pipeline limpo. Raro neste time. Agora ataque o topo.")
    else:
        st.warning(html(f"**{dead:.0%} do seu pipeline precisa de revisão.** São {len(stale)} deals ocupando a sua "
                        "previsão e a sua agenda. Até sexta: confirmar status e próximo passo com o cliente. "
                        "Requalificar ou encerrar após decisão humana. Estão na aba Revisão."))
    no_acc = int(d[d.acao.isin(sc.ALIVE + [sc.ACT_PROSPECT])].account.isna().sum())
    if no_acc:
        st.error(f"**Antes de tudo:** preencher a conta de {no_acc} deals de negociação/prospecção. "
                 "Todo deal fechado da base tem conta preenchida.")

    st.markdown("### Seus 5 comandos da semana")
    plan = sc.monday_plan(d)
    if plan.empty:
        st.info("Nenhum deal vivo nem prospecção. Comece pela aba Revisão.")
    cols = st.columns(2, gap="medium")
    for i, r in enumerate(plan.itertuples(), 1):
        with cols[(i - 1) % 2]:
            deal_card(i, r)

    t1, t2, t3, t4 = st.tabs([f"Pipeline vivo ({len(alive)})", f"Prospecção ({d.acao.eq(sc.ACT_PROSPECT).sum()})",
                              f"Revisão ({len(stale)})", "Como o score funciona"])
    with t1:
        deal_table(alive, "vivo_v", show_agent=False)
    with t2:
        deal_table(d[d.acao == sc.ACT_PROSPECT], "prosp_v", show_agent=False)
    with t3:
        deal_table(stale, "limpeza_v", show_agent=False)
    with t4:
        how_it_works()


def manager_view():
    f = st.columns(3)
    region = f[0].selectbox("Escritório", ["Todos"] + sorted(deals.regional_office.dropna().unique()))
    d = deals if region == "Todos" else deals[deals.regional_office == region]
    manager = f[1].selectbox("Manager", ["Todos"] + sorted(d.manager.dropna().unique()))
    d = d if manager == "Todos" else d[d.manager == manager]
    products = f[2].multiselect("Produto", sorted(deals["product"].unique()), placeholder="Todos")
    if products:
        d = d[d["product"].isin(products)]
    if d.empty:
        st.info("Nenhum deal aberto com esses filtros.")
        return

    scoped = history
    for column, selected in [("regional_office", region), ("manager", manager)]:
        if selected != "Todos":
            scoped = scoped[scoped[column].eq(selected)]
    if products:
        scoped = scoped[scoped["product"].isin(products)]
    diagnosis(d, scoped)
    st.divider()
    st.markdown("### Onde o time gasta energia em pipeline parado")
    st.caption("Ordenado por % do pipeline que passou do maior ciclo já registrado.")
    st.dataframe(sc.team_audit(d).rename(columns={"sales_agent": "Vendedor", "manager": "Manager"}),
                 hide_index=True, width="stretch", height=380, column_config={
        "% parado": st.column_config.ProgressColumn(min_value=0, max_value=1, format="percent"),
        "Valor parado": st.column_config.NumberColumn(format="dollar", help="Preço de catálogo somado"),
    })

    alive, stale = d[d.acao.isin(sc.ALIVE)], d[d.acao == sc.ACT_STALE]
    t1, t2, t3, t4 = st.tabs([f"Pipeline vivo ({len(alive)})", f"Prospecção ({d.acao.eq(sc.ACT_PROSPECT).sum()})",
                              f"Revisão ({len(stale)})", "Como o score funciona"])
    with t1:
        deal_table(alive, "vivo_m")
    with t2:
        deal_table(d[d.acao == sc.ACT_PROSPECT], "prosp_m")
    with t3:
        deal_table(stale, "limpeza_m")
    with t4:
        how_it_works()


# ---------------------------------------------------------------- página
head = st.columns([3, 2], vertical_alignment="bottom")
head[0].title("🎯 Onde focar esta semana")
role = head[1].radio("Quem é você?", ["Vendedor", "Gerente"], horizontal=True, key="role")
st.caption(f"Pipeline em {sc.TODAY:%d/%m/%Y} (último dia do dataset). Prioridade baseada em taxa sob hipótese × "
           "preço de catálogo. Cada deal sai com uma ação e uma referência para revisão.")
if role == "Gerente":
    manager_view()
else:
    seller_view()
