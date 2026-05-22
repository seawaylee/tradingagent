import threading
import time
import unittest
from unittest.mock import patch

from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI, OpenAIClient


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _FakeAPIConnectionError(Exception):
    pass


class _FakeRateLimitError(Exception):
    def __init__(self, message: str, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class _FakeConstructedChatModel:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.model_name = kwargs.get("model", "")
        self.fallback_llm = None
        self.transient_error_max_retries = 0
        self.transient_error_retry_delay_seconds = 0
        self.__class__.created.append(self)


class _FakeFallbackLLM:
    def __init__(self, content: str):
        self.content = content
        self.calls = []
        self.model_name = "fallback-model"

    def invoke(self, input, config=None, **kwargs):
        self.calls.append((input, config, kwargs))
        return _FakeResponse(self.content)

    def bind_tools(self, tools, **kwargs):
        self.calls.append(("bind_tools", tools, kwargs))
        return self


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

    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_empty_response_without_fallback_raises_plain_error(self, mock_invoke):
        mock_invoke.return_value = _FakeResponse("")
        llm = NormalizedChatOpenAI.model_construct(
            model_name="gpt-5.4",
            transient_error_max_retries=0,
            transient_error_retry_delay_seconds=0,
            fallback_llm=None,
        )

        with self.assertRaisesRegex(RuntimeError, r"^LLM gpt-5\.4 returned empty content$"):
            NormalizedChatOpenAI.invoke(llm, "hello")

    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_falls_back_when_primary_invoke_exceeds_timeout(self, mock_invoke):
        def slow_invoke(*args, **kwargs):
            threading.Event().wait(0.2)
            return _FakeResponse("late primary")

        mock_invoke.side_effect = slow_invoke
        fallback_llm = _FakeFallbackLLM("fallback ok")
        llm = NormalizedChatOpenAI.model_construct(
            model_name="gpt-5.4",
            request_timeout=0.05,
            transient_error_max_retries=0,
            transient_error_retry_delay_seconds=0,
            fallback_llm=fallback_llm,
        )

        started = time.monotonic()
        response = NormalizedChatOpenAI.invoke(llm, "hello")
        elapsed = time.monotonic() - started

        self.assertEqual("fallback ok", response.content)
        self.assertEqual(1, len(fallback_llm.calls))
        self.assertLess(elapsed, 0.18)

    @patch("tradingagents.llm_clients.openai_client.time.sleep")
    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.invoke")
    def test_local_timeout_skips_primary_retries_and_goes_to_fallback(self, mock_invoke, mock_sleep):
        def slow_invoke(*args, **kwargs):
            threading.Event().wait(0.2)
            return _FakeResponse("late primary")

        mock_invoke.side_effect = slow_invoke
        fallback_llm = _FakeFallbackLLM("fallback ok")
        llm = NormalizedChatOpenAI.model_construct(
            model_name="gpt-5.4",
            request_timeout=0.05,
            transient_error_max_retries=3,
            transient_error_retry_delay_seconds=5,
            fallback_llm=fallback_llm,
        )

        response = NormalizedChatOpenAI.invoke(llm, "hello")

        self.assertEqual("fallback ok", response.content)
        self.assertEqual(1, mock_invoke.call_count)
        mock_sleep.assert_not_called()

    @patch("tradingagents.llm_clients.openai_client.ChatOpenAI.bind_tools")
    def test_bind_tools_rebinds_fallback_chain(self, mock_bind_tools):
        mock_bind_tools.return_value = "bound-primary"
        fallback_llm = _FakeFallbackLLM("fallback ok")
        llm = NormalizedChatOpenAI.model_construct(
            model_name="gpt-5.4",
            fallback_llm=fallback_llm,
        )

        bound = NormalizedChatOpenAI.bind_tools(llm, ["tool-a"])

        self.assertEqual(bound, "bound-primary")
        self.assertEqual(fallback_llm.calls[0][0], "bind_tools")
        self.assertEqual(fallback_llm.calls[0][1], ["tool-a"])

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI", _FakeConstructedChatModel)
    def test_fallback_keeps_provider_specific_api_key(self):
        _FakeConstructedChatModel.created = []
        client = OpenAIClient(
            model="gpt-5.4",
            base_url="https://api.awnjkankwik.asia/v1",
            provider="openai",
            api_key="primary-key",
            max_tokens=8192,
            fallback_provider="openrouter",
            fallback_model="qwen/qwen3.6-plus-preview:free",
            fallback_base_url="https://openrouter.ai/api/v1",
            fallback_api_key="openrouter-key",
            fallback_max_tokens=4096,
        )

        llm = client.get_llm()

        self.assertEqual(len(_FakeConstructedChatModel.created), 2)
        self.assertEqual(_FakeConstructedChatModel.created[0].kwargs["api_key"], "primary-key")
        self.assertEqual(_FakeConstructedChatModel.created[0].kwargs["max_tokens"], 8192)
        self.assertEqual(_FakeConstructedChatModel.created[1].kwargs["api_key"], "openrouter-key")
        self.assertEqual(_FakeConstructedChatModel.created[1].kwargs["max_tokens"], 4096)
        self.assertIs(llm.fallback_llm, _FakeConstructedChatModel.created[1])

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI", _FakeConstructedChatModel)
    def test_fallback_targets_build_nested_chain(self):
        _FakeConstructedChatModel.created = []
        client = OpenAIClient(
            model="gpt-5.4",
            base_url="https://code.xmapi.cc",
            provider="openai",
            api_key="primary-key",
            fallback_targets=[
                {
                    "provider": "openai",
                    "model": "gpt-5.4",
                    "base_url": "https://www.xmapi.cc",
                    "api_key": "xmapi-fallback-key",
                    "label": "XMAPI",
                },
                {
                    "provider": "openrouter",
                    "model": "openai/gpt-oss-120b:free",
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "openrouter-key",
                    "label": "OpenRouter",
                },
            ],
        )

        llm = client.get_llm()

        self.assertEqual(len(_FakeConstructedChatModel.created), 3)
        primary = _FakeConstructedChatModel.created[0]
        openrouter_fb = _FakeConstructedChatModel.created[1]
        xmapi_fb = _FakeConstructedChatModel.created[2]
        self.assertEqual(primary.kwargs["api_key"], "primary-key")
        self.assertEqual(xmapi_fb.kwargs["base_url"], "https://www.xmapi.cc")
        self.assertEqual(xmapi_fb.kwargs["api_key"], "xmapi-fallback-key")
        self.assertEqual(openrouter_fb.kwargs["base_url"], "https://openrouter.ai/api/v1")
        self.assertEqual(openrouter_fb.kwargs["api_key"], "openrouter-key")
        self.assertIs(llm.fallback_llm, xmapi_fb)
        self.assertIs(xmapi_fb.fallback_llm, openrouter_fb)


if __name__ == "__main__":
    unittest.main()
