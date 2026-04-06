import unittest

from cli.utils import normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import build_instrument_context


class HongKongTickerHandlingTests(unittest.TestCase):
    def test_normalize_hk_symbol_preserves_market_suffix(self):
        self.assertEqual(normalize_ticker_symbol("01810.HK"), "01810.HK")
        self.assertEqual(normalize_ticker_symbol("1810.hk"), "01810.HK")
        self.assertEqual(normalize_ticker_symbol("01810"), "01810.HK")

    def test_build_instrument_context_mentions_hk_market(self):
        context = build_instrument_context("01810.HK")

        self.assertIn("01810.HK", context)
        self.assertIn("Hong Kong", context)
        self.assertIn(".HK", context)


if __name__ == "__main__":
    unittest.main()
