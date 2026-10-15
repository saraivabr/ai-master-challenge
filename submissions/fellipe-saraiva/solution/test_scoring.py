"""Testes das regras de priorização e da integridade temporal do backtest.

Execute: python -m unittest discover -s . -p 'test_*.py'
"""
import hashlib
import unittest

import numpy as np
import pandas as pd

import scoring as sc


def deal(identifier, stage="Engaging", age=40, price=100, close_date=None, account="Conta",
         agent="Vendedor"):
    return {
        "opportunity_id": identifier,
        "deal_stage": stage,
        "engage_date": sc.TODAY - pd.Timedelta(days=age) if age is not None else pd.NaT,
        "close_date": pd.Timestamp(close_date) if close_date else pd.NaT,
        "sales_price": price,
        "account": account,
        "product": "Produto",
        "sector": "setor",
        "sales_agent": agent,
        "manager": "Manager",
    }


def frame(*rows):
    return pd.DataFrame(rows).astype({"engage_date": "datetime64[ns]", "close_date": "datetime64[ns]"})


class FitTests(unittest.TestCase):
    def setUp(self):
        # ciclos: ganho em 138 dias, perda em 10 dias; um aberto há 300 dias (parado)
        self.history = frame(
            deal("won", "Won", age=138, close_date="2017-12-31"),
            deal("lost", "Lost", age=20, close_date="2017-12-21"),
            deal("old", age=300),
        )
        self.m = sc.fit(self.history)

    def test_cliff_is_longest_recorded_cycle(self):
        self.assertEqual(self.m["cliff"], 138)
        self.assertEqual(self.m["n_closed"], 2)
        self.assertEqual(self.m["crm_rate"], 0.5)

    def test_curve_counts_stale_as_loss_only_as_explicit_hypothesis(self):
        # dia 0: 1 ganho entre 3 conhecidos (ganho, perda, parado) → 1/3, abaixo dos 50% do CRM
        self.assertAlmostEqual(self.m["base"], 1 / 3)
        self.assertLess(self.m["base"], self.m["crm_rate"])
        self.assertEqual(self.m["n_stale"], 1)

    def test_fit_ignores_closes_after_cut(self):
        before = sc.fit(self.history, "2017-12-30")
        self.assertEqual(before["n_closed"], 1)
        self.assertEqual(before["cliff"], 10)

    def test_no_history_is_supported(self):
        m = sc.fit(frame(deal("open", age=40)))
        self.assertIsNone(m["cliff"])
        out = sc.score(frame(deal("open", age=40)), m)
        self.assertEqual(len(out), 1)


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.df = sc.load()
        self.m = sc.fit(self.df)
        self.prices = pd.read_csv(sc.DATA / "products.csv").sales_price
        self.o = sc.score(self.df[self.df.deal_stage.isin(sc.OPEN)], self.m, prices=self.prices)

    def test_boundary_day_138_is_alive_and_139_is_stale(self):
        src = frame(deal("at", age=138, price=4821), deal("after", age=139, price=4821))
        out = sc.score(src, self.m, prices=self.prices).set_index("opportunity_id")
        self.assertNotEqual(out.loc["at", "acao"], sc.ACT_STALE)
        self.assertEqual(out.loc["after", "acao"], sc.ACT_STALE)
        self.assertEqual(out.loc["after", "valor_esperado"], 0)

    def test_missing_engage_date_goes_to_cleanup(self):
        out = sc.score(frame(deal("x", age=None)), self.m, prices=self.prices).iloc[0]
        self.assertEqual(out.acao, sc.ACT_STALE)
        self.assertIn("data de engajamento", out.comando)

    def test_age_changes_order_not_only_price(self):
        src = frame(deal("pro_old", age=125, price=4821), deal("basic_new", age=20, price=1096))
        out = sc.score(src, self.m, prices=self.prices).set_index("opportunity_id")
        self.assertGreater(out.loc["basic_new", "score"], out.loc["pro_old", "score"])

    def test_filter_does_not_change_scores(self):
        sub = self.df[self.df.deal_stage.isin(sc.OPEN) & self.df.sales_agent.eq("Vicki Laflamme")]
        again = sc.score(sub, self.m, prices=self.prices)
        pd.testing.assert_series_equal(self.o.loc[sub.index, "score"], again.score)

    def test_real_dataset_partition(self):
        self.assertEqual(len(self.o), 2089)
        self.assertEqual(self.o.opportunity_id.nunique(), 2089)
        self.assertTrue(self.o.score.between(0, 100).all())
        counts = self.o.acao.value_counts()
        self.assertEqual(counts[sc.ACT_STALE], 1291)
        self.assertEqual(counts[sc.ACT_PROSPECT], 500)
        self.assertEqual(self.o.acao.isin(sc.ALIVE).sum(), 298)
        self.assertTrue(self.o[["verdade", "por_que", "comando"]].notna().all().all())

    def test_invalid_prices_are_rejected(self):
        with self.assertRaises(ValueError):
            sc.score(frame(deal("bad", price=0)), self.m, prices=self.prices)

    def test_empty_input(self):
        empty = self.df.iloc[:0]
        out = sc.score(empty, self.m, prices=self.prices)
        self.assertTrue(out.empty)
        self.assertTrue(sc.monday_plan(out).empty)
        self.assertTrue(sc.team_audit(out).empty)


