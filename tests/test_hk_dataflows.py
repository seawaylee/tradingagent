import unittest
from unittest.mock import patch

import pandas as pd
import requests

from tradingagents.dataflows.hk_share import (
    get_balance_sheet,
    get_cashflow,
    get_company_announcements,
    get_fundamentals,
    get_indicators,
    get_income_statement,
    get_news,
    get_stock_data,
)
from tradingagents.dataflows.interface import route_to_vendor


class HongKongDataflowTests(unittest.TestCase):
    @patch("tradingagents.dataflows.interface.get_hk_news")
    def test_route_to_vendor_skips_a_share_only_vendor_for_hk_news(self, mock_hk_news):
        mock_hk_news.return_value = "hk-news"

        with patch(
            "tradingagents.dataflows.interface.get_config",
            return_value={
                "tool_vendors": {"get_news": "mx,akshare"},
                "data_vendors": {},
                "allow_vendor_fallback": False,
            },
        ):
            result = route_to_vendor("get_news", "01810.HK", "2026-02-01", "2026-04-06")

        self.assertEqual("hk-news", result)
        mock_hk_news.assert_called_once_with("01810.HK", "2026-02-01", "2026-04-06")

    @patch("tradingagents.dataflows.interface.get_hk_stock_data")
    @patch("tradingagents.dataflows.interface.get_akshare_stock_data")
    def test_route_to_vendor_uses_hk_stock_data_for_hk_symbol(self, mock_a_share, mock_hk):
        mock_hk.return_value = "hk-result"

        result = route_to_vendor("get_stock_data", "01810.HK", "2024-03-01", "2024-03-05")

        self.assertEqual(result, "hk-result")
        mock_hk.assert_called_once_with("01810.HK", "2024-03-01", "2024-03-05")
        mock_a_share.assert_not_called()

    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_hist")
    def test_get_stock_data_formats_hk_ohlcv(self, mock_hist):
        mock_hist.return_value = pd.DataFrame(
            {
                "日期": ["2024-03-01", "2024-03-04"],
                "开盘": [14.0, 14.2],
                "收盘": [14.2, 14.5],
                "最高": [14.3, 14.7],
                "最低": [13.9, 14.1],
                "成交量": [1000000, 1200000],
                "成交额": [14000000, 17400000],
                "振幅": [2.8, 4.2],
                "涨跌幅": [1.4, 2.1],
                "涨跌额": [0.2, 0.3],
                "换手率": [0.4, 0.5],
            }
        )

        result = get_stock_data("1810.HK", "2024-03-01", "2024-03-04")

        self.assertIn("01810.HK", result)
        self.assertIn("TurnoverPct", result)
        self.assertIn("2024-03-04", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_daily")
    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_hist")
    def test_get_stock_data_falls_back_to_sina_when_eastmoney_fails(self, mock_hist, mock_daily):
        mock_hist.side_effect = requests.exceptions.ConnectionError("Connection aborted")
        mock_daily.return_value = pd.DataFrame(
            {
                "date": ["2024-03-01", "2024-03-04"],
                "open": [14.0, 14.2],
                "close": [14.2, 14.5],
                "high": [14.3, 14.7],
                "low": [13.9, 14.1],
                "volume": [1000000, 1200000],
                "amount": [14000000, 17400000],
            }
        )

        result = get_stock_data("01810.HK", "2024-03-01", "2024-03-04")

        self.assertIn("01810.HK", result)
        self.assertIn("Amount", result)
        self.assertIn("PctChange", result)
        mock_daily.assert_called_once()

    @patch("tradingagents.dataflows.hk_share._load_hk_ohlcv")
    def test_get_indicators_formats_hk_series(self, mock_load_ohlcv):
        mock_load_ohlcv.return_value = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-03-01", "2024-03-04", "2024-03-05"]),
                "Open": [14.0, 14.2, 14.6],
                "High": [14.3, 14.7, 14.8],
                "Low": [13.9, 14.1, 14.4],
                "Close": [14.2, 14.5, 14.7],
                "Volume": [1000000, 1200000, 1100000],
            }
        )

        result = get_indicators("01810.HK", "close_10_ema", "2024-03-05", 3)

        self.assertIn("01810.HK close_10_ema values", result)
        self.assertIn("2024-03-05:", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_financial_indicator_em")
    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_security_profile_em")
    @patch("tradingagents.dataflows.hk_share.ak.stock_hk_company_profile_em")
    def test_get_fundamentals_builds_hk_summary(self, mock_profile, mock_security, mock_indicator):
        mock_profile.return_value = pd.DataFrame(
            {
                "公司名称": ["小米集团"],
                "所属行业": ["资讯科技器材"],
                "公司介绍": ["智能手机、IoT 与互联网服务公司"],
            }
        )
        mock_security.return_value = pd.DataFrame(
            {
                "证券代码": ["01810.HK"],
                "证券简称": ["小米集团-W"],
                "上市日期": ["2018-07-09"],
                "板块": ["主板"],
            }
        )
        mock_indicator.return_value = pd.DataFrame(
            {
                "基本每股收益(元)": [1.62],
                "每股净资产(元)": [10.22],
                "营业总收入": [457286687000],
                "净利润": [41643389000],
                "市盈率": [17.36],
            }
        )

        result = get_fundamentals("01810.HK", "2026-04-06")

        self.assertIn("Hong Kong stock company profile", result)
        self.assertIn("小米集团", result)
        self.assertIn("核心财务指标", result)
        self.assertIn("市盈率", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_financial_hk_report_em")
    def test_get_balance_sheet_selects_hk_items(self, mock_report):
        mock_report.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2025-12-31", "2025-12-31", "2025-12-31"],
                "STD_ITEM_NAME": ["总资产", "总负债", "股东权益合计"],
                "AMOUNT": [1000.0, 400.0, 600.0],
            }
        )

        result = get_balance_sheet("01810.HK", curr_date="2026-04-06")

        self.assertIn("总资产", result)
        self.assertIn("总负债", result)
        self.assertIn("2025-12-31", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_financial_hk_report_em")
    def test_get_cashflow_selects_hk_items(self, mock_report):
        mock_report.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2025-12-31", "2025-12-31"],
                "STD_ITEM_NAME": ["经营业务现金净额", "融资业务现金净额"],
                "AMOUNT": [300.0, 50.0],
            }
        )

        result = get_cashflow("01810.HK", curr_date="2026-04-06")

        self.assertIn("经营业务现金净额", result)
        self.assertIn("融资业务现金净额", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_financial_hk_report_em")
    def test_get_income_statement_selects_hk_items(self, mock_report):
        mock_report.return_value = pd.DataFrame(
            {
                "REPORT_DATE": ["2025-12-31", "2025-12-31"],
                "STD_ITEM_NAME": ["营业额", "本年度溢利"],
                "AMOUNT": [2000.0, 200.0],
            }
        )

        result = get_income_statement("01810.HK", curr_date="2026-04-06")

        self.assertIn("营业额", result)
        self.assertIn("本年度溢利", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_news_em")
    def test_get_news_formats_hk_news(self, mock_news):
        mock_news.return_value = pd.DataFrame(
            {
                "发布时间": ["2026-04-01 09:00:00"],
                "文章来源": ["东方财富网"],
                "新闻标题": ["小米集团-W 发布新产品"],
                "新闻内容": ["发布会带动市场关注"],
                "新闻链接": ["https://example.com/news"],
            }
        )

        result = get_news("01810.HK", "2026-04-01", "2026-04-06")

        self.assertIn("Hong Kong stock company news", result)
        self.assertIn("小米集团-W 发布新产品", result)

    @patch("tradingagents.dataflows.hk_share.ak.stock_news_em")
    def test_get_company_announcements_filters_hk_disclosure_news(self, mock_news):
        mock_news.return_value = pd.DataFrame(
            {
                "发布时间": ["2026-04-01 09:00:00", "2026-04-01 10:00:00"],
                "文章来源": ["东方财富网", "东方财富网"],
                "新闻标题": ["小米集团-W 公告：董事会决议", "小米集团-W 产品发布会"],
                "新闻内容": ["披露董事会相关事项", "介绍新产品"],
                "新闻链接": ["https://example.com/notice", "https://example.com/news"],
            }
        )

        result = get_company_announcements("01810.HK", "2026-04-01", "2026-04-06")

        self.assertIn("Hong Kong stock company announcements", result)
        self.assertIn("董事会决议", result)
        self.assertNotIn("产品发布会", result)


if __name__ == "__main__":
    unittest.main()
