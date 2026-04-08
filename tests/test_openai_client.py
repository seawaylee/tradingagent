import unittest
from unittest.mock import patch

from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeAPIConnectionError(Exception):
    pass


class _FakeRateLimitError(Exception):
    def __init__(self, message: str, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class TestOpenAIClientRetry(unittest.TestCase):
    @patch("tradingagents.llm_clients.openai_client.time.sleep")
    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_retries_transient_connection_errors(self, mock_invoke, mock_sleep):
        mock_invoke.side_effect = [
            _FakeAPIConnectionError("Connection error."),
            _FakeAPIConnectionError("Connection error."),
            _FakeResponse("ok"),
        ]
        llm = NormalizedChatOpenAI.model_construct(
            transient_error_max_retries=3,
            transient_error_retry_delay_seconds=5,
        )

        response = NormalizedChatOpenAI.invoke(llm, "hello")

        self.assertEqual("ok", response.content)
        self.assertEqual(3, mock_invoke.call_count)
        self.assertEqual(2, mock_sleep.call_count)
        mock_sleep.assert_any_call(5)

    @patch("tradingagents.llm_clients.openai_client.time.sleep")
    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_retries_rate_limit_errors(self, mock_invoke, mock_sleep):
        mock_invoke.side_effect = [
            _FakeRateLimitError("LLM error 1302: 您的账户已达到速率限制，请您控制请求频率", status_code=429),
            _FakeResponse("ok"),
        ]
        llm = NormalizedChatOpenAI.model_construct(
            transient_error_max_retries=3,
            transient_error_retry_delay_seconds=5,
        )

        response = NormalizedChatOpenAI.invoke(llm, "hello")

        self.assertEqual("ok", response.content)
        self.assertEqual(2, mock_invoke.call_count)
        mock_sleep.assert_called_once_with(5)

    @patch("tradingagents.llm_clients.openai_client.time.sleep")
    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_non_retryable_errors_still_raise(self, mock_invoke, mock_sleep):
        mock_invoke.side_effect = ValueError("bad prompt")
        llm = NormalizedChatOpenAI.model_construct(
            transient_error_max_retries=3,
            transient_error_retry_delay_seconds=5,
        )

        with self.assertRaises(ValueError):
            NormalizedChatOpenAI.invoke(llm, "hello")

        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
