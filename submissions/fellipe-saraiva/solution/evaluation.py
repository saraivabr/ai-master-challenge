"""Comparação retrospectiva do plano por vendedor; execute python evaluation.py.

Só desfechos já conhecidos no corte entram no fit. A hipótese opcional de abertos
antigos como pseudo-perdas usa o estado do snapshot, não seu desfecho posterior.
O resultado observado em 90 dias é consultado apenas DEPOIS da seleção dos IDs.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import scoring as sc

SNAPSHOTS = ("2017-04-01", "2017-05-01", "2017-06-01", "2017-07-01")
SCENARIOS = {
    "padrao": (True, True),
    "sem_pseudo_perdas": (False, True),
    "antigos_elegiveis": (False, False),
}


def snapshot(df, at):
    """Remove status, data e valor de fechamento futuros antes de ajustar/ordenar.

    Prospecting não tem data de criação; não sabemos se existia em cortes passados.
    Só engajados até o corte compõem a população reconstruível.
    """
    at = pd.Timestamp(at)
    d = df[df.engage_date.notna() & df.engage_date.le(at)].copy()
    closed = sc._closed_at(d, at)
    d.loc[~closed, "deal_stage"] = "Engaging"
    d.loc[~closed, "close_date"] = pd.NaT
    d.loc[~closed, "close_value"] = np.nan
    return d


def select_policies(df, at, scenario="padrao", n=5):
    """Seleção pura, sem acesso aos rótulos futuros. Baselines usam o mesmo pool.

    No cenário padrão o pool exclui antigos em revisão para TODAS as políticas.
    O cenário antigos_elegiveis mede a sensibilidade a essa exclusão.
    """
    stale_as_loss, review_old = SCENARIOS[scenario]
    known = snapshot(df, at)
    m = sc.fit(known, at, stale_as_loss=stale_as_loss)
    candidates = known[known.deal_stage.eq("Engaging")]
    scored = sc.score(candidates, m, today=at, prices=df.sales_price.dropna(),
                      review_old=review_old)
    choices = {name: [] for name in ("top5", "maior_preco", "maior_idade")}
    for _, group in scored.groupby("sales_agent", sort=True):
        eligible = group[group.acao.isin(sc.ALIVE)]
        choices["top5"].append(sc.monday_plan(group, n))
        choices["maior_preco"].append(eligible.sort_values(
            ["sales_price", "opportunity_id"], ascending=[False, True], kind="stable").head(n))
        choices["maior_idade"].append(eligible.sort_values(
            ["age_days", "opportunity_id"], ascending=[False, True], kind="stable").head(n))
    selected = {name: pd.concat(parts) if parts else scored.iloc[:0]
                for name, parts in choices.items()}
    metadata = {"candidatos": len(scored), "elegiveis": int(scored.acao.isin(sc.ALIVE).sum()),
                "vendedores": scored.sales_agent.nunique(),
                "pseudo_negativos": m.get("n_stale", 0) if stale_as_loss else 0}
    return selected, metadata


def evaluate(df, snapshots=SNAPSHOTS, horizon_days=90, n=5):
    """Métricas observadas, sem converter desconhecidos em rótulos Lost.

    Receita por vaga usa close_value apenas para Won registrado no horizonte.
    Ganhos/vaga é rendimento observado, NÃO estimativa da probabilidade de ganhar.
    Cortes podem selecionar o mesmo deal; nenhuma significância é inferida.
    """
    if not df.opportunity_id.is_unique:
        raise ValueError("opportunity_id deve ser único na avaliação.")
    outcomes = df.set_index("opportunity_id")
    rows, selections = [], []
    for snap in map(pd.Timestamp, snapshots):
        end = snap + pd.Timedelta(days=horizon_days)
        if end > sc.TODAY:
            raise ValueError("Horizonte ultrapassa o último dia observado.")
        for scenario in SCENARIOS:
            policies, metadata = select_policies(df, snap, scenario, n)
            for policy, selected in policies.items():
                observed = outcomes.loc[selected.opportunity_id]
                resolved = sc._closed_at(observed, end) & observed.close_date.gt(snap)
                won = resolved & observed.deal_stage.eq("Won")
                count, known = len(selected), int(resolved.sum())
                revenue = float(observed.loc[won, "close_value"].sum())
                rows.append({"corte": snap.date().isoformat(), "cenario": scenario,
                             "politica": policy, **metadata, "selecionados": count,
                             "resolvidos": known, "desconhecidos": count - known,
                             "ganhos": int(won.sum()), "cobertura": known / count if count else np.nan,
                             "taxa_entre_resolvidos": won.sum() / known if known else np.nan,
                             "ganhos_por_vaga": won.sum() / count if count else np.nan,
                             "receita_observada": revenue,
                             "receita_por_vaga": revenue / count if count else np.nan})
                for r in selected.itertuples():
                    selections.append({"corte": snap.date().isoformat(), "cenario": scenario,
                                       "politica": policy, "sales_agent": r.sales_agent,
                                       "opportunity_id": r.opportunity_id})
    return pd.DataFrame(rows), pd.DataFrame(selections)


def summarize(results):
    """Soma de seleções por corte (não deals únicos), taxas ponderadas pelas contagens."""
    totals = results.groupby(["cenario", "politica"], sort=False)[[
        "selecionados", "resolvidos", "desconhecidos", "ganhos", "receita_observada"]].sum()
    totals["cobertura"] = totals.resolvidos / totals.selecionados
    totals["taxa_entre_resolvidos"] = totals.ganhos / totals.resolvidos
    totals["ganhos_por_vaga"] = totals.ganhos / totals.selecionados
    totals["receita_por_vaga"] = totals.receita_observada / totals.selecionados
    return totals.reset_index()


if __name__ == "__main__":
    results, selected = evaluate(sc.load())
    output = Path(__file__).parent.parent / "docs"
    results.to_csv(output / "baselines.csv", index=False, float_format="%.6f")
    selected.to_csv(output / "baseline-selections.csv", index=False)
    print("Horizonte: 90 dias; 5 vagas por vendedor/corte, se houver elegíveis.")
    print("Seleções repetidas entre cortes; desconhecidos não são perdas.")
    print(summarize(results).round(3).to_string(index=False))
    print("\nDetalhe por corte:\n" + results.round(3).to_string(index=False))
