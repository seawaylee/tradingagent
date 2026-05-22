import importlib.util
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from langchain_core.messages import AIMessage

from .base_client import BaseLLMClient
from .openai_client import OpenAIClient


def _candidate_repo_paths() -> list[Path]:
    candidates: list[Path] = []
    explicit = str(os.getenv("CORE_COMMON_TOOLS_REPO") or "").strip()
    if explicit:
        candidates.append(Path(explicit).expanduser())
    repo_root = Path(__file__).resolve().parents[2]
    candidates.append(repo_root.parent / "core-common-tools")
    return candidates


def _load_shared_llm_client_module():
    last_error: Exception | None = None
    for repo_path in _candidate_repo_paths():
        module_path = repo_path / "core_common_tools" / "llm_client.py"
        if not module_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("tradingagents_shared_llm_client", module_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            last_error = exc
    hint = ", ".join(str(path) for path in _candidate_repo_paths())
    raise ModuleNotFoundError(
        f"Unable to import shared core_common_tools.llm_client; checked: {hint}"
    ) from last_error


def _stringify_message_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", "")
                if text:
                    parts.append(str(text))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _normalize_message(item: Any) -> tuple[str, str]:
    if isinstance(item, tuple) and len(item) >= 2:
        return str(item[0] or ""), _stringify_message_content(item[1])
    if isinstance(item, dict):
        return str(item.get("role") or item.get("type") or ""), _stringify_message_content(item.get("content"))
    role = getattr(item, "type", "") or getattr(item, "role", "")
    content = _stringify_message_content(getattr(item, "content", item))
    return str(role or ""), content


def _coerce_prompt_input(input_value: Any) -> tuple[Optional[str], str]:
    if isinstance(input_value, str):
        return None, input_value

    if isinstance(input_value, Iterable):
        system_parts: list[str] = []
        dialogue_parts: list[str] = []
        for item in input_value:
            role, content = _normalize_message(item)
            normalized_role = role.strip().lower()
            if not content:
                continue
            if normalized_role in {"system", "developer"}:
                system_parts.append(content)
                continue
            label = {
                "human": "USER",
                "user": "USER",
                "ai": "ASSISTANT",
                "assistant": "ASSISTANT",
            }.get(normalized_role, normalized_role.upper() or "MESSAGE")
            dialogue_parts.append(f"[{label}]\n{content}")
        system_prompt = "\n\n".join(part for part in system_parts if part).strip() or None
        prompt = "\n\n".join(part for part in dialogue_parts if part).strip()
        if prompt:
            return system_prompt, prompt
        if system_prompt:
            return None, system_prompt

    return None, _stringify_message_content(input_value)


class _SharedChatModel:
    def __init__(
        self,
        *,
        shared_module: Any,
        tool_llm: Any,
        model_name: str,
        timeout: int = 120,
        reasoning_effort: Optional[str] = None,
    ):
        self._shared_module = shared_module
        self._tool_llm = tool_llm
        self.model_name = model_name
        self.timeout = timeout
        self.reasoning_effort = str(reasoning_effort or "").strip() or None

    def invoke(self, input, config=None, **kwargs):
        system_prompt, prompt = _coerce_prompt_input(input)
        request_kwargs: dict[str, Any] = {
            "temperature": kwargs.get("temperature", 0.7),
            "timeout": int(kwargs.get("timeout", self.timeout)),
        }
        if system_prompt:
            request_kwargs["system_prompt"] = system_prompt
        if self.reasoning_effort:
            request_kwargs["reasoning_effort"] = self.reasoning_effort
        content = self._shared_module.chat_completion_or_raise(prompt, **request_kwargs)
        return AIMessage(content=str(content or "").strip())

    def bind_tools(self, tools):
        return self._tool_llm.bind_tools(tools)


class SharedLLMClient(BaseLLMClient):
    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, base_url, **kwargs)
        self._shared_module = _load_shared_llm_client_module()

    def _shared_reasoning_effort(self) -> Optional[str]:
        configured = str(self.kwargs.get("reasoning_effort") or "").strip()
        if configured:
            return configured
        shared_default = str(getattr(self._shared_module, "DEFAULT_REASONING_EFFORT", "") or "").strip()
        return shared_default or None

    def _shared_openai_compatible_targets(self) -> list[dict[str, str]]:
        target_builder = getattr(self._shared_module, "list_openai_compatible_targets", None)
        if callable(target_builder):
            try:
                targets = target_builder(base_url=self.base_url, api_key=self.kwargs.get("api_key"))
            except TypeError:
                targets = target_builder()
            if isinstance(targets, list):
                normalized = [item for item in targets if isinstance(item, dict) and str(item.get("base_url") or "").strip()]
                if normalized:
                    return normalized

        default_base_url = str(
            self.base_url or getattr(self._shared_module, "DEFAULT_BASE_URL", "") or ""
        ).strip()
        default_api_key = str(
            self.kwargs.get("api_key") or getattr(self._shared_module, "DEFAULT_API_KEY", "") or ""
        ).strip()
        if not default_base_url:
            return []
        return [{"label": "XMAPI", "base_url": default_base_url, "api_key": default_api_key}]

    def _shared_tool_fallback_targets(self, *, model_name: str) -> list[dict[str, str]]:
        fallback_builder = getattr(self._shared_module, "build_tool_calling_fallback_targets", None)
        if callable(fallback_builder):
            try:
                targets = fallback_builder(
                    base_url=self.base_url,
                    api_key=self.kwargs.get("api_key"),
                    model=model_name,
                )
            except TypeError:
                targets = fallback_builder()
            if isinstance(targets, list):
                normalized = [item for item in targets if isinstance(item, dict) and str(item.get("model") or "").strip()]
                if normalized:
                    return normalized

        fallback_model = str(
            getattr(self._shared_module, "OPENROUTER_MODEL", "")
            or getattr(self._shared_module, "OPENROUTER_FALLBACK_MODEL", "")
            or ""
        ).strip()
        fallback_api_key = str(getattr(self._shared_module, "OPENROUTER_API_KEY", "") or "").strip()
        if not fallback_model or not fallback_api_key:
            return []
        fallback_target = {
            "provider": "openrouter",
            "model": fallback_model,
            "api_key": fallback_api_key,
            "label": "OpenRouter",
        }
        fallback_base_url = str(getattr(self._shared_module, "OPENROUTER_BASE_URL", "") or "").strip()
        if fallback_base_url:
            fallback_target["base_url"] = fallback_base_url
        return [fallback_target]

    def _build_tool_calling_llm(self):
        default_model = str(self.model or getattr(self._shared_module, "DEFAULT_MODEL", "") or "").strip()
        targets = self._shared_openai_compatible_targets()
        primary_target = targets[0] if targets else {}
        default_base_url = str(primary_target.get("base_url") or "").strip()
        default_api_key = str(primary_target.get("api_key") or "").strip()
        default_reasoning_effort = self._shared_reasoning_effort()

        tool_client_kwargs = dict(self.kwargs)
        if default_api_key:
            tool_client_kwargs["api_key"] = default_api_key
        if default_reasoning_effort:
            tool_client_kwargs["reasoning_effort"] = default_reasoning_effort
        fallback_targets = self._shared_tool_fallback_targets(model_name=default_model)
        if fallback_targets:
            tool_client_kwargs["fallback_targets"] = fallback_targets

        return OpenAIClient(
            model=default_model,
            base_url=default_base_url,
            provider="openai",
            **tool_client_kwargs,
        ).get_llm()

    def get_llm(self) -> Any:
        model_name = str(self.model or getattr(self._shared_module, "DEFAULT_MODEL", "") or "").strip()
        timeout = int(self.kwargs.get("timeout", 120))
        return _SharedChatModel(
            shared_module=self._shared_module,
            tool_llm=self._build_tool_calling_llm(),
            model_name=model_name,
            timeout=timeout,
            reasoning_effort=self._shared_reasoning_effort(),
        )

    def validate_model(self) -> bool:
        return True
