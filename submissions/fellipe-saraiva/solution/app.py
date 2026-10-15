"""Fila de trabalho comercial explicável. Execute: streamlit run app.py."""
import pandas as pd
import streamlit as st
import scoring as sc

st.set_page_config(
    page_title="Lead Scorer · Prioridades comerciais", page_icon="🎯", layout="wide"
)


@st.cache_data
def data():
    source = sc.load()
    model = sc.fit(source)
    prices = pd.read_csv(sc.DATA / "products.csv").sales_price
    deals = sc.score(source[source.deal_stage.isin(sc.OPEN)], model, prices=prices)
    return deals, model, sc.backtest(source)


def money(value):
    return f"US$ {value:,.0f}"


deals, model, backtest = data()
reference = model["reference_max_cycle"]
with st.sidebar:
    st.header("Seu pipeline")
    region = st.selectbox(
        "Escritório", ["Todos"] + sorted(deals.regional_office.dropna().unique())
    )
    selected = deals if region == "Todos" else deals[deals.regional_office == region]
    manager = st.selectbox(
        "Manager", ["Todos"] + sorted(selected.manager.dropna().unique())
    )
    selected = selected if manager == "Todos" else selected[selected.manager == manager]
    agent = st.selectbox(
        "Vendedor", ["Todos"] + sorted(selected.sales_agent.dropna().unique())
    )
    selected = selected if agent == "Todos" else selected[selected.sales_agent == agent]
    products = st.multiselect("Produto", sorted(deals["product"].unique()))
    if products:
        selected = selected[selected["product"].isin(products)]
    st.caption(
        f"Retrato histórico: {sc.TODAY:%d/%m/%Y}. Os dados não representam um CRM atual."
    )

st.title("Onde focar esta semana")
st.write(
    "Revise oportunidades antigas, organize as negociações e defina o próximo contato."
)
st.caption(
    "O score organiza a fila de trabalho. Não representa chance de compra nem previsão de receita."
)
if selected.empty:
    st.info(
        "Nenhuma oportunidade aberta com esses filtros. Altere vendedor, escritório ou produto."
    )
    st.stop()
negotiations = selected[selected.acao == sc.ACT_NEGOTIATE]
reviews = selected[selected.acao == sc.ACT_REVIEW]
prospects = selected[selected.acao == sc.ACT_PROSPECT]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Em negociação", len(negotiations))
col2.metric(
    "Revisar situação",
    len(reviews),
    help=f"Engajadas há mais de {reference} dias: conferir o status com o vendedor.",
)
col3.metric("Em prospecção", len(prospects))
col4.metric(
    "Valor nominal aberto",
    money(selected.sales_price.sum()),
    help="Soma dos preços de tabela. Não é receita esperada ou confirmada.",
)
if len(reviews):
    st.warning(
        f"{len(reviews):,} oportunidades estão abertas há mais de {reference} dias, o maior ciclo registrado entre os negócios encerrados. Confira se o status está atualizado e combine o próximo passo. A idade, sozinha, não comprova perda."
    )
else:
    st.info(
        f"Nenhuma oportunidade deste recorte ultrapassa {reference} dias. Isso não avalia a qualidade da negociação."
    )

st.subheader("Seu plano de trabalho")
if agent == "Todos":
    st.info("Selecione seu nome em Vendedor para ver até cinco próximos passos.")
else:
    st.caption(
        "Até duas revisões de status e três negociações. Vagas restantes recebem prospecções e outras oportunidades. Adapte a agenda ao contexto do cliente."
    )
    for index, row in enumerate(sc.monday_plan(selected).itertuples(), 1):
        account = row.account if isinstance(row.account, str) else "Conta não informada"
        with st.container(border=True):
            st.markdown(f"**{index}. {account} · {row.product}**")
            st.caption(
                f"{row.opportunity_id} · {row.acao} · {money(row.sales_price)} de preço de tabela"
            )
            st.write(row.observacao)
            st.write(row.por_que)
            st.markdown(f"**Próximo passo:** {row.comando}")

COLUMNS = {
    "score": "Prioridade (0–100)",
    "opportunity_id": "ID",
    "account": "Conta",
    "product": "Produto",
    "sales_price": "Preço de tabela (US$)",
    "age_days": "Dias desde engajamento",
    "sales_agent": "Vendedor",
    "observacao": "Observação",
    "por_que": "Critério",
    "comando": "Próximo passo",
}


