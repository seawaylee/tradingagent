import os
import re
import shlex
import time
from pathlib import Path
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatOpenAI(ChatOpenAI):
    """对 ChatOpenAI 输出做内容规范化封装。

    Responses API 可能返回分块内容（如 reasoning、text 等），
    这里统一整理为字符串，便于后续链路稳定处理。

    支持 fallback_llm：主 provider 失败或返回空内容时自动切换备用 LLM。
    """

    transient_error_max_retries: int = 3
    transient_error_retry_delay_seconds: int = 5
    fallback_llm: Any = None  # Optional[ChatOpenAI] fallback instance

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
        for attempt in range(max_attempts):
            try:
                result = normalize_content(super().invoke(input, config, **kwargs))
                if not self._is_empty_response(result):
                    return result
                # Empty response — treat as provider failure, try fallback
                print(f"[llm] {self.model_name} returned empty content, attempting fallback...")
                break
            except Exception as exc:
                last_exc = exc
                if attempt < max_attempts - 1 and self._is_retryable_error(exc):
                    time.sleep(retry_delay)
                    continue
                # Non-retryable or final attempt — try fallback before raising
                break

        # Fallback to secondary LLM
        if self.fallback_llm is not None:
            try:
                fb_model = getattr(self.fallback_llm, "model_name", "unknown")
                print(f"[llm] Falling back to {fb_model}...")
                result = normalize_content(self.fallback_llm.invoke(input, config, **kwargs))
                if not self._is_empty_response(result):
                    return result
                print(f"[llm] Fallback {fb_model} also returned empty content")
            except Exception as fb_exc:
                print(f"[llm] Fallback failed: {fb_exc}")

        # No fallback or fallback also failed — raise original error
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"Primary LLM {self.model_name} returned empty content and no fallback succeeded")

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
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/coding/paas/v4", "api_key_env": "ZAI_API_KEY"},
}


def _alias_env_var(alias_name: str, var_name: str) -> Optional[str]:
    zshrc = Path.home() / ".zshrc"
    if not zshrc.exists():
        return None
    text = zshrc.read_text(encoding="utf-8")
    match = re.search(rf"alias\s+{re.escape(alias_name)}='([^']+)'", text)
    if not match:
        return None
    parts = shlex.split(match.group(1))
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "env":
            index += 1
            continue
        if part == "-u":
            index += 2
            continue
        if "=" not in part:
            break
        key, value = part.split("=", 1)
        if key == var_name:
            return value
        index += 1
    return None


def _resolve_zhipu_api_key() -> Optional[str]:
    direct_value = os.environ.get("ZAI_API_KEY")
    if direct_value:
        return direct_value
    for alias_name in ("cc-glm", "cc"):
        for var_name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
            value = _alias_env_var(alias_name, var_name)
            if value:
                return value
    return None


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
            if self.provider == "zhipu":
                api_key = _resolve_zhipu_api_key()
            else:
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

        # Build fallback LLM if fallback config is provided
        fallback_provider = self.kwargs.get("fallback_provider")
        fallback_model = self.kwargs.get("fallback_model")
        if fallback_provider and fallback_model:
            fb_kwargs = {"model": fallback_model}
            fb_config = _PROVIDER_CONFIG.get(fallback_provider)
            if fb_config:
                fb_kwargs["base_url"] = self.kwargs.get("fallback_base_url") or fb_config["base_url"]
                if fallback_provider == "zhipu":
                    fb_api_key = _resolve_zhipu_api_key()
                else:
                    fb_api_key_env = fb_config.get("api_key_env")
                    fb_api_key = os.environ.get(fb_api_key_env) if fb_api_key_env else None
                if fb_api_key:
                    fb_kwargs["api_key"] = fb_api_key
            elif self.kwargs.get("fallback_base_url"):
                fb_kwargs["base_url"] = self.kwargs["fallback_base_url"]
            if self.kwargs.get("fallback_max_tokens") is not None:
                fb_kwargs["max_tokens"] = self.kwargs["fallback_max_tokens"]
            # Copy passthrough kwargs to fallback (except fallback-specific ones)
            for key in _PASSTHROUGH_KWARGS:
                if key in self.kwargs:
                    if key in {"api_key", "max_tokens"} and fb_kwargs.get(key) is not None:
                        continue
                    fb_kwargs[key] = self.kwargs[key]
            fb_llm = NormalizedChatOpenAI(**fb_kwargs)
            fb_llm.transient_error_max_retries = int(self.kwargs.get("transient_error_max_retries", 3))
            fb_llm.transient_error_retry_delay_seconds = int(self.kwargs.get("transient_error_retry_delay_seconds", 5))
            llm.fallback_llm = fb_llm
            print(f"[llm] Fallback configured: {fallback_provider}/{fallback_model}")

        return llm

    def validate_model(self) -> bool:
        """
        校验模型是否适用于当前提供方。
        
        返回：
            bool: 条件满足时返回 True，否则返回 False。
        """
        return validate_model(self.provider, self.model)
