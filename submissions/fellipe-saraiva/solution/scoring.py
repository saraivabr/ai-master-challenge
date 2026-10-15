"""Priorizador heurístico: evidência, contexto e próximo passo.

Score de organização, não probabilidade nem previsão de receita. Negociações:
60% valor relativo logarítmico + 40% idade relativa ao maior ciclo encerrado.
Prospecção: apenas valor. Oportunidades abertas nunca viram perdas inferidas.
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
TODAY = pd.Timestamp("2017-12-31")  # data de referência do dataset
OPEN = ["Engaging", "Prospecting"]
VALUE_WEIGHT, AGE_WEIGHT = 0.6, 0.4
ACT_REVIEW = "Revisar status"
ACT_NEGOTIATE = "Avançar negociação"
ACT_PROSPECT = "Fazer 1º contato"
NO_ACCOUNT_CMD = "Validar e preencher a conta no CRM. "


def load(data_dir=DATA):
    """Carrega as quatro tabelas e normaliza duas grafias divergentes conhecidas."""
    data_dir = Path(data_dir)
    p = pd.read_csv(
        data_dir / "sales_pipeline.csv", parse_dates=["engage_date", "close_date"]
    )
    p["product"] = p["product"].replace({"GTXPro": "GTX Pro"})
    acc = pd.read_csv(data_dir / "accounts.csv")
    acc["sector"] = acc["sector"].replace({"technolgy": "technology"})
    return (
        p.merge(acc, on="account", how="left")
        .merge(pd.read_csv(data_dir / "products.csv"), on="product", how="left")
        .merge(pd.read_csv(data_dir / "sales_teams.csv"), on="sales_agent", how="left")
    )


def _closed_at(df, at):
    return (
        df.close_date.notna()
        & df.close_date.le(at)
        & df.deal_stage.isin(["Won", "Lost"])
    )


def outcomes(deals, at=TODAY):
    """Somente fechamentos registrados têm desfecho; desconhecidos recebem won=NA."""
    at = pd.Timestamp(at)
    closed = _closed_at(deals, at)
    won = pd.Series(pd.NA, index=deals.index, dtype="boolean")
    won.loc[closed] = deals.loc[closed, "deal_stage"].eq("Won")
    life = (at - deals.engage_date).dt.days.astype(float)
    life.loc[closed] = (
        deals.loc[closed, "close_date"] - deals.loc[closed, "engage_date"]
    ).dt.days
    return pd.DataFrame({"life": life, "won": won, "known": closed}, index=deals.index)


def fit(df, at=TODAY, value_weight=VALUE_WEIGHT, age_weight=AGE_WEIGHT):
    """Resume fechados <= corte; pesos são política configurável, não aprendizado.

    O catálogo é estático no dataset. Limites vêm do conjunto completo recebido,
    antes dos filtros de consulta. Sem ciclo válido, a idade contribui zero.
    """
    if (
        not np.isfinite([value_weight, age_weight]).all()
        or min(value_weight, age_weight) < 0
        or not np.isclose(value_weight + age_weight, 1)
    ):
        raise ValueError("Os pesos devem ser não negativos e somar 1.")
    closed = df.loc[_closed_at(df, pd.Timestamp(at))]
    cycle = (closed.close_date - closed.engage_date).dt.days
    cycle = cycle[cycle.ge(0)]
    prices = df.sales_price.dropna()
    if len(prices) and ((prices <= 0).any() or not np.isfinite(prices).all()):
        raise ValueError("Os preços de catálogo devem ser positivos e finitos.")
    return {
        "reference_max_cycle": int(cycle.max()) if len(cycle) else None,
        "closed_win_rate": float(closed.deal_stage.eq("Won").mean())
        if len(closed)
        else np.nan,
        "n_closed": len(closed),
        "price_min": float(prices.min()) if len(prices) else None,
        "price_max": float(prices.max()) if len(prices) else None,
        "value_weight": float(value_weight),
        "age_weight": float(age_weight),
    }


def score(deals, m, today=TODAY, prices=None):
    """0–100: 60% log(preço/min)/log(max/min) + 40% min(idade/referência,1).

    Prospecting usa só valor relativo. Catálogo de preço único tem valor relativo 1.
    `prices`, quando informado, deve ser o catálogo inteiro, nunca o filtro da tela.
    """
    d = deals.copy()
    lo, hi = m["price_min"], m["price_max"]
    if prices is not None:
        prices = pd.Series(prices).dropna()
        lo, hi = (
            (float(prices.min()), float(prices.max())) if len(prices) else (None, None)
        )
    if len(d) and (
        d.sales_price.isna().any()
        or not np.isfinite(d.sales_price).all()
        or d.sales_price.le(0).any()
    ):
        raise ValueError(
            "Cada oportunidade precisa de preço de catálogo positivo e finito."
        )
    if len(d) and (lo is None or hi is None or lo <= 0 or hi < lo):
        raise ValueError("Informe limites válidos do catálogo global.")
    d["age_days"] = (pd.Timestamp(today) - d.engage_date).dt.days
    value = (
        (np.log(d.sales_price / lo) / np.log(hi / lo)).clip(0, 1)
        if len(d) and hi != lo
        else pd.Series(1.0, index=d.index)
    )
    ref = m["reference_max_cycle"]
    age = (d.age_days / ref).clip(0, 1).fillna(0) if ref and ref > 0 else 0.0
    engaging = d.deal_stage.eq("Engaging")
    beyond = (
        engaging & d.age_days.gt(ref)
        if ref is not None
        else pd.Series(False, index=d.index)
    )
    review = beyond | (engaging & d.engage_date.isna())
    prospect = d.deal_stage.eq("Prospecting")
    d["score"] = 100 * (m["value_weight"] * value + m["age_weight"] * age)
    d.loc[prospect, "score"] = 100 * value[prospect]
    d["score"] = d.score.clip(0, 100).round(1)
    d["acao"] = np.select([review, prospect], [ACT_REVIEW, ACT_PROSPECT], ACT_NEGOTIATE)
    d["fila"] = np.select([review, prospect], ["Revisão", "Prospecção"], "Negociação")
    columns = ["observacao", "por_que", "comando"]
    d[columns] = pd.DataFrame(
        [_why(r, m) for r in d.itertuples()], index=d.index, columns=columns
    )
    return d


def _why(r, m):
    """Observação verificável → razão da prioridade → próximo passo verificável."""
    value = f"{r.product} (preço de catálogo: ${r.sales_price:,.0f})"
    if r.acao == ACT_PROSPECT:
        result = (
            value + ", estágio Prospecting",
            "A fila de prospecção é ordenada pelo valor de catálogo; não há histórico da transição para engajamento.",
            "Verificar o histórico de contatos, confirmar aderência e registrar o próximo passo com o responsável.",
        )
    elif pd.isna(r.age_days):
        result = (
            value + ", estágio Engaging sem data de engajamento",
            "A data ausente impede comparar a idade com o histórico.",
            "Validar a data de engajamento e o status com o responsável; registrar o que for confirmado.",
        )
    elif r.acao == ACT_REVIEW:
        result = (
            value + f", aberto há {r.age_days:.0f} dias",
            f"Supera o maior ciclo encerrado observado ({m['reference_max_cycle']} dias). Isso indica revisão, não perda confirmada.",
            "Confirmar com o responsável se há negociação ativa e registrar o próximo passo. Atualizar o status somente com evidência.",
        )
    else:
        result = (
            value + f", {r.age_days:.0f} dias desde o engajamento",
            f"Prioridade {r.score:.1f}/100: política de {m['value_weight']:.0%} valor relativo e {m['age_weight']:.0%} idade relativa. Não é chance de compra.",
            "Confirmar a pendência com o cliente e combinar um próximo passo com responsável e data acordada.",
        )
    if pd.isna(r.account):
        result = (
            result[0] + "; conta não preenchida",
            result[1],
            NO_ACCOUNT_CMD + result[2],
        )
    return result


def ranked(d):
    """Score decrescente; empate: idade, preço e ID. Use dentro de cada fila."""
    return d.sort_values(
        ["score", "age_days", "sales_price", "opportunity_id"],
        ascending=[False, False, False, True],
        na_position="last",
        kind="stable",
    )


def monday_plan(d, n=5):
    """Até 2 revisões por idade + até 3 negociações por score, sem comparar as filas.

    Completa com prospecção, revisão restante, negociação restante, nessa ordem.
    Para n diferente de 5, mantém cotas iniciais limitadas a n. É política de agenda.
    """
    if n < 0:
        raise ValueError("n deve ser não negativo.")
    if n == 0 or d.empty:
        return d.iloc[:0].copy()
    review = d[d.acao.eq(ACT_REVIEW)].sort_values(
        ["age_days", "sales_price", "opportunity_id"],
        ascending=[False, False, True],
        na_position="first",
    )
    negotiation = ranked(d[d.acao.eq(ACT_NEGOTIATE)])
    prospect = ranked(d[d.acao.eq(ACT_PROSPECT)])
    nr = min(2, n, len(review))
    nn = min(3, n - nr, len(negotiation))
    return pd.concat(
        [
            review.head(nr),
            negotiation.head(nn),
            prospect,
            review.iloc[nr:],
            negotiation.iloc[nn:],
        ]
    ).head(n)


def team_audit(d, m=None):
    """Carga de trabalho por vendedor; valores são catálogo, não receita prevista."""
    g = d.groupby(["manager", "sales_agent"], dropna=False)
    out = pd.DataFrame(
        {
            "Abertos": g.size(),
            "Negociação": g.acao.apply(lambda s: s.eq(ACT_NEGOTIATE).sum()),
            "Revisão": g.acao.apply(lambda s: s.eq(ACT_REVIEW).sum()),
            "Prospecção": g.acao.apply(lambda s: s.eq(ACT_PROSPECT).sum()),
            "Sem conta": g.account.apply(lambda s: s.isna().sum()),
            "Valor de catálogo": g.sales_price.sum(),
        }
    )
    out["% em revisão"] = out["Revisão"] / out["Abertos"]
    return out.reset_index().sort_values(
        ["% em revisão", "sales_agent"], ascending=[False, True]
    )


def auc(y, s):
    """AUC por ranks; NA sem duas classes ou valores válidos, sem exclusão silenciosa."""
    y, s = np.asarray(y, bool), np.asarray(s, float)
    if len(y) != len(s):
        raise ValueError("Rótulos e scores devem ter o mesmo tamanho.")
    n1, n0 = y.sum(), (~y).sum()
    if not n1 or not n0 or not np.isfinite(s).all():
        return np.nan
    ranks = pd.Series(s).rank().values
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def temporal_split(df, at):
    """Treino fechado <= corte; teste engajado <= corte e sem fechamento até o corte.

    Reconstrução parcial do snapshot final: sem histórico dos campos nem data de
    criação para reconstituir Prospecting. Não exclui contas ausentes.
    """
    at = pd.Timestamp(at)
    train = df.loc[_closed_at(df, at)].copy()
    test = df.loc[
        df.engage_date.notna()
        & df.engage_date.le(at)
        & (df.close_date.isna() | df.close_date.gt(at))
    ].copy()
    overlap = set(train.opportunity_id) & set(test.opportunity_id)
    assert not overlap, f"IDs presentes no treino e teste: {sorted(overlap)}"
    return train, test


def backtest(df, snapshots=("2017-04-01", "2017-05-01", "2017-06-01", "2017-07-01")):
    """Diagnóstico do score versus preço e idade entre desfechos encerrados observados.

    Não resolvidos ficam censurados e contados. AUC não valida receita nem chances;
    há seleção pelos desfechos conhecidos e dependência entre cortes que reutilizam
    oportunidades. Catálogo estático final; sem histórico dos campos, não é replay
    completo do CRM nem teste prospectivo. Prospecting não pode ser reconstruído.
    """
    rows = []
    for snap in map(pd.Timestamp, snapshots):
        train, test = temporal_split(df, snap)
        m = fit(df, snap)
        truth = outcomes(test, TODAY)
        resolved = truth.known
        # Estágio final só fornece rótulo; os testes eram Engaging no corte reconstruído.
        scores = score(test.assign(deal_stage="Engaging"), m, today=snap)
        y = truth.loc[resolved, "won"].astype(bool)
        observed = scores.loc[resolved]
        rows.append(
            {
                "corte": snap.date(),
                "n_train": len(train),
                "n_test": len(test),
                "n_resolved": int(resolved.sum()),
                "n_unresolved": int((~resolved).sum()),
                "train_test_overlap": 0,
                "auc_score": auc(y, observed.score),
                "auc_price": auc(y, observed.sales_price),
                "auc_age": auc(y, observed.age_days),
            }
        )
    return pd.DataFrame(rows).round(3)


if __name__ == "__main__":
    df = load()
    prices = pd.read_csv(DATA / "products.csv").sales_price
    model = fit(df)
    opened = score(df[df.deal_stage.isin(OPEN)], model, prices=prices)
    assert opened.score.between(0, 100).all()
    assert opened[["observacao", "por_que", "comando"]].notna().all().all()
    assert team_audit(opened).Abertos.sum() == len(opened)
    print(
        f"Referência histórica: {model['reference_max_cycle']} dias; "
        f"ganhos entre {model['n_closed']} encerrados: {model['closed_win_rate']:.1%}"
    )
    print(opened.acao.value_counts().to_string())
    print(backtest(df).to_string(index=False))
    print("OK — score de prioridade, sem probabilidades ou previsão de receita")