class PlanTests(unittest.TestCase):
    def setUp(self):
        df = sc.load()
        self.m = sc.fit(df)
        prices = pd.read_csv(sc.DATA / "products.csv").sales_price
        self.o = sc.score(df[df.deal_stage.isin(sc.OPEN)], self.m, prices=prices)

    def test_plan_never_contains_stale_and_has_five_unique(self):
        for agent, g in self.o.groupby("sales_agent"):
            plan = sc.monday_plan(g)
            self.assertFalse(plan.acao.eq(sc.ACT_STALE).any(), agent)
            self.assertEqual(plan.opportunity_id.nunique(), len(plan), agent)
            avail = g.acao.isin(sc.ALIVE + [sc.ACT_PROSPECT]).sum()
            self.assertEqual(len(plan), min(5, avail), agent)

    def test_plan_includes_most_valuable_last_call(self):
        for agent, g in self.o.groupby("sales_agent"):
            last = g[g.acao.eq(sc.ACT_LAST)]
            if len(last) and g.acao.isin(sc.ALIVE).sum() >= 5:
                plan = sc.monday_plan(g)
                best = last.sort_values(["valor_esperado", "urgencia", "opportunity_id"],
                                       ascending=[False, True, True]).iloc[0]
                self.assertIn(best.opportunity_id, set(plan.opportunity_id), agent)

    def test_plan_fills_with_prospects_when_no_alive(self):
        g = self.o[self.o.sales_agent.eq("Darcel Schlecht")]
        self.assertEqual(g.acao.isin(sc.ALIVE).sum(), 0)
        plan = sc.monday_plan(g)
        self.assertTrue(plan.acao.eq(sc.ACT_PROSPECT).all())
        self.assertEqual(len(plan), 5)

    def test_team_audit_totals(self):
        t = sc.team_audit(self.o)
        self.assertEqual(t.Abertos.sum(), len(self.o))
        self.assertEqual(t.Parados.sum(), 1291)


