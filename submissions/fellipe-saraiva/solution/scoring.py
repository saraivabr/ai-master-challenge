"""Lead scoring do pipeline: o que fazer com cada deal, em que ordem e até quando.

O que os dados mostram (python scoring.py reproduz tudo):
1. Nenhuma das 6.711 negociações encerradas levou mais de 138 dias. 1.291 negociações abertas já passaram disso.
2. Vendedor, produto, setor e conta não separam ganho de perda de forma estável fora da amostra (AUC ≈ 0,5).
3. O score usa o que muda a decisão: valor do produto e sua idade em relação ao histórico.

A chance por idade é uma HIPÓTESE explícita: deal aberto além do maior ciclo conta como perda
não registrada. Ela é usada para ordenar e sugerir revisão, nunca como previsão de receita ou prazo fatal.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
TODAY = pd.Timestamp("2017-12-31")  # data de referência: último dia do dataset
OPEN = ["Engaging", "Prospecting"]
HOT, WARM = 70, 45                  # cortes de score: "Atacar agora" / "Manter cadência"

ACT_STALE = "Revisar e requalificar"
ACT_LAST = "Revisão próxima"
ACT_HOT = "Atacar agora"
ACT_WARM = "Manter cadência"
ACT_LOW = "Baixa prioridade"
ACT_PROSPECT = "Fazer 1º contato"
ALIVE = [ACT_LAST, ACT_HOT, ACT_WARM, ACT_LOW]
NO_ACCOUNT_CMD = "Hoje: preencher a conta no CRM (todo deal fechado da base tem conta). "


def load(data_dir=DATA):
    """Carrega as quatro tabelas e corrige duas grafias divergentes conhecidas."""
    data_dir = Path(data_dir)
    p = pd.read_csv(data_dir / "sales_pipeline.csv", parse_dates=["engage_date", "close_date"])
    p["product"] = p["product"].replace({"GTXPro": "GTX Pro"})
    acc = pd.read_csv(data_dir / "accounts.csv")
    acc["sector"] = acc["sector"].replace({"technolgy": "technology"})
    return (p.merge(acc, on="account", how="left")
             .merge(pd.read_csv(data_dir / "products.csv"), on="product", how="left")
             .merge(pd.read_csv(data_dir / "sales_teams.csv"), on="sales_agent", how="left"))


def _closed_at(df, at):
    return df.close_date.notna() & df.close_date.le(at) & df.deal_stage.isin(["Won", "Lost"])


def fit(df, at=TODAY, stale_as_loss=True):
    """Aprende só com o que se sabia em `at`.

    - cliff: maior ciclo (engajamento → fechamento) entre os fechados até `at`.
    - curve[d]: dos deals que chegaram abertos ao dia d, quantos ganharam. HIPÓTESE: quem passou
      do cliff sem fechar conta como perda (nenhum fechamento da base aconteceu depois disso).
    - crm_rate: taxa de ganho só entre fechados (o que o CRM mostra).
    A curva padrão também usa abertos antigos do próprio snapshot como pseudo-negativos,
    inclusive IDs avaliados depois. Isso não usa seus desfechos futuros; não é treino
    exclusivamente supervisionado/disjunto. stale_as_loss=False desliga essa hipótese.
    """
    at = pd.Timestamp(at)
    closed = df.loc[_closed_at(df, at)]
    cycle = (closed.close_date - closed.engage_date).dt.days
    cycle = cycle[cycle.ge(0)]
    m = {"cliff": int(cycle.max()) if len(cycle) else None,
         "n_closed": len(closed),
         "crm_rate": float(closed.deal_stage.eq("Won").mean()) if len(closed) else np.nan,
         "loss_median": int(lost.median()) if len(lost := cycle[closed.loc[cycle.index].deal_stage.eq("Lost")])
         else 0}
    if m["cliff"] is None:
        m.update(curve=pd.Series(dtype=float), base=np.nan, last_call=None)
        return m
    eng = df[df.engage_date.notna() & df.engage_date.le(at)]
    is_closed = _closed_at(eng, at)
    age = (at - eng.engage_date).dt.days
    stale = ~is_closed & age.gt(m["cliff"])
    known = is_closed | (stale & stale_as_loss)
    life = np.where(is_closed, (eng.close_date - eng.engage_date).dt.days, age)[known.values]
    won = (is_closed & eng.deal_stage.eq("Won"))[known].values
    curve = pd.Series({d: won[life >= d].mean() if (life >= d).any() else 0.0
                       for d in range(m["cliff"] + 1)})
    base = float(curve.iloc[0])
    below = curve[curve < base / 2]
    m.update(curve=curve, base=base, n_stale=int(stale.sum()),
             last_call=int(below.index[0]) if len(below) else None)
    return m


def score(deals, m, today=TODAY, prices=None, review_old=True):
    """Score 0–100 = escala log do valor sob hipótese (taxa por idade × preço de catálogo).

    `prices` deve ser o catálogo inteiro (limites fixos: o score não muda quando a tela filtra).
    """
    d = deals.copy()
    prices = d.sales_price if prices is None else pd.Series(prices).dropna()
    if len(d) and (d.sales_price.isna().any() or not np.isfinite(d.sales_price).all()
                   or d.sales_price.le(0).any()):
        raise ValueError("Cada deal precisa de preço de catálogo positivo e finito.")
    if len(d) and (not len(prices) or prices.le(0).any()):
        raise ValueError("Catálogo de preços inválido.")
    cliff = m["cliff"]
    d["age_days"] = (pd.Timestamp(today) - d.engage_date).dt.days
    d["days_left"] = cliff - d.age_days if cliff is not None else np.nan
    d["deadline"] = d.engage_date + pd.Timedelta(days=cliff) if cliff is not None else pd.NaT
    engaging = d.deal_stage.eq("Engaging")
    prospect = d.deal_stage.eq("Prospecting")
    no_date = engaging & d.engage_date.isna()
    stale = (engaging & d.age_days.gt(cliff)) if cliff is not None and review_old else pd.Series(False, index=d.index)
    stale = stale | no_date
    alive = engaging & ~stale

    if cliff is None:  # sem histórico: só o valor ordena
        d["prob"] = np.where(stale, 0.0, 1.0)
    else:
        d["prob"] = m["base"]
        d.loc[alive, "prob"] = d.loc[alive, "age_days"].clip(0, cliff).astype(int).map(m["curve"])
        if not review_old:
            # Sensibilidade: fora do suporte histórico, usar a média como proxy explícita.
            d.loc[alive & d.age_days.gt(cliff), "prob"] = m["base"]
        d.loc[stale, "prob"] = 0.0
    d["valor_esperado"] = (d.prob * d.sales_price).round().astype(int)

    top = float(m["curve"].max()) if cliff is not None else 1.0
    if top <= 0:
        d["score"] = 0  # nenhuma vitória observada: zero evidência, nunca ACT_HOT
    else:
        lo, hi = np.log(0.05 * prices.min()), np.log(top * prices.max())
        lev = np.log(d.valor_esperado.clip(lower=1).astype(float))
        d["score"] = ((lev - lo) / (hi - lo) * 100).clip(0, 100).round().astype(int) if hi > lo else 100
        d.loc[d.valor_esperado.eq(0), "score"] = 0

    last = alive & d.age_days.ge(m["last_call"]) if m.get("last_call") is not None else alive & False
    d["acao"] = np.select([stale, prospect, last, d.score >= HOT, d.score >= WARM],
                          [ACT_STALE, ACT_PROSPECT, ACT_LAST, ACT_HOT, ACT_WARM], ACT_LOW)
    d["urgencia"] = np.where(alive, d.days_left, 10_000)  # desempate: menor distância à referência histórica vem antes
    cols = ["verdade", "por_que", "comando"]
    d[cols] = pd.DataFrame([_why(r, m) for r in d.itertuples()], index=d.index, columns=cols)
    return d


def _why(r, m):
    """Fato observado → hipótese/limitação → próximo passo com decisão humana."""
    v = f"{r.product} (${r.sales_price:,.0f})"
    cliff = m["cliff"]
    if cliff is None and r.acao in ALIVE:
        t = (v, "Sem histórico de fechamentos: só o valor ordena.",
             "Confirmar o próximo passo com o cliente esta semana.")
    elif r.acao == ACT_STALE and pd.isna(r.age_days):
        t = (v + ", Engaging sem data de engajamento",
             "Sem a data não dá para comparar a idade com o histórico.",
             "Hoje: preencher a data de engajamento e confirmar o status com o cliente.")
    elif r.acao == ACT_STALE:
        t = (v + f", aberto há {r.age_days:.0f} dias",
             f"Acima do maior ciclo observado ({cliff} dias em {m['n_closed']:,} negociações encerradas). "
             "Isso pede revisão; não comprova perda.",
             "Até sexta: confirmar interesse e próximo passo com o cliente. Requalificar ou encerrar "
             "apenas após avaliação humana e registro do motivo.")
    elif r.acao == ACT_PROSPECT:
        t = (v + ", ainda sem engajamento",
             "Conversão de prospecção desconhecida. O valor sob hipótese usa a média dos engajados "
             "como proxy não validada; esta fila é ordenada por preço.",
             "Primeiro contato esta semana, começando pelos de maior valor.")
    elif r.acao == ACT_LAST:
        t = (v + f", {r.age_days:.0f} dias, taxa sob hipótese {r.prob:.0%}",
             f"Referência histórica de {cliff} dias em {r.deadline:%d/%m}. A curva cai abaixo da metade "
             "da média sob a hipótese de abertos antigos como perdas; não é prazo fatal.",
             "Esta semana: revisar interesse e combinar próximo passo. Sem resposta, reavaliar "
             "cadência com o responsável; idade sozinha não determina encerramento.")
    elif r.acao in (ACT_HOT, ACT_WARM) and r.age_days <= m["loss_median"]:
        t = (v + f", {r.age_days:.0f} dias em negociação",
             f"Metade das perdas registradas acontece até o dia {m['loss_median']}. "
             "Isso não determina o desfecho deste deal.",
             "Marcar a próxima conversa em até 48h.")
    elif r.acao in (ACT_HOT, ACT_WARM):
        t = (v + f", {r.age_days:.0f} dias, taxa sob hipótese {r.prob:.0%}",
             f"Valor sob hipótese de ${r.valor_esperado:,.0f}; referência histórica em {r.deadline:%d/%m}. "
             "Não é previsão de receita nem probabilidade calibrada.",
             "Confirmar próximo passo esta semana e revisar a prioridade com o cliente.")
    else:
        t = (v + (f", {r.age_days:.0f} dias" if pd.notna(r.age_days) else ""),
             f"Preço de catálogo ${r.sales_price:,.0f}; menor prioridade pela regra atual. "
             "Não há dados de custo do atendimento para concluir rentabilidade.",
             "Após os prioritários, revisar interesse e adequação do produto com o cliente.")
    if pd.isna(r.account):
        t = (t[0] + "; conta não preenchida", t[1], NO_ACCOUNT_CMD + t[2])
    return t


def ranked(d):
    """Ordem de trabalho: score, depois menor distância à referência histórica, depois valor esperado e ID (estável)."""
    return d.sort_values(["score", "urgencia", "valor_esperado", "opportunity_id"],
                         ascending=[False, True, False, True], kind="stable")


def monday_plan(d, n=5):
    """Plano de segunda: n deals vivos por valor esperado; a Revisão próxima mais valiosa sempre entra.

    Deals parados nunca entram no top n: viram uma tarefa de revisão separada. Se faltar deal vivo,
    completa com primeiro contato nas prospecções de maior valor.
    """
    if n <= 0 or d.empty:
        return d.iloc[:0].copy()
    alive = d[d.acao.isin(ALIVE)].sort_values(["valor_esperado", "urgencia", "opportunity_id"],
                                             ascending=[False, True, True], kind="stable")
    plan = alive.head(n)
    last = alive[alive.acao.eq(ACT_LAST) & alive.days_left.gt(0)]  # referência já atingida hoje
    if len(last) and not plan.acao.eq(ACT_LAST).any() and len(plan) == n:
        plan = pd.concat([plan.iloc[: n - 1], last.head(1)])
    if len(plan) < n:
        plan = pd.concat([plan, ranked(d[d.acao.eq(ACT_PROSPECT)]).head(n - len(plan))])
    return plan


def exposure(d):
    """Quanto do valor nominal aberto está em deals mais velhos que qualquer negociação já encerrada."""
    stale = d.acao.eq(ACT_STALE)
    total = float(d.sales_price.sum())
    return {"n_stale": int(stale.sum()), "stale_value": float(d.loc[stale, "sales_price"].sum()),
            "open_value": total}


def diagnosis_rates(history, open_deals, at=TODAY):
    """Taxas com o mesmo recorte das contagens; referência de idade permanece global."""
    closed = history.loc[_closed_at(history, at)]
    n, wins = len(closed), int(closed.deal_stage.eq("Won").sum())
    # Sem data pede revisão, mas não é evidência de idade acima do máximo.
    stale = int((open_deals.acao.eq(ACT_STALE) & open_deals.age_days.notna()).sum())
    return {"n_closed": n, "n_stale": stale,
            "crm_rate": wins / n if n else np.nan,
            "assumed_rate": wins / (n + stale) if n else np.nan}


def team_audit(d):
    """Visão do manager: quanto do pipeline de cada vendedor está parado."""
    if d.empty:
        return pd.DataFrame(columns=["manager", "sales_agent", "Abertos", "Vivos", "Revisão próxima",
                                     "Parados", "Sem conta", "% parado", "Valor parado"])
    g = d.groupby(["manager", "sales_agent"], dropna=False)
    out = pd.DataFrame({
        "Abertos": g.size(),
        "Vivos": g.acao.apply(lambda s: int(s.isin(ALIVE).sum())),
        "Revisão próxima": g.acao.apply(lambda s: int(s.eq(ACT_LAST).sum())),
        "Parados": g.acao.apply(lambda s: int(s.eq(ACT_STALE).sum())),
        "Sem conta": g.account.apply(lambda s: int(s.isna().sum())),
        "Valor parado": g.apply(lambda x: int(x.loc[x.acao.eq(ACT_STALE), "sales_price"].sum()),
                                include_groups=False),
    })
    out["% parado"] = out.Parados.astype(float) / out.Abertos.astype(float)
    return out.reset_index().sort_values(["% parado", "sales_agent"], ascending=[False, True])


def auc(y, s):
    """AUC via ranks (Mann-Whitney). NaN quando falta uma das classes ou há score inválido."""
    y, s = np.asarray(y, bool), np.asarray(s, float)
    if len(y) != len(s):
        raise ValueError("Rótulos e scores devem ter o mesmo tamanho.")
    n1, n0 = y.sum(), (~y).sum()
    if not n1 or not n0 or not np.isfinite(s).all():
        return np.nan
    r = pd.Series(s).rank().values
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def temporal_split(df, at):
    """Histórico rotulado: fechados até o corte. Avaliação: engajados e ainda abertos.

    fit(df, at) também usa abertos antigos como pseudo-negativos; estes não estão em train."""
    at = pd.Timestamp(at)
    train = df.loc[_closed_at(df, at)].copy()
    test = df.loc[df.engage_date.notna() & df.engage_date.le(at)
                  & (df.close_date.isna() | df.close_date.gt(at))].copy()
    overlap = set(train.opportunity_id) & set(test.opportunity_id)
    assert not overlap, f"IDs no treino e no teste: {sorted(overlap)}"
    return train, test


def backtest(df, snapshots=("2017-04-01", "2017-05-01", "2017-06-01", "2017-07-01")):
    """Para cada corte: aprende só com o passado e mede AUC nos deals abertos naquele dia.

    Rótulo = desfecho REGISTRADO até 31/12/2017. Deals que seguem abertos ficam fora da AUC e são
    contados em `ainda_abertos` (nenhum vira perda presumida aqui). Os cortes reutilizam deals,
    então as linhas não são amostras independentes.
    """
    rows = []
    for snap in map(pd.Timestamp, snapshots):
        train, test = temporal_split(df, snap)
        m = fit(df, snap)
        resolved = _closed_at(test, TODAY)
        row = {"corte": snap.date(), "abertos_no_corte": len(test),
               "com_desfecho": int(resolved.sum()), "ainda_abertos": int((~resolved).sum())}
        t = test[resolved]
        y = t.deal_stage.eq("Won").values
        if len(test) and m["cliff"] is not None:
            s = score(t.assign(deal_stage="Engaging", close_date=pd.NaT, close_value=np.nan), m, today=snap,
                      prices=df.sales_price.dropna())
            row["score"] = auc(y, s.score)
            row["idade"] = auc(y, s.prob)
        else:
            row["score"] = row["idade"] = np.nan
        row["preço"] = auc(y, t.sales_price)
        tr = train.assign(won=train.deal_stage.eq("Won"))
        for col, name in [("sales_agent", "vendedor"), ("product", "produto"),
                          ("sector", "setor"), ("account", "conta")]:
            rate = tr.groupby(col).won.mean()
            row[name] = auc(y, t[col].map(rate).fillna(tr.won.mean() if len(tr) else 0.5))
        rows.append(row)
    return pd.DataFrame(rows).round(3)


if __name__ == "__main__":  # python scoring.py
    df = load()
    prices = pd.read_csv(DATA / "products.csv").sales_price
    m = fit(df)
    o = score(df[df.deal_stage.isin(OPEN)], m, prices=prices)
    assert len(o) == 2089 and o.score.between(0, 100).all()
    stale = o[o.acao == ACT_STALE]
    assert (stale.age_days > m["cliff"]).all() and (stale.valor_esperado == 0).all()
    assert not o[o.age_days.eq(m["cliff"])].acao.eq(ACT_STALE).any(), "dia 138 ainda está no suporte histórico"
    for _, g in o.groupby("sales_agent"):
        assert not monday_plan(g).acao.eq(ACT_STALE).any()
    assert team_audit(o).Abertos.sum() == len(o)
    ex = exposure(o)
    print(f"Maior ciclo entre {m['n_closed']:,} fechados: {m['cliff']} dias. "
          f"Abertos além disso: {ex['n_stale']:,} (${ex['stale_value']:,.0f} de ${ex['open_value']:,.0f}, "
          f"{ex['stale_value'] / ex['open_value']:.0%}).")
    print(f"Taxa de ganho entre fechados: {m['crm_rate']:.1%}. Contando os parados como perda "
          f"(hipótese): {m['base']:.1%}. Revisão próxima a partir do dia {m['last_call']}.\n")
    print(o.acao.value_counts().to_string(), "\n")
    print(backtest(df).to_string(index=False))
    print("\nOK")
