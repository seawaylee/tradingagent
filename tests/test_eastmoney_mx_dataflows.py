import unittest
from unittest.mock import patch

from tradingagents.default_config import build_runtime_config
from tradingagents.dataflows import interface
from tradingagents.dataflows.eastmoney_mx import get_fundamentals, get_news


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class EastmoneyMXDataflowTests(unittest.TestCase):
    @patch("tradingagents.dataflows.eastmoney_mx.requests.post")
    @patch("tradingagents.dataflows.eastmoney_mx._get_mx_api_key", return_value="mx-test-key")
    def test_get_news_filters_by_date_and_symbol(self, _mock_key, mock_post):
        mock_post.return_value = _FakeResponse(
            {
                "status": 0,
                "data": {
                    "data": {
                        "llmSearchResponse": {
                            "data": [
                                {
                                    "title": "紫金矿业一季度业绩预增",
                                    "content": "内容A",
                                    "date": "2026-04-02 10:00:00",
                                    "informationType": "NEWS",
                                    "secuList": [{"secuCode": "601899", "secuName": "紫金矿业"}],
                                },
                                {
                                    "title": "其他公司新闻",
                                    "content": "内容B",
                                    "date": "2026-04-02 09:00:00",
                                    "informationType": "NEWS",
                                    "secuList": [{"secuCode": "600519", "secuName": "贵州茅台"}],
                                },
                                {
                                    "title": "紫金矿业过期新闻",
                                    "content": "内容C",
                                    "date": "2026-03-20 09:00:00",
                                    "informationType": "NEWS",
                                    "secuList": [{"secuCode": "601899", "secuName": "紫金矿业"}],
                                },
                            ]
                        }
                    }
                },
            }
        )

        result = get_news("601899", "2026-04-01", "2026-04-03")

        self.assertIn("紫金矿业一季度业绩预增", result)
        self.assertNotIn("其他公司新闻", result)
        self.assertNotIn("紫金矿业过期新闻", result)
        self.assertIn("601899.SH", result)

    @patch("tradingagents.dataflows.eastmoney_mx.requests.post")
    @patch("tradingagents.dataflows.eastmoney_mx._get_mx_api_key", return_value="mx-test-key")
    def test_get_fundamentals_formats_query_tables(self, _mock_key, mock_post):
        mock_post.return_value = _FakeResponse(
            {
                "status": 0,
                "data": {
                    "data": {
                        "searchDataResultDTO": {
                            "dataTableDTOList": [
                                {
                                    "title": "紫金矿业关键财务摘要",
                                    "table": {
                                        "headName": ["2025-12-31"],
                                        "f1": [518.0],
                                        "f2": [3491.0],
                                    },
                                    "nameMap": {
                                        "f1": "归母净利润",
                                        "f2": "营业总收入",
                                    },
                                    "indicatorOrder": ["f1", "f2"],
                                }
                            ]
                        }
                    }
                },
            }
        )

        result = get_fundamentals("601899", "2026-04-03")

        self.assertIn("# A-share company profile for 601899.SH", result)
        self.assertIn("紫金矿业关键财务摘要", result)
        self.assertIn("归母净利润", result)
        self.assertIn("营业总收入", result)
        self.assertIn("2025-12-31", result)

    def test_route_to_vendor_falls_back_when_primary_vendor_raises(self):
        def _mx_fail(*args, **kwargs):
            raise RuntimeError("mx unavailable")

        def _akshare_ok(*args, **kwargs):
            return "akshare result"

        with patch.dict(interface.VENDOR_METHODS["get_news"], {"mx": _mx_fail, "akshare": _akshare_ok}, clear=True):
            with patch("tradingagents.dataflows.interface.get_vendor", return_value="mx,akshare"):
                result = interface.route_to_vendor("get_news", "601899", "2026-04-01", "2026-04-03")

        self.assertEqual("akshare result", result)

    def test_build_runtime_config_keeps_default_tool_vendors_when_last_config_is_empty(self):
        with patch("tradingagents.default_config.load_last_config", return_value={"tool_vendors": {}}):
            runtime_config = build_runtime_config()

        self.assertEqual("mx,akshare", runtime_config["tool_vendors"]["get_news"])
        self.assertEqual("mx,akshare", runtime_config["tool_vendors"]["get_fundamentals"])


if __name__ == "__main__":
    unittest.main()