class BacktestTests(unittest.TestCase):
    def test_close_on_cut_day_is_train_only(self):
        src = frame(
            deal("on-cut", "Won", age=100, close_date="2017-12-01"),
            deal("later", "Lost", age=100, close_date="2017-12-02"),
            deal("open", age=200, account=None),
            deal("not-yet", age=10),
        )
        train, test = sc.temporal_split(src, "2017-12-01")
        self.assertEqual(set(train.opportunity_id), {"on-cut"})
        self.assertEqual(set(test.opportunity_id), {"later", "open"})

    def test_duplicate_ids_across_boundary_are_rejected(self):
        src = frame(deal("same", "Won", age=100, close_date="2017-12-01"), deal("same", age=100))
        with self.assertRaises(AssertionError):
            sc.temporal_split(src, "2017-12-01")

    def test_unresolved_are_counted_not_labeled(self):
        src = frame(
            deal("train", "Won", age=100, price=10, close_date="2017-12-01"),
            deal("won", "Won", age=80, price=1000, close_date="2017-12-02"),
            deal("lost", "Lost", age=90, price=100, close_date="2017-12-03"),
            deal("open", age=200),
        )
        row = sc.backtest(src, snapshots=["2017-12-01"]).iloc[0]
        self.assertEqual((row.abertos_no_corte, row.com_desfecho, row.ainda_abertos), (3, 2, 1))
        self.assertEqual(row["preço"], 1)

    def test_real_backtest_is_consistent(self):
        bt = sc.backtest(sc.load())
        self.assertTrue((bt.abertos_no_corte == bt.com_desfecho + bt.ainda_abertos).all())
        self.assertTrue(bt.score.between(0.4, 0.6).all())  # documentado: ≈ acaso

    def test_auc_edge_cases(self):
        self.assertTrue(np.isnan(sc.auc([True], [1])))
        self.assertTrue(np.isnan(sc.auc([True, False], [np.nan, 1])))
        self.assertEqual(sc.auc([True, False], [2, 1]), 1.0)





class RegressionTests(unittest.TestCase):
    def test_no_wins_has_zero_score_not_hot(self):
        history = frame(deal("loss", "Lost", age=30, close_date="2017-12-31"))
        m = sc.fit(history)
        with np.errstate(divide="raise", invalid="raise"):
            out = sc.score(frame(deal("open", age=10), deal("prospect", "Prospecting", age=None)), m)
        self.assertTrue(out.valor_esperado.eq(0).all())
        self.assertTrue(out.score.eq(0).all())
        self.assertFalse(out.acao.eq(sc.ACT_HOT).any())

    def test_scoped_rates_use_filtered_closed_and_open(self):
        df = sc.load()
        all_open = sc.score(df[df.deal_stage.isin(sc.OPEN)], sc.fit(df))
        for filters in ({"product": "GTK 500"}, {"regional_office": "Central"},
                        {"manager": "Dustin Brinkmann"},
                        {"regional_office": "West", "product": "GTX Pro"}):
            history, opened = df, all_open
            for key, value in filters.items():
                history, opened = history[history[key].eq(value)], opened[opened[key].eq(value)]
            rates = sc.diagnosis_rates(history, opened)
            closed = history[history.deal_stage.isin(["Won", "Lost"])]
            wins = closed.deal_stage.eq("Won").sum()
            self.assertAlmostEqual(rates["crm_rate"], wins / len(closed))
            self.assertAlmostEqual(rates["assumed_rate"], wins / (len(closed) + rates["n_stale"]))
        gtk = sc.diagnosis_rates(df[df["product"].eq("GTK 500")],
                                 all_open[all_open["product"].eq("GTK 500")])
        self.assertEqual(gtk["n_stale"], 14)
        self.assertEqual(f"{gtk['crm_rate']:.0%} → {gtk['assumed_rate']:.0%}", "60% → 38%")
        self.assertTrue(np.isnan(sc.diagnosis_rates(df.iloc[:0], all_open.iloc[:0])["crm_rate"]))

    def test_recommendations_do_not_infer_loss_or_cost_from_age(self):
        df = sc.load()
        opened = sc.score(df[df.deal_stage.isin(sc.OPEN)], sc.fit(df))
        text = " ".join(opened.comando) + " ".join(opened.por_que)
        for unsupported in ("marcar Lost", "Sem resposta: Lost", "custa mais que", "Prazo final"):
            self.assertNotIn(unsupported, text)
        self.assertTrue(opened[opened.account.isna()].comando.str.startswith(sc.NO_ACCOUNT_CMD).all())


class DataTests(unittest.TestCase):
    def test_csvs_match_recorded_hashes(self):
        """Os CSVs são exatamente os que geraram os números do README (data/SHA256SUMS)."""
        for line in (sc.DATA / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split(maxsplit=1)
            self.assertEqual(hashlib.sha256((sc.DATA / name).read_bytes()).hexdigest(), digest, name)


if __name__ == "__main__":
    unittest.main()
