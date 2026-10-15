"""Testes da interface com dados reais; execute via unittest discover."""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest
import scoring as sc

APP = Path(__file__).with_name("app.py")


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = sc.load()
        cls.opened = sc.score(source[source.deal_stage.isin(sc.OPEN)], sc.fit(source))

    def app(self):
        app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0)
        return app

    def test_initial_totals_and_disclosed_limit(self):
        app = self.app()
        self.assertEqual(
            [metric.value for metric in app.metric[:3]], ["298", "1291", "500"]
        )
        self.assertTrue(
            any(
                "Não representa chance de compra" in caption.value
                for caption in app.caption
            )
        )
        self.assertEqual(len(app.tabs), 5)

    def test_seller_filters_rows_and_plan_without_changing_scores(self):
        app = self.app()
        app.selectbox[2].select("Vicki Laflamme").run()
        self.assertEqual(len(app.exception), 0)
        selected = self.opened[self.opened.sales_agent.eq("Vicki Laflamme")]
        counts = [
            str(selected.acao.eq(action).sum())
            for action in [sc.ACT_NEGOTIATE, sc.ACT_REVIEW, sc.ACT_PROSPECT]
        ]
        self.assertEqual([metric.value for metric in app.metric[:3]], counts)
        for table in app.dataframe:
            if "Vendedor" in table.value:
                self.assertEqual(set(table.value["Vendedor"]), {"Vicki Laflamme"})
        headers = [
            item.value
            for item in app.markdown
            if any(item.value.startswith(f"**{i}.") for i in range(1, 6))
        ]
        self.assertEqual(len(headers), min(5, len(selected)))
        table = next(
            table.value
            for table in app.dataframe
            if "Prioridade (0–100)" in table.value
        )
        expected = selected.set_index("opportunity_id").score
        for _, row in table.iterrows():
            self.assertEqual(row["Prioridade (0–100)"], expected[row["ID"]])

    def test_empty_filter_is_explained_and_recovers(self):
        products = set(self.opened["product"])
        seller, absent = next(
            (seller, sorted(products - set(group["product"]))[0])
            for seller, group in self.opened.groupby("sales_agent")
            if products - set(group["product"])
        )
        app = self.app()
        app.selectbox[2].select(seller).run()
        app.multiselect[0].set_value([absent]).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(
            any("Nenhuma oportunidade aberta" in message.value for message in app.info)
        )
        self.assertEqual(len(app.metric), 0)
        app.multiselect[0].set_value([]).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.metric), 4)

    def test_region_and_manager_filters_cascade(self):
        app = self.app()
        region = app.selectbox[0].options[1]
        app.selectbox[0].select(region).run()
        expected = self.opened[self.opened.regional_office.eq(region)]
        self.assertEqual(set(app.selectbox[1].options[1:]), set(expected.manager))
        manager = app.selectbox[1].options[1]
        app.selectbox[1].select(manager).run()
        expected = expected[expected.manager.eq(manager)]
        self.assertEqual(set(app.selectbox[2].options[1:]), set(expected.sales_agent))
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()
