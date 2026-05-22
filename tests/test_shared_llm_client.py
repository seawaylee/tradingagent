import unittest
from unittest.mock import patch

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.shared_client import SharedLLMClient


class _FakeSharedModule:
    DEFAULT_MODEL = "gpt-5.4"
    DEFAULT_BASE_URL = "https://api.awnjkankwik.asia/v1"
    DEFAULT_API_KEY = "xmapi-key"
    DEFAULT_REASONING_EFFORT = "xhigh"
    OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY = "openrouter-key"
    OPENROUTER_MODEL = "openai/gpt-oss-120b:free"
    last_call = None

    @staticmethod
    def chat_completion_or_raise(prompt, **kwargs):
        _FakeSharedModule.last_call = {"prompt": prompt, "kwargs": kwargs}
        return f"shared::{prompt}::{kwargs.get('system_prompt', '')}"

    @staticmethod
    def list_openai_compatible_targets(*, base_url=None, api_key=None):
        primary_base_url = base_url or _FakeSharedModule.DEFAULT_BASE_URL
        primary_api_key = api_key or _FakeSharedModule.DEFAULT_API_KEY
        return [
            {"label": "XMAPI", "base_url": primary_base_url, "api_key": primary_api_key},
            {"label": "XMAPI", "base_url": "https://www.xmapi.cc", "api_key": primary_api_key},
        ]

    @staticmethod
    def build_tool_calling_fallback_targets(*, base_url=None, api_key=None, model=None):
        targets = []
        if model:
            targets.append(
                {
                    "provider": "openai",
                    "model": model,
                    "base_url": "https://www.xmapi.cc",
                    "api_key": api_key or _FakeSharedModule.DEFAULT_API_KEY,
                    "label": "XMAPI",
                }
            )
        if _FakeSharedModule.OPENROUTER_API_KEY:
            targets.append(
                {
                    "provider": "openrouter",
                    "model": _FakeSharedModule.OPENROUTER_MODEL,
                    "base_url": _FakeSharedModule.OPENROUTER_BASE_URL,
                    "api_key": _FakeSharedModule.OPENROUTER_API_KEY,
                    "label": "OpenRouter",
                }
            )
        return targets


class _FakeToolBinding:
    def __init__(self, tools):
        self.tools = tools


class _FakeToolLLM:
    def __init__(self):
        self.bound_tools = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return _FakeToolBinding(tools)


class _FakeOpenAIClient:
    created = []

    def __init__(self, model, base_url=None, provider="openai", **kwargs):
        self.model = model
        self.base_url = base_url
        self.provider = provider
        self.kwargs = kwargs
        self.__class__.created.append(self)

    def get_llm(self):
        return _FakeToolLLM()


class SharedLLMClientTests(unittest.TestCase):
    @patch("tradingagents.llm_clients.shared_client._load_shared_llm_client_module", return_value=_FakeSharedModule())
    @patch("tradingagents.llm_clients.shared_client.SharedLLMClient._build_tool_calling_llm", return_value=_FakeToolLLM())
    def test_shared_client_routes_plain_invoke_and_tool_binding(self, mock_tool_llm, _mock_shared_module):
        client = create_llm_client(provider="shared", model="", base_url=None)

        self.assertIsInstance(client, SharedLLMClient)

        llm = client.get_llm()
        response = llm.invoke("plain prompt")
        binding = llm.bind_tools(["tool-a"])

        self.assertEqual(response.content, "shared::plain prompt::")
        self.assertEqual(_FakeSharedModule.last_call["kwargs"]["reasoning_effort"], "xhigh")
        self.assertEqual(binding.tools, ["tool-a"])
        mock_tool_llm.assert_called_once()

    @patch("tradingagents.llm_clients.shared_client._load_shared_llm_client_module", return_value=_FakeSharedModule())
    @patch("tradingagents.llm_clients.shared_client.OpenAIClient", _FakeOpenAIClient)
    def test_shared_tool_llm_prefers_explicit_reasoning_effort_override(self, _mock_shared_module):
        _FakeOpenAIClient.created = []
        client = SharedLLMClient(model="", base_url=None, reasoning_effort="medium", timeout=45)

        tool_llm = client._build_tool_calling_llm()

        self.assertIsInstance(tool_llm, _FakeToolLLM)
        self.assertEqual(1, len(_FakeOpenAIClient.created))
        created = _FakeOpenAIClient.created[0]
        self.assertEqual(created.kwargs["reasoning_effort"], "medium")
        self.assertEqual(created.kwargs["timeout"], 45)
        self.assertEqual(created.base_url, "https://api.awnjkankwik.asia/v1")
        self.assertEqual(created.kwargs["fallback_targets"][0]["base_url"], "https://www.xmapi.cc")
        self.assertEqual(created.kwargs["fallback_targets"][0]["model"], "gpt-5.4")
        self.assertEqual(created.kwargs["fallback_targets"][1]["provider"], "openrouter")
        self.assertEqual(created.kwargs["fallback_targets"][1]["api_key"], "openrouter-key")

    @patch("tradingagents.llm_clients.shared_client._load_shared_llm_client_module", return_value=_FakeSharedModule())
    @patch("tradingagents.llm_clients.shared_client.OpenAIClient", _FakeOpenAIClient)
    def test_shared_tool_llm_skips_openrouter_fallback_when_api_key_missing(self, _mock_shared_module):
        _FakeOpenAIClient.created = []
        original_key = _FakeSharedModule.OPENROUTER_API_KEY
        _FakeSharedModule.OPENROUTER_API_KEY = ""
        try:
            client = SharedLLMClient(model="", base_url=None, timeout=45)
            client._build_tool_calling_llm()
        finally:
            _FakeSharedModule.OPENROUTER_API_KEY = original_key

        created = _FakeOpenAIClient.created[0]
        self.assertEqual(len(created.kwargs["fallback_targets"]), 1)
        self.assertEqual(created.kwargs["fallback_targets"][0]["base_url"], "https://www.xmapi.cc")


if __name__ == "__main__":
    unittest.main()
