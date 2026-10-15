"""Regressões do protocolo, incluindo isolamento dos desfechos na seleção."""
import unittest

import numpy as np
import pandas as pd

import evaluation as ev
import scoring as sc
from test_scoring import deal, frame


class EvaluationTests(unittest.TestCase):
    def test_future_outcomes_cannot_change_selected_ids(self):
        df = sc.load()
        at = pd.Timestamp("2017-04-01")
        altered = df.copy()
        future = ~sc._closed_at(altered, at)
        altered.loc[future, "deal_stage"] = "Won"
        altered.loc[future, "close_date"] = pd.Timestamp("2018-01-01")
        altered.loc[future, "close_value"] = 99999999
        for scenario in ev.SCENARIOS:
            actual, _ = ev.select_policies(df, at, scenario)
            changed, _ = ev.select_policies(altered, at, scenario)
            for policy in actual:
                self.assertEqual(list(actual[policy].opportunity_id), list(changed[policy].opportunity_id))
                self.assertTrue(actual[policy].close_date.isna().all())
                self.assertTrue(actual[policy].close_value.isna().all())

    def test_unknown_is_not_loss_and_revenue_uses_only_observed_wins(self):
        df = frame(deal("train", "Won", age=150, close_date="2017-10-01"),
                   deal("win", "Won", age=100, close_date="2017-11-01"),
                   deal("loss", "Lost", age=100, close_date="2017-11-02"),
                   deal("unknown", age=100),
                   deal("beyond-horizon", "Won", age=100, close_date="2017-12-31"))
        df["close_value"] = [10, 123, 0, np.nan, 999]
        results, _ = ev.evaluate(df, snapshots=["2017-10-01"], horizon_days=60)
        for r in results.itertuples():
            self.assertEqual((r.selecionados, r.resolvidos, r.desconhecidos, r.ganhos), (4, 2, 2, 1))
            self.assertEqual(r.receita_observada, 123)
            self.assertEqual(r.taxa_entre_resolvidos, 0.5)
            self.assertEqual(r.ganhos_por_vaga, 0.25)

    def test_sensitivity_and_equal_budgets(self):
        df = sc.load()
        for snap in ev.SNAPSHOTS:
            for scenario in ev.SCENARIOS:
                selected, meta = ev.select_policies(df, snap, scenario)
                budgets = [x.groupby("sales_agent").size() for x in selected.values()]
                for counts in budgets:
                    self.assertTrue(counts.le(5).all())
                    pd.testing.assert_series_equal(counts, budgets[0])
                for chosen in selected.values():
                    self.assertTrue(chosen.opportunity_id.is_unique)
                if scenario == "antigos_elegiveis":
                    self.assertEqual(meta["elegiveis"], meta["candidatos"])
                if scenario != "padrao":
                    self.assertEqual(meta["pseudo_negativos"], 0)

    def test_fit_sensitivity_uses_same_snapshot_without_pseudo_labels(self):
        df = ev.snapshot(sc.load(), "2017-07-01")
        assumed = sc.fit(df, "2017-07-01")
        closed_only = sc.fit(df, "2017-07-01", stale_as_loss=False)
        self.assertGreater(assumed["n_stale"], 0)
        self.assertAlmostEqual(closed_only["base"], closed_only["crm_rate"])
        self.assertLess(assumed["base"], closed_only["base"])

    def test_unobserved_horizon_and_duplicate_ids_are_rejected(self):
        df = sc.load()
        with self.assertRaises(ValueError):
            ev.evaluate(df, snapshots=["2017-12-31"])
        with self.assertRaises(ValueError):
            ev.evaluate(pd.concat([df, df.iloc[:1]]))
