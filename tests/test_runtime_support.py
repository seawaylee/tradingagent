import tempfile
import unittest
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from tradingagents.runtime_support import FileCheckpointSaver, build_partial_final_state


class _CounterState(TypedDict):
    x: int


class RuntimeSupportTests(unittest.TestCase):
    def test_file_checkpoint_saver_recovers_from_corrupted_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_file = Path(temp_dir) / "checkpoint.pkl"
            checkpoint_file.write_bytes(b"not-a-valid-pickle")

            saver = FileCheckpointSaver(checkpoint_file)

            self.assertEqual(0, len(saver.storage))
            self.assertFalse(checkpoint_file.exists())
            backups = list(checkpoint_file.parent.glob("checkpoint.pkl.corrupt*"))
            self.assertEqual(1, len(backups))

    def test_file_checkpoint_saver_persists_and_resumes_incomplete_run(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            checkpoint_file = Path(temp_dir) / "checkpoint.pkl"

            builder = StateGraph(_CounterState)
            builder.add_node("first", lambda state: {"x": state["x"] + 1})
            builder.add_node("second", lambda state: {"x": state["x"] + 10})
            builder.add_edge(START, "first")
            builder.add_edge("first", "second")
            builder.add_edge("second", END)

            config = {"configurable": {"thread_id": "quick:01810.HK:2026-04-06"}}

            first_graph = builder.compile(
                checkpointer=FileCheckpointSaver(checkpoint_file),
                interrupt_after=["first"],
            )
            first_chunks = list(first_graph.stream({"x": 1}, config))

            self.assertTrue(checkpoint_file.exists())
            self.assertEqual({"first": {"x": 2}}, first_chunks[0])
            self.assertIn("__interrupt__", first_chunks[1])

            resumed_graph = builder.compile(
                checkpointer=FileCheckpointSaver(checkpoint_file),
                interrupt_after=["first"],
            )
            resumed_state = resumed_graph.get_state(config)
            self.assertEqual(("second",), resumed_state.next)
            self.assertEqual({"x": 2}, resumed_state.values)

            resumed_chunks = list(resumed_graph.stream(None, config))
            self.assertEqual([{"second": {"x": 12}}], resumed_chunks)

    def test_build_partial_final_state_promotes_completed_stage_outputs(self):
        partial_state = build_partial_final_state(
            {
                "market_report": "market body",
                "final_market_report": "",
                "sentiment_report": "sentiment body",
                "news_report": "",
                "fundamentals_report": "fundamentals body",
                "investment_plan": "research plan",
                "trader_investment_plan": "trader plan",
                "final_trade_decision": "portfolio decision",
            }
        )

        self.assertEqual("market body", partial_state["final_market_report"])
        self.assertEqual("sentiment body", partial_state["final_sentiment_report"])
        self.assertEqual("fundamentals body", partial_state["final_fundamentals_report"])
        self.assertEqual("research plan", partial_state["final_investment_plan_report"])
        self.assertEqual("trader plan", partial_state["final_trader_investment_plan_report"])
        self.assertEqual("portfolio decision", partial_state["final_trade_decision_report"])


if __name__ == "__main__":
    unittest.main()
