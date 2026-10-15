"""Testes da interface com dados reais (streamlit.testing).

Execute: python -m unittest discover -s . -p 'test_*.py'
"""
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

import scoring as sc

APP = str(Path(__file__).with_name("app.py"))


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df = sc.load()
        cls.o = sc.score(df[df.deal_stage.isin(sc.OPEN)], sc.fit(df))

    def run_app(self):
        at = AppTest.from_file(APP, default_timeout=60).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def test_every_seller_renders_plan_without_errors(self):
        at = self.run_app()
        for agent in sorted(self.o.sales_agent.unique()):
            at.selectbox[0].select(agent).run()
            self.assertEqual(len(at.exception), 0, agent)
            g = self.o[self.o.sales_agent.eq(agent)]
            cards = [md for md in at.markdown if any(md.value.startswith(f"**{i}.") for i in range(1, 6))]
            self.assertEqual(len(cards), min(5, g.acao.isin(sc.ALIVE + [sc.ACT_PROSPECT]).sum()), agent)
            self.assertEqual(at.metric[2].value, str(g.acao.eq(sc.ACT_STALE).sum()), agent)

    def test_manager_view_totals_and_filters_cascade(self):
        at = self.run_app()
        at.radio[0].set_value("Gerente").run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.metric[0].value, "1,291")
        region = at.selectbox[0].options[1]
        at.selectbox[0].select(region).run()
        expected = self.o[self.o.regional_office.eq(region)]
        self.assertEqual(set(at.selectbox[1].options[1:]), set(expected.manager))
        self.assertEqual(at.metric[0].value, f"{expected.acao.eq(sc.ACT_STALE).sum():,}")

    def test_empty_product_filter_is_explained_and_recovers(self):
        at = self.run_app()
        at.radio[0].set_value("Gerente").run()
        sub = self.o[self.o.manager.eq("Dustin Brinkmann")]
        missing = sorted(set(self.o["product"]) - set(sub["product"]))
        self.assertTrue(missing)
        at.selectbox[1].select("Dustin Brinkmann").run()
        at.multiselect[0].set_value(missing[:1]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any("Nenhum deal aberto" in i.value for i in at.info))
        at.multiselect[0].set_value([]).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.metric[0].value, f"{sub.acao.eq(sc.ACT_STALE).sum():,}")

if __name__ == "__main__":
    unittest.main()
