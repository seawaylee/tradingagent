import os
from queue import Empty, Queue
import re
import shlex
import threading
import time
from pathlib import Path
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class _InvokeDeadlineExceeded(TimeoutError):
    """Raised when the wrapper's local deadline expires before the provider returns."""


class NormalizedChatOpenAI(ChatOpenAI):
    """对 ChatOpenAI 输出做内容规范化封装。

    Responses API 可能返回分块内容（如 reasoning、text 等），
    这里统一整理为字符串，便于后续链路稳定处理。

    支持 fallback_llm：主 provider 失败或返回空内容时自动切换备用 LLM。
    """

    transient_error_max_retries: int = 3
    transient_error_retry_delay_seconds: int = 5
    fallback_llm: Any = None  # Optional[ChatOpenAI] fallback instance

    def bind_tools(self, tools, **kwargs):
        """Bind tools to both the primary model and its fallback chain."""
        if self.fallback_llm is not None and hasattr(self.fallback_llm, "bind_tools"):
            self.fallback_llm = self.fallback_llm.bind_tools(tools, **kwargs)
        return super().bind_tools(tools, **kwargs)

    def _request_timeout_seconds(self, override: Any = None) -> Optional[float]:
        timeout = override if override is not None else getattr(self, "request_timeout", None)
        if isinstance(timeout, (int, float)):
            return float(timeout) if timeout > 0 else None
        if isinstance(timeout, tuple):
            values = [float(value) for value in timeout if isinstance(value, (int, float)) and value > 0]
            return max(values) if values else None

        values: list[float] = []
        for attr in ("read", "write", "connect", "pool"):
            value = getattr(timeout, attr, None)
            if isinstance(value, (int, float)) and value > 0:
                values.append(float(value))
        return max(values) if values else None

    def _invoke_with_timeout_guard(self, input, config=None, **kwargs):
        timeout_seconds = self._request_timeout_seconds(kwargs.get("timeout"))
        parent_invoke = super().invoke

        if timeout_seconds is None:
            return parent_invoke(input, config, **kwargs)

        result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

        def run_invoke() -> None:
            try:
                result_queue.put(("result", parent_invoke(input, config, **kwargs)))
            except BaseException as exc:
                result_queue.put(("error", exc))

        worker = threading.Thread(
            target=run_invoke,
            name="normalized-chat-openai",
            daemon=True,
        )
        worker.start()
        try:
            outcome, payload = result_queue.get(timeout=timeout_seconds)
        except Empty as exc:
            raise _InvokeDeadlineExceeded(
                f"LLM request timed out after {timeout_seconds:.3f}s while waiting for provider response"
            ) from exc
        if outcome == "error":
            raise payload
        return payload

    def _is_retryable_error(self, exc: Exception) -> bool:
        message = str(exc or "").lower()
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)

        if status_code in {429, 500, 502, 503, 524, 529}:
            return True

        markers = (
            "connection error",
            "connection reset by peer",
            "timed out",
            "timeout",
            "rate limit",
            "llm error 1302",
            "error code: 524",
            "error code: 529",
            "请控制请求频率",
            "达到速率限制",
            "requests per minute",
            "too many requests",
            "temporarily unavailable",
            "service unavailable",
        )
        return any(marker in message for marker in markers)

    def _is_empty_response(self, response: Any) -> bool:
        """Check if the response has empty/None content — a sign of provider failure.

        Tool-call responses (with tool_calls but empty content) are NOT considered empty.
        """
        if response is None:
            return True
        # Tool call responses have empty content but valid tool_calls — not empty
        if getattr(response, "tool_calls", None):
            return False
        if getattr(response, "function_call", None):
            return False
        additional_kwargs = getattr(response, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict):
            if additional_kwargs.get("function_call") or additional_kwargs.get("tool_calls"):
                return False
        content = getattr(response, "content", None)
        if content is None:
            return True
        if isinstance(content, str) and not content.strip():
            return True
        if isinstance(content, list) and not any(
            (item.get("text", "") if isinstance(item, dict) else str(item)).strip()
            for item in content
        ):
            return True
        return False

    def invoke(self, input, config=None, **kwargs):
        """
        执行模型调用，支持 transient 重试和 provider fallback。

        参数：
            input: 输入内容。
            config: 运行时配置映射。
            kwargs: 透传给底层可调用对象的关键字参数。

        返回：
            Any: 规范化后的模型响应。
        """
        max_attempts = max(1, int(getattr(self, "transient_error_max_retries", 0)) + 1)
        retry_delay = max(0, int(getattr(self, "transient_error_retry_delay_seconds", 5)))

        last_exc: Exception | None = None
        fallback_model_name = getattr(self.fallback_llm, "model_name", "fallback") if self.fallback_llm is not None else ""
        fallback_exc: Exception | None = None
        fallback_returned_empty = False
        for attempt in range(max_attempts):
            try:
                result = normalize_content(self._invoke_with_timeout_guard(input, config, **kwargs))
                if not self._is_empty_response(result):
                    return result
                # Empty response — treat as provider failure, try fallback
                print(f"[llm] {self.model_name} returned empty content, attempting fallback...")
                break
            except Exception as exc:
                last_exc = exc
                if isinstance(exc, _InvokeDeadlineExceeded):
                    break
                if attempt < max_attempts - 1 and self._is_retryable_error(exc):
                    time.sleep(retry_delay)
                    continue
                # Non-retryable or final attempt — try fallback before raising
                break

        # Fallback to secondary LLM
        if self.fallback_llm is not None:
            try:
                print(f"[llm] Falling back to {fallback_model_name}...")
                result = normalize_content(self.fallback_llm.invoke(input, config, **kwargs))
                if not self._is_empty_response(result):
                    return result
                fallback_returned_empty = True
                print(f"[llm] Fallback {fallback_model_name} also returned empty content")
            except Exception as fb_exc:
                fallback_exc = fb_exc
                print(f"[llm] Fallback failed: {fb_exc}")

        # No fallback or fallback also failed — raise original error
        if last_exc is not None:
            raise last_exc
        if self.fallback_llm is None:
            raise RuntimeError(f"LLM {self.model_name} returned empty content")
        if fallback_exc is not None:
            raise RuntimeError(
                f"LLM {self.model_name} returned empty content and fallback {fallback_model_name} failed: {fallback_exc}"
            )
        if fallback_returned_empty:
            raise RuntimeError(
                f"LLM {self.model_name} returned empty content and fallback {fallback_model_name} also returned empty content"
            )
        raise RuntimeError(
            f"LLM {self.model_name} returned empty content and fallback {fallback_model_name} did not succeed"
        )

