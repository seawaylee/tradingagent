import unittest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.report_finalizer import create_report_finalizer
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.trader.trader import create_trader
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.graph.conditional_logic import ConditionalLogic


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    def __init__(self, content: str = "测试输出"):
        self.content = content
        self.invocations = []

    def invoke(self, payload):
        self.invocations.append(payload)
        return _FakeResponse(self.content)


class _FailingLLM(_FakeLLM):
    def invoke(self, payload):
        self.invocations.append(payload)
        raise RuntimeError("cleanup failed")


class _FakeMemory:
    def get_memories(self, curr_situation, n_matches=2):
        return [{"recommendation": "历史复盘"}]


class AgentLanguagePromptTest(unittest.TestCase):
    def setUp(self):
        self.original_config = get_config()
        updated_config = self.original_config.copy()
        updated_config["internal_language"] = "English"
        updated_config["final_output_language"] = "Chinese"
        updated_config["output_language"] = "Chinese"
        set_config(updated_config)
        self.memory = _FakeMemory()

    def tearDown(self):
        set_config(self.original_config)

    def _base_state(self):
        return {
            "company_of_interest": "000333.SZ",
            "market_report": "市场报告",
            "sentiment_report": "情绪报告",
            "news_report": "新闻报告",
            "fundamentals_report": "基本面报告",
            "investment_plan": "投资计划",
            "trader_investment_plan": "交易计划",
            "investment_debate_state": {
                "history": "历史辩论",
                "bull_history": "",
                "bear_history": "",
                "latest_speaker": "",
                "current_response": "上一轮观点",
                "judge_decision": "",
                "count": 0,
            },
            "risk_debate_state": {
                "history": "风险历史",
                "aggressive_history": "",
                "conservative_history": "",
                "neutral_history": "",
                "latest_speaker": "",
                "current_aggressive_response": "激进观点",
                "current_conservative_response": "保守观点",
                "current_neutral_response": "中性观点",
                "judge_decision": "",
                "count": 0,
            },
        }

    def test_internal_nodes_use_internal_language_constraints(self):
        bull_llm = _FakeLLM()
        state = self._base_state()

        create_bull_researcher(bull_llm, self.memory)(state)

        bull_prompt = bull_llm.invocations[0]

        self.assertNotIn("selected final output language", bull_prompt)

    def test_user_facing_nodes_use_final_language_constraints(self):
        research_llm = _FakeLLM()
        trader_llm = _FakeLLM()
        state = self._base_state()

        create_research_manager(research_llm, self.memory)(state)
        create_trader(trader_llm, self.memory)(state)

        research_prompt = research_llm.invocations[0]
        trader_system_prompt = trader_llm.invocations[0][0]["content"]

        self.assertIn("A-share research manager and debate facilitator", research_prompt)
        self.assertIn("selected final output language", research_prompt)
        self.assertIn("selected final output language", trader_system_prompt)
        self.assertIn("FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**", trader_system_prompt)
        self.assertNotIn("selected internal language", trader_system_prompt)

    def test_user_facing_nodes_switch_market_wording_for_hk_symbols(self):
        research_llm = _FakeLLM()
        trader_llm = _FakeLLM()
        state = self._base_state()
        state["company_of_interest"] = "01810.HK"

        create_research_manager(research_llm, self.memory)(state)
        create_trader(trader_llm, self.memory)(state)

        research_prompt = research_llm.invocations[0]
        trader_system_prompt = trader_llm.invocations[0][0]["content"]

        self.assertIn("Hong Kong stock research manager", research_prompt)
        self.assertIn("Hong Kong stock trader", trader_system_prompt)
        self.assertIn("southbound flows", trader_system_prompt)
        self.assertNotIn("A-share research manager", research_prompt)
        self.assertNotIn("You are an A-share trader", trader_system_prompt)

    def test_debate_nodes_emit_english_speaker_labels_when_internal_is_english(self):
        state = self._base_state()

        bull_llm = _FakeLLM("Bullish view")
        bear_llm = _FakeLLM("Bearish view")
        aggressive_llm = _FakeLLM("Aggressive view")
        conservative_llm = _FakeLLM("Conservative view")
        neutral_llm = _FakeLLM("Neutral view")

        bull_result = create_bull_researcher(bull_llm, self.memory)(state)
        bear_result = create_bear_researcher(bear_llm, self.memory)(state)
        aggressive_result = create_aggressive_debator(aggressive_llm)(state)
        conservative_result = create_conservative_debator(conservative_llm)(state)
        neutral_result = create_neutral_debator(neutral_llm)(state)

        self.assertIn("Bull Analyst: Bullish view", bull_result["investment_debate_state"]["current_response"])
        self.assertIn("Bear Analyst: Bearish view", bear_result["investment_debate_state"]["current_response"])
        self.assertEqual("Bull Researcher", bull_result["investment_debate_state"]["latest_speaker"])
        self.assertEqual("Bear Researcher", bear_result["investment_debate_state"]["latest_speaker"])
        self.assertIn("Aggressive Analyst: Aggressive view", aggressive_result["risk_debate_state"]["current_aggressive_response"])
        self.assertIn("Conservative Analyst: Conservative view", conservative_result["risk_debate_state"]["current_conservative_response"])
        self.assertIn("Neutral Analyst: Neutral view", neutral_result["risk_debate_state"]["current_neutral_response"])

    def test_debate_routing_uses_latest_speaker_in_internal_english_mode(self):
        logic = ConditionalLogic(max_debate_rounds=1)
        state = self._base_state()

        state["investment_debate_state"]["latest_speaker"] = "Bull Researcher"
        state["investment_debate_state"]["current_response"] = "Bull Analyst: Bullish view"
        self.assertEqual("Bear Researcher", logic.should_continue_debate(state))

        state["investment_debate_state"]["latest_speaker"] = "Bear Researcher"
        state["investment_debate_state"]["current_response"] = "Bear Analyst: Bearish view"
        self.assertEqual("Bull Researcher", logic.should_continue_debate(state))

        state["investment_debate_state"]["count"] = 2
        self.assertEqual("Research Manager", logic.should_continue_debate(state))

    def test_research_manager_sanitizes_sensitive_financial_metaphors(self):
        class _SensitiveMemory:
            def get_memories(self, curr_situation, n_matches=2):
                return [{"recommendation": "曾经出现自杀式下跌、血洗和砸盘，最后腰斩。"}]

        state = self._base_state()
        state["investment_debate_state"]["history"] = "空头提到杀跌、踩踏和暴雷风险。"
        llm = _FakeLLM()

        create_research_manager(llm, _SensitiveMemory())(state)
        prompt = llm.invocations[0]

        self.assertIn("past lessons", prompt)
        self.assertIn("高风险下跌", prompt)
        self.assertIn("大幅回撤", prompt)
        self.assertIn("大额卖出", prompt)
        self.assertIn("大幅下跌", prompt)
        self.assertIn("恐慌性下跌", prompt)
        self.assertIn("集中抛售", prompt)
        self.assertIn("突发利空", prompt)
        self.assertNotIn("自杀式", prompt)
        self.assertNotIn("血洗", prompt)
        self.assertNotIn("砸盘", prompt)
        self.assertNotIn("腰斩", prompt)
        self.assertNotIn("杀跌", prompt)
        self.assertNotIn("踩踏", prompt)
        self.assertNotIn("暴雷", prompt)
        self.assertNotIn("past mistakes", prompt)


    def test_portfolio_manager_keeps_chinese_final_output_constraints(self):
        portfolio_llm = _FakeLLM()
        state = self._base_state()

        create_portfolio_manager(portfolio_llm, self.memory)(state)
        prompt = portfolio_llm.invocations[0]

        self.assertIn("**评级**", prompt)
        self.assertIn("**执行摘要**", prompt)
        self.assertIn("**投资逻辑**", prompt)
        self.assertIn("selected final output language", prompt)
        self.assertIn("Keep the rating keyword itself in English", prompt)


    def test_report_finalizer_builds_final_report_fields(self):
        finalizer_llm = _FakeLLM("终稿内容")
        state = self._base_state()
        state["final_trade_decision"] = "组合经理最终决策"

        result = create_report_finalizer(finalizer_llm)(state)

        self.assertEqual("市场报告", result["final_market_report"])
        self.assertEqual("情绪报告", result["final_sentiment_report"])
        self.assertEqual("新闻报告", result["final_news_report"])
        self.assertEqual("基本面报告", result["final_fundamentals_report"])
        self.assertEqual("投资计划", result["final_investment_plan_report"])
        self.assertEqual("交易计划", result["final_trader_investment_plan_report"])
        self.assertEqual("组合经理最终决策", result["final_trade_decision_report"])
        self.assertEqual([], finalizer_llm.invocations)

    def test_report_finalizer_rewrites_english_leakage_when_final_language_is_chinese(self):
        finalizer_llm = _FakeLLM("清洗后的中文报告")
        state = self._base_state()
        state["market_report"] = "Now let me compile the report.\n# Market Analysis Report\nEnglish body"
        state["sentiment_report"] = ""
        state["news_report"] = ""
        state["fundamentals_report"] = ""
        state["investment_plan"] = ""
        state["trader_investment_plan"] = ""
        state["final_trade_decision"] = ""

        result = create_report_finalizer(finalizer_llm)(state)

        self.assertEqual("清洗后的中文报告", result["final_market_report"])
        self.assertEqual(1, len(finalizer_llm.invocations))
        self.assertIn("Rewrite the following market analysis report", finalizer_llm.invocations[0])
        self.assertIn("Remove English workflow narration or meta commentary", finalizer_llm.invocations[0])

    def test_report_finalizer_does_not_silently_fall_back_when_cleanup_fails(self):
        finalizer_llm = _FailingLLM()
        state = self._base_state()
        state["market_report"] = "Now let me compile the report.\n# Market Analysis Report\nEnglish body"

        with self.assertRaises(RuntimeError) as ctx:
            create_report_finalizer(finalizer_llm)(state)

        self.assertIn("cleanup failed", str(ctx.exception))
        self.assertEqual(1, len(finalizer_llm.invocations))


if __name__ == "__main__":
    unittest.main()
