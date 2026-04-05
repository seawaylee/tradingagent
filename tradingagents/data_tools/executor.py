from threading import RLock
from typing import Any

from tradingagents.data_tools.registry import DataToolRegistry
from tradingagents.data_tools.storage import LocalArtifactStore
from tradingagents.data_tools.types import ToolExecutionResult


# AkShare/py_mini_racer 在并发工具调用下会触发 native crash；
# ToolNode 可能并行执行同一轮里的多个工具，因此这里串行化数据工具执行。
_DATA_TOOL_EXECUTION_LOCK = RLock()


class CachedDataToolExecutor:
    """提供带缓存与快照能力的数据工具执行器。"""

    def __init__(self, registry: DataToolRegistry, artifact_store: LocalArtifactStore):
        """
        初始化数据工具执行器。

        参数：
            registry: 数据工具注册表。
            artifact_store: 本地工件存储。

        返回：
            None: 无返回值。
        """
        self.registry = registry
        self.artifact_store = artifact_store

    def execute(
        self,
        tool_name: str,
        use_cache: bool = True,
        persist_snapshot: bool = False,
        snapshot_group: str = "daily",
        snapshot_date: str | None = None,
        **params: Any,
    ) -> ToolExecutionResult:
        """
        执行一个数据工具，并按需进行缓存和快照。

        参数：
            tool_name: 工具名称。
            use_cache: 是否优先读取缓存。
            persist_snapshot: 是否额外保存快照。
            snapshot_group: 快照分组名。
            snapshot_date: 快照日期，格式为 YYYY-MM-DD。
            params: 透传给工具处理函数的参数。

        返回：
            ToolExecutionResult: 执行结果对象。
        """
        with _DATA_TOOL_EXECUTION_LOCK:
            definition = self.registry.get(tool_name)
            cache_key = self.artifact_store.build_cache_key(tool_name, params)
            metadata = {
                "namespace": definition.namespace,
                "description": definition.description,
            }

            if use_cache and definition.cache_enabled:
                cached = self.artifact_store.load_cache(tool_name, params)
                if cached is not None:
                    cached_value, artifact_path = cached
                    snapshot_path = None
                    if persist_snapshot:
                        snapshot_path = str(
                            self.artifact_store.save_snapshot(
                                tool_name,
                                params,
                                cached_value,
                                snapshot_group=snapshot_group,
                                snapshot_date=snapshot_date,
                                metadata=metadata,
                            )
                        )
                    return ToolExecutionResult(
                        tool_name=tool_name,
                        params=params,
                        value=cached_value,
                        from_cache=True,
                        cache_key=cache_key,
                        artifact_path=str(artifact_path),
                        snapshot_path=snapshot_path,
                        metadata=metadata,
                    )

            value = definition.handler(**params)
            artifact_path = None
            if definition.cache_enabled:
                artifact_path = str(
                    self.artifact_store.save_cache(
                        tool_name,
                        params,
                        value,
                        metadata=metadata,
                    )
                )

            snapshot_path = None
            if persist_snapshot:
                snapshot_path = str(
                    self.artifact_store.save_snapshot(
                        tool_name,
                        params,
                        value,
                        snapshot_group=snapshot_group,
                        snapshot_date=snapshot_date,
                        metadata=metadata,
                    )
                )

            return ToolExecutionResult(
                tool_name=tool_name,
                params=params,
                value=value,
                from_cache=False,
                cache_key=cache_key,
                artifact_path=artifact_path,
                snapshot_path=snapshot_path,
                metadata=metadata,
            )