# 将用户配置中的 kwargs 透传给 ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client", "max_tokens",
)

# 各提供方的基础地址与 API Key 环境变量
_PROVIDER_CONFIG = {
    "xai": {"base_url": "https://api.x.ai/v1", "api_key_env": "XAI_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
    "ollama": {"base_url": "http://localhost:11434/v1", "api_key_env": None},
    "qwen": {"base_url": "https://coding.dashscope.aliyuncs.com/v1", "api_key_env": "QWEN_API_KEY"},
}


class OpenAIClient(BaseLLMClient):
    """面向 OpenAI、Ollama、OpenRouter 与 xAI 的客户端封装。

    原生 OpenAI 模型默认使用 `/v1/responses`，以支持统一的
    `reasoning_effort` 与工具调用行为；兼容提供方继续使用
    标准 Chat Completions 接口。
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        """
        初始化对象。
        
        参数：
            model: 模型标识。
            base_url: 基础接口地址。
            provider: 模型提供方名称。
            kwargs: 透传给底层可调用对象的关键字参数。
        
        返回：
            None: 无返回值。
        """
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """
        返回配置好的 ChatOpenAI 实例。
        
        返回：
            Any: 配置完成的 ChatOpenAI 实例。
        """
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        # 提供方专属的基础地址与鉴权参数
        if self.provider in _PROVIDER_CONFIG:
            provider_config = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = self.base_url or provider_config["base_url"]
            api_key_env = provider_config["api_key_env"]
            api_key = os.environ.get(api_key_env) if api_key_env else None
            if api_key:
                llm_kwargs["api_key"] = api_key
            elif self.provider == "ollama":
                llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # 继续透传用户提供的 kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # 原生 OpenAI：使用 Responses API，以在不同模型家族间保持一致行为
        # 第三方兼容提供方则继续使用 Chat Completions。
        # 如果 base_url 被覆盖为非 OpenAI 官方地址，也走 Chat Completions。
        if self.provider == "openai" and not self.base_url:
            llm_kwargs["use_responses_api"] = True

        llm = NormalizedChatOpenAI(**llm_kwargs)
        llm.transient_error_max_retries = int(self.kwargs.get("transient_error_max_retries", 3))
        llm.transient_error_retry_delay_seconds = int(self.kwargs.get("transient_error_retry_delay_seconds", 5))

        fallback_targets = self._fallback_targets()
        fallback_chain = self._build_fallback_chain(fallback_targets)
        if fallback_chain is not None:
            llm.fallback_llm = fallback_chain

        return llm

    def _fallback_targets(self) -> list[dict[str, Any]]:
        configured = self.kwargs.get("fallback_targets")
        targets: list[dict[str, Any]] = []
        if isinstance(configured, list):
            for item in configured:
                if isinstance(item, dict):
                    targets.append(dict(item))
        fallback_provider = self.kwargs.get("fallback_provider")
        fallback_model = self.kwargs.get("fallback_model")
        if fallback_provider and fallback_model:
            single_target = {
                "provider": fallback_provider,
                "model": fallback_model,
            }
            if self.kwargs.get("fallback_base_url"):
                single_target["base_url"] = self.kwargs.get("fallback_base_url")
            if self.kwargs.get("fallback_api_key"):
                single_target["api_key"] = self.kwargs.get("fallback_api_key")
            if self.kwargs.get("fallback_max_tokens") is not None:
                single_target["max_tokens"] = self.kwargs.get("fallback_max_tokens")
            targets.append(single_target)
        return targets

    def _build_single_fallback_llm(self, target: dict[str, Any]) -> Any:
        fallback_provider = str(target.get("provider") or "openai").strip().lower()
        fallback_model = str(target.get("model") or "").strip()
        if not fallback_model:
            raise ValueError("fallback target missing model")

        fb_kwargs: dict[str, Any] = {"model": fallback_model}
        fb_config = _PROVIDER_CONFIG.get(fallback_provider)
        if fb_config:
            fb_kwargs["base_url"] = target.get("base_url") or fb_config["base_url"]
            fb_api_key_env = fb_config.get("api_key_env")
            fb_api_key = target.get("api_key")
            if not fb_api_key and fb_api_key_env:
                fb_api_key = os.environ.get(fb_api_key_env)
            if fb_api_key:
                fb_kwargs["api_key"] = fb_api_key
            elif fallback_provider == "ollama":
                fb_kwargs["api_key"] = "ollama"
        elif target.get("base_url"):
            fb_kwargs["base_url"] = target["base_url"]

        explicit_fb_api_key = target.get("api_key")
        if explicit_fb_api_key and "api_key" not in fb_kwargs:
            fb_kwargs["api_key"] = explicit_fb_api_key
        if target.get("max_tokens") is not None:
            fb_kwargs["max_tokens"] = target["max_tokens"]

        for key in _PASSTHROUGH_KWARGS:
            if key not in self.kwargs:
                continue
            if key == "api_key":
                if fb_kwargs.get(key) is not None:
                    continue
                if fallback_provider and fallback_provider != self.provider:
                    continue
            if key == "max_tokens" and fb_kwargs.get(key) is not None:
                continue
            fb_kwargs[key] = self.kwargs[key]

        fb_llm = NormalizedChatOpenAI(**fb_kwargs)
        fb_llm.transient_error_max_retries = int(self.kwargs.get("transient_error_max_retries", 3))
        fb_llm.transient_error_retry_delay_seconds = int(self.kwargs.get("transient_error_retry_delay_seconds", 5))
        return fb_llm

    def _build_fallback_chain(self, targets: list[dict[str, Any]]) -> Any:
        if not targets:
            return None

        built_chain = None
        configured_labels: list[str] = []
        for target in reversed(targets):
            fb_llm = self._build_single_fallback_llm(target)
            fb_llm.fallback_llm = built_chain
            built_chain = fb_llm
            configured_labels.append(
                str(target.get("label") or target.get("provider") or target.get("base_url") or target.get("model") or "fallback")
            )
        print(f"[llm] Fallback configured: {' -> '.join(reversed(configured_labels))}")
        return built_chain

    def validate_model(self) -> bool:
        """
        校验模型是否适用于当前提供方。
        
        返回：
            bool: 条件满足时返回 True，否则返回 False。
        """
        return validate_model(self.provider, self.model)
