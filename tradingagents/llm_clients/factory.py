from typing import Optional

from .base_client import BaseLLMClient
from .azure_client import AzureClient
from .openai_client import OpenAIClient
from .anthropic_client import AnthropicClient
from .google_client import GoogleClient


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """为指定提供方创建 LLM 客户端。

    参数：
        provider: LLM 提供方，如 openai、azure、anthropic、google、xai、ollama、openrouter、zhipu。
        model: 模型名称或标识。
        base_url: 可选的 API 基础地址。
        **kwargs: 提供方专属的附加参数。
            - http_client: 自定义 httpx.Client，用于 SSL 代理或证书定制。
            - http_async_client: 自定义 httpx.AsyncClient，用于异步请求。
            - timeout: 请求超时时间（秒）。
            - max_retries: 最大重试次数。
            - api_key: 提供方 API Key。
            - callbacks: LangChain 回调。

    返回：
        配置完成的 BaseLLMClient 实例。

    异常：
        ValueError: 当 provider 不受支持时抛出。
    """
    provider_lower = provider.lower()

    if provider_lower in ("openai", "ollama", "openrouter", "qwen", "zhipu"):
        return OpenAIClient(model, base_url, provider=provider_lower, **kwargs)

    if provider_lower == "azure":
        return AzureClient(model, base_url, **kwargs)

    if provider_lower == "xai":
        return OpenAIClient(model, base_url, provider="xai", **kwargs)

    if provider_lower == "anthropic":
        return AnthropicClient(model, base_url, **kwargs)

    if provider_lower == "google":
        return GoogleClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")
