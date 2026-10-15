"""Testes de integridade temporal e das regras que sustentam a priorização."""
import unittest

import numpy as np
import pandas as pd

import scoring as sc


def deal(
    identifier, stage="Engaging", age=40, price=100, close_date=None, account="Conta"
):
    return {
        "opportunity_id": identifier,
        "deal_stage": stage,
        "engage_date": sc.TODAY - pd.Timedelta(days=age) if age is not None else pd.NaT,
        "close_date": pd.Timestamp(close_date) if close_date else pd.NaT,
        "sales_price": price,
        "account": account,
        "product": "Produto",
        "sales_agent": "Vendedor",
        "manager": "Manager",
    }


def frame(*rows):
    return pd.DataFrame(rows).astype(
        {"engage_date": "datetime64[ns]", "close_date": "datetime64[ns]"}
    )


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.history = frame(
            deal("won", "Won", age=138, price=10, close_date="2017-12-31"),
            deal("lost", "Lost", age=80, price=1000, close_date="2017-12-30"),
        )
        self.model = sc.fit(self.history)

    def test_reference_boundary_keeps_138_in_negotiation_and_reviews_139(self):
        source = frame(deal("at", age=138), deal("after", age=139))
        scored = sc.score(source, self.model).set_index("opportunity_id")
        self.assertEqual(scored.loc["at", "acao"], sc.ACT_NEGOTIATE)
        self.assertEqual(scored.loc["after", "acao"], sc.ACT_REVIEW)
        self.assertEqual(scored.loc["at", "deal_stage"], "Engaging")
        self.assertEqual(scored.loc["after", "deal_stage"], "Engaging")

    def test_open_deals_never_become_inferred_losses(self):
        source = frame(deal("old", age=500), deal("prospect", "Prospecting", age=None))
        outcomes = sc.outcomes(source)
        self.assertFalse(outcomes.known.any())
        self.assertTrue(outcomes.won.isna().all())
        scored = sc.score(source, self.model)
        self.assertEqual(list(scored.deal_stage), list(source.deal_stage))
        self.assertFalse(
            {"prob", "valor_esperado", "days_left", "deadline"} & set(scored.columns)
        )

    def test_fit_uses_only_recorded_closed_outcomes_at_cut(self):
        source = pd.concat(
            [self.history, frame(deal("old", age=900))], ignore_index=True
        )
        model = sc.fit(source)
        self.assertEqual(model["n_closed"], 2)
        self.assertEqual(model["closed_win_rate"], 0.5)
        self.assertEqual(model["reference_max_cycle"], 138)
        before = sc.fit(source, "2017-12-30")
        self.assertEqual(before["n_closed"], 1)
        self.assertEqual(before["closed_win_rate"], 0)
        self.assertEqual(before["reference_max_cycle"], 79)

    def test_temporal_split_includes_day_of_close_only_in_train(self):
        source = frame(
            deal("on-cut", "Won", age=100, close_date="2017-12-01"),
            deal("later", "Lost", age=100, close_date="2017-12-02"),
            deal("unresolved", age=200, account=None),
            deal("not-yet-engaged", age=10),
        )
        train, test = sc.temporal_split(source, "2017-12-01")
        self.assertEqual(set(train.opportunity_id), {"on-cut"})
        self.assertEqual(set(test.opportunity_id), {"later", "unresolved"})
        self.assertFalse(set(train.opportunity_id) & set(test.opportunity_id))

    def test_duplicate_ids_cannot_cross_train_test_boundary(self):
        source = frame(
            deal("same", "Won", age=100, close_date="2017-12-01"), deal("same", age=100)
        )
        with self.assertRaises(AssertionError):
            sc.temporal_split(source, "2017-12-01")

    def test_backtest_counts_censored_and_keeps_missing_accounts(self):
        source = frame(
            deal("train", "Won", age=100, price=10, close_date="2017-12-01"),
            deal(
                "won", "Won", age=80, price=1000, close_date="2017-12-02", account=None
            ),
            deal("lost", "Lost", age=90, close_date="2017-12-03"),
            deal("open", age=200),
        )
        row = sc.backtest(source, snapshots=["2017-12-01"]).iloc[0]
        self.assertEqual(
            (row.n_train, row.n_test, row.n_resolved, row.n_unresolved), (1, 3, 2, 1)
        )
        self.assertEqual(row.train_test_overlap, 0)
        self.assertEqual(row.auc_price, 1)

    def test_score_is_monotonic_by_price_and_age(self):
        source = frame(
            deal("small", age=0, price=10),
            deal("middle", age=0, price=100),
            deal("large", age=0, price=1000),
            deal("older", age=138, price=1000),
        )
        scored = sc.score(source, self.model)
        self.assertTrue(scored.score.is_monotonic_increasing)
        self.assertEqual(list(scored.score), [0, 30, 60, 100])

    def test_prospect_score_depends_only_on_value(self):
        source = frame(
            deal("p1", "Prospecting", age=None, price=100),
            deal("p2", "Prospecting", age=100, price=100),
        )
        scored = sc.score(source, self.model)
        self.assertEqual(list(scored.score), [50, 50])
        self.assertTrue(scored.acao.eq(sc.ACT_PROSPECT).all())

    def test_filter_does_not_change_scores_or_relative_order(self):
        source = frame(
            deal("small", price=10),
            deal("middle", price=100),
            deal("large", price=1000),
        )
        scored = sc.score(source, self.model)
        selected = source.sales_price.ge(100)
        filtered = sc.score(source.loc[selected], self.model)
        pd.testing.assert_series_equal(scored.loc[selected, "score"], filtered.score)
        self.assertEqual(
            list(sc.ranked(scored.loc[selected]).opportunity_id),
            list(sc.ranked(filtered).opportunity_id),
        )

    def test_monday_plan_has_two_reviews_and_three_negotiations(self):
        source = frame(
            *(deal(f"r{i}", age=139 + i) for i in range(4)),
            *(deal(f"n{i}", age=i, price=10 ** (i + 1)) for i in range(3)),
            deal("p", "Prospecting", age=None, price=1000),
        )
        scored = sc.score(source, self.model)
        plan = sc.monday_plan(scored)
        self.assertEqual(list(plan.opportunity_id), ["r3", "r2", "n2", "n1", "n0"])
        self.assertEqual(plan.opportunity_id.nunique(), 5)
        complete = sc.monday_plan(scored, n=100)
        self.assertEqual(set(complete.opportunity_id), set(scored.opportunity_id))
        self.assertEqual(len(complete), len(scored))

    def test_monday_plan_fills_short_queues_and_includes_missing_account(self):
        source = frame(
            deal("r", age=200, account=None),
            deal("n", age=50),
            deal("p", "Prospecting", age=None),
        )
        plan = sc.monday_plan(sc.score(source, self.model))
        self.assertEqual(list(plan.opportunity_id), ["r", "n", "p"])
        self.assertTrue(plan.iloc[0].comando.startswith(sc.NO_ACCOUNT_CMD))
        self.assertNotIn("nenhum deal sem conta", plan.iloc[0].comando.lower())

    def test_missing_engagement_date_requires_review(self):
        scored = sc.score(frame(deal("missing", age=None)), self.model).iloc[0]
        self.assertEqual(scored.acao, sc.ACT_REVIEW)
        self.assertIn("Validar a data", scored.comando)

    def test_no_history_and_empty_inputs_are_supported(self):
        source = frame(deal("open", age=40))
        model = sc.fit(source)
        self.assertIsNone(model["reference_max_cycle"])
        self.assertTrue(np.isnan(model["closed_win_rate"]))
        self.assertEqual(sc.score(source, model).iloc[0].acao, sc.ACT_NEGOTIATE)
        empty = source.iloc[:0]
        scored = sc.score(empty, sc.fit(empty))
        self.assertTrue(scored.empty)
        self.assertTrue(sc.monday_plan(scored).empty)
        self.assertTrue(sc.ranked(scored).empty)
        self.assertTrue(sc.team_audit(scored).empty)
        row = sc.backtest(empty, snapshots=["2017-12-01"]).iloc[0]
        self.assertEqual(row.n_test, 0)
        self.assertTrue(np.isnan(row.auc_score))

    def test_auc_with_single_class_or_missing_score_is_explicitly_unavailable(self):
        self.assertTrue(np.isnan(sc.auc([True], [20])))
        self.assertTrue(np.isnan(sc.auc([True, False], [np.nan, 20])))
        self.assertEqual(sc.auc([True, False], [20, 20]), 0.5)

    def test_invalid_weights_and_prices_are_rejected(self):
        with self.assertRaises(ValueError):
            sc.fit(self.history, value_weight=0.8, age_weight=0.8)
        with self.assertRaises(ValueError):
            sc.score(frame(deal("invalid", price=0)), self.model)

    def test_real_dataset_partition_and_plan_cover_each_salesperson(self):
        df = sc.load()
        model = sc.fit(df)
        opened = df.loc[df.deal_stage.isin(sc.OPEN)]
        scored = sc.score(opened, model)
        self.assertEqual(len(scored), len(opened))
        self.assertEqual(sc.team_audit(scored).Abertos.sum(), len(opened))
        self.assertEqual(scored.opportunity_id.nunique(), len(opened))
        self.assertTrue(scored.score.between(0, 100).all())
        for _, group in scored.groupby("sales_agent"):
            plan = sc.monday_plan(group)
            self.assertEqual(len(plan), min(5, len(group)))
            self.assertEqual(plan.opportunity_id.nunique(), len(plan))
        diagnostic = sc.backtest(df)
        self.assertTrue(diagnostic.train_test_overlap.eq(0).all())
        self.assertTrue(
            diagnostic.n_test.eq(diagnostic.n_resolved + diagnostic.n_unresolved).all()
        )


if __name__ == "__main__":
    unittest.main()