def table(frame, key, drop=()):
    if frame.empty:
        st.info("Nenhuma oportunidade nesta fila com os filtros atuais.")
        return
    names = {field: label for field, label in COLUMNS.items() if field not in drop}
    view = sc.ranked(frame)[list(names)].rename(columns=names)
    view["Conta"] = view["Conta"].fillna("Não informada")
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        column_config={
            "Prioridade (0–100)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.1f"
            ),
            "Preço de tabela (US$)": st.column_config.NumberColumn(format="%.0f"),
            "Dias desde engajamento": st.column_config.NumberColumn(format="%d"),
        },
    )
    st.download_button(
        "Baixar esta fila em CSV",
        view.to_csv(index=False).encode("utf-8-sig"),
        f"{key}.csv",
        mime="text/csv",
        key=key,
    )


negotiation_tab, prospect_tab, review_tab, team_tab, method_tab = st.tabs(
    [
        f"Negociações ({len(negotiations)})",
        f"Prospecção ({len(prospects)})",
        f"Revisão ({len(reviews)})",
        "Visão do time",
        "Critérios e validação",
    ]
)
with negotiation_tab:
    st.caption(
        "Prioridade = 60% valor relativo do produto + 40% idade relativa. Pesos de trabalho, não probabilidade de compra. Confira o contexto antes de agir."
    )
    table(negotiations, "negociacoes")
with prospect_tab:
    st.caption(
        "Sem data de engajamento. Ordem pelo preço de tabela, sem estimar conversão dessa etapa. Confirme adequação e interesse no primeiro contato."
    )
    table(prospects, "prospeccao", drop=("score", "age_days"))
with review_tab:
    st.caption(
        "Confira status, interesse e último contato. Nenhum negócio é encerrado automaticamente. O plano de trabalho coloca as revisões mais antigas primeiro."
    )
    table(reviews, "revisao", drop=("score",))
with team_tab:
    st.caption(
        "Distribuição das filas por vendedor no recorte selecionado. Idade e preço não medem esforço, desempenho ou qualidade do atendimento."
    )
    st.dataframe(
        sc.team_audit(selected, model),
        hide_index=True,
        width="stretch",
        column_config={
            "manager": "Manager",
            "sales_agent": "Vendedor",
            "% em revisão": st.column_config.NumberColumn(format="percent"),
            "Valor de catálogo": st.column_config.NumberColumn(
                "Valor de catálogo (US$)", format="%.0f"
            ),
        },
    )
with method_tab:
    st.markdown(
        f"""
**O que está observado**

- {model['n_closed']:,} oportunidades encerradas; {model['closed_win_rate']:.1%} delas estão marcadas como Won.
- O maior ciclo registrado entre os encerrados é de {reference} dias. Há fechamento ganho exatamente nesse dia.
- Oportunidades ainda abertas continuam com resultado desconhecido.

**Como a prioridade é calculada**

Nas negociações, o preço de tabela é normalizado em escala logarítmica entre o menor e o maior preço do catálogo.
A idade é dividida por {reference} dias, limitada a 100%. O score combina **60% valor e 40% idade**.
Esses pesos são uma política de organização proposta; não foram otimizados para prever vendas.
Os limites usam o catálogo completo, por isso filtrar a tela não recalcula o score.

Negócios acima de {reference} dias formam uma fila de revisão. Os demais Engaging permanecem em negociação.
Prospecting tem sua própria fila por valor, sem probabilidade atribuída. O app não altera o CRM.

**O que foi verificado no histórico**

O treino usa encerramentos até a data de corte. O teste contém oportunidades engajadas até a data de corte
e ainda abertas ao fim daquele dia. Não há IDs simultaneamente no treino e no teste.
AUC compara a ordenação com ganhos/perdas observados até 31/12/2017, somente nos casos já encerrados.
Os ainda abertos são informados separadamente, sem serem convertidos em perdas.
AUC próxima de 0,5 indica pouco poder de separar ganho de perda nessa amostra.

O dataset é um retrato final: não há histórico de alterações de conta, estágio ou atividade.
Os mesmos negócios podem reaparecer em cortes diferentes; os cortes não são amostras independentes.
Este diagnóstico não demonstra aumento de conversão, economia de tempo ou receita futura.
"""
    )
    st.dataframe(backtest, hide_index=True, width="stretch")
    st.markdown(
        "**Próxima validação no negócio:** comparar a fila com a rotina atual, medindo contatos úteis, avanços confirmados e tempo de trabalho, antes de ajustar pesos ou automatizar decisões."
    )
