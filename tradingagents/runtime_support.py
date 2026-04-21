import datetime
import json
import os
import pickle
import re
import threading
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver


_THREAD_SAFE_PART_RE = re.compile(r"[^A-Za-z0-9._:-]+")
_REPORT_PROMOTION_SPECS = (
    ("market_report", "final_market_report"),
    ("sentiment_report", "final_sentiment_report"),
    ("news_report", "final_news_report"),
    ("fundamentals_report", "final_fundamentals_report"),
    ("investment_plan", "final_investment_plan_report"),
    ("trader_investment_plan", "final_trader_investment_plan_report"),
    ("final_trade_decision", "final_trade_decision_report"),
)


def build_run_thread_id(ticker: str, trade_date: str, run_mode: str = "analysis") -> str:
    """
    基于标的、日期与运行模式构建稳定的续跑线程 ID。

    参数：
        ticker: 股票代码。
        trade_date: 交易日期。
        run_mode: 运行模式，例如 quick/full。

    返回：
        str: 稳定且可复用的线程 ID。
    """
    safe_parts = [
        _THREAD_SAFE_PART_RE.sub("_", str(run_mode or "analysis")),
        _THREAD_SAFE_PART_RE.sub("_", str(ticker)),
        _THREAD_SAFE_PART_RE.sub("_", str(trade_date)),
    ]
    return ":".join(safe_parts)


def build_partial_final_state(state_values: dict[str, Any] | None) -> dict[str, Any]:
    """
    将当前图状态提升为可持久化的最终报告视图。

    参数：
        state_values: 图状态中的 channel values。

    返回：
        dict[str, Any]: 补齐 final_* 字段后的状态副本。
    """
    normalized = dict(state_values or {})
    for source_key, target_key in _REPORT_PROMOTION_SPECS:
        if normalized.get(target_key):
            continue
        if normalized.get(source_key):
            normalized[target_key] = normalized[source_key]
    return normalized


def snapshot_to_dict(snapshot, *, include_promoted_state: bool = True) -> dict[str, Any] | None:
    """
    将 LangGraph 的状态快照转换为可 JSON 序列化的结构。

    参数：
        snapshot: Compiled graph state snapshot.
        include_promoted_state: 是否补齐 final_* 字段。

    返回：
        dict[str, Any] | None: 可序列化快照；若快照为空则返回 None。
    """
    if snapshot is None:
        return None

    values = dict(getattr(snapshot, "values", {}) or {})
    if include_promoted_state:
        values = build_partial_final_state(values)

    return {
        "values": values,
        "next": list(getattr(snapshot, "next", ()) or ()),
        "config": getattr(snapshot, "config", None),
        "metadata": getattr(snapshot, "metadata", None),
        "created_at": getattr(snapshot, "created_at", None),
        "parent_config": getattr(snapshot, "parent_config", None),
        "tasks": [
            {
                "id": getattr(task, "id", None),
                "name": getattr(task, "name", None),
                "path": list(getattr(task, "path", ()) or ()),
                "error": getattr(task, "error", None),
                "interrupts": [str(item) for item in getattr(task, "interrupts", ()) or ()],
            }
            for task in getattr(snapshot, "tasks", ()) or ()
        ],
    }


def persist_snapshot(snapshot_path: str | Path, snapshot, *, reason: str | None = None) -> dict[str, Any] | None:
    """
    将状态快照写入磁盘，便于中断后查看与续跑。

    参数：
        snapshot_path: 输出 JSON 路径。
        snapshot: LangGraph 状态快照。
        reason: 可选原因描述。

    返回：
        dict[str, Any] | None: 已写入的快照内容。
    """
    payload = snapshot_to_dict(snapshot)
    if payload is None:
        return None

    if reason:
        payload["reason"] = reason
    payload["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    snapshot_file = Path(snapshot_path)
    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
    snapshot_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return payload


def append_error_log(log_path: str | Path, exc: BaseException, *, context: dict[str, Any] | None = None) -> None:
    """
    将详细异常信息追加写入错误日志。

    参数：
        log_path: 错误日志路径。
        exc: 当前异常对象。
        context: 额外上下文。

    返回：
        None: 无返回值。
    """
    error_file = Path(log_path)
    error_file.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"[{timestamp}] {type(exc).__name__}: {exc}",
    ]
    if context:
        lines.append(json.dumps(context, ensure_ascii=False, default=str))
    lines.append(traceback.format_exc().rstrip())
    lines.append("")
    with error_file.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


class FileCheckpointSaver(InMemorySaver):
    """
    将 LangGraph checkpoint 持久化到本地文件，支持跨进程续跑。
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._io_lock = threading.RLock()
        super().__init__()
        self._restore()

    def _corrupt_backup_path(self) -> Path:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = self.path.with_name(f"{self.path.name}.corrupt-{timestamp}")
        counter = 1
        while candidate.exists():
            candidate = self.path.with_name(f"{self.path.name}.corrupt-{timestamp}-{counter}")
            counter += 1
        return candidate

    def _quarantine_corrupted_file(self) -> None:
        if not self.path.exists():
            return
        backup_path = self._corrupt_backup_path()
        self.path.replace(backup_path)

    def _restore(self) -> None:
        if not self.path.exists():
            return
        with self._io_lock:
            try:
                with self.path.open("rb") as handle:
                    payload = pickle.load(handle)
                if not isinstance(payload, dict):
                    raise ValueError("Checkpoint payload must be a dict.")
            except (EOFError, pickle.PickleError, ValueError, TypeError, AttributeError):
                self._quarantine_corrupted_file()
                return
        storage_payload = payload.get("storage", {})
        restored_storage = defaultdict(lambda: defaultdict(dict))
        for thread_id, namespaces in storage_payload.items():
            restored_storage[thread_id] = defaultdict(
                dict,
                {checkpoint_ns: dict(checkpoints) for checkpoint_ns, checkpoints in namespaces.items()},
            )
        self.storage = restored_storage
        self.writes = defaultdict(
            dict,
            {
                tuple(key): dict(value)
                for key, value in payload.get("writes", {}).items()
            },
        )
        self.blobs = dict(payload.get("blobs", {}))

    def _to_plain_dict(self, value):
        if isinstance(value, dict):
            return {key: self._to_plain_dict(item) for key, item in value.items()}
        return value

    def _flush(self) -> None:
        with self._io_lock:
            payload = {
                "storage": self._to_plain_dict(self.storage),
                "writes": self._to_plain_dict(self.writes),
                "blobs": self._to_plain_dict(self.blobs),
            }
            temp_path = self.path.with_name(
                f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
            )
            try:
                with temp_path.open("wb") as handle:
                    pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
                    handle.flush()
                    os.fsync(handle.fileno())
                temp_path.replace(self.path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()

    def put(self, config, checkpoint, metadata, new_versions):
        with self._io_lock:
            result = super().put(config, checkpoint, metadata, new_versions)
            self._flush()
            return result

    def put_writes(self, config, writes, task_id, task_path=""):
        with self._io_lock:
            super().put_writes(config, writes, task_id, task_path)
            self._flush()

    def delete_thread(self, thread_id: str) -> None:
        with self._io_lock:
            super().delete_thread(thread_id)
            self._flush()

    def delete_for_runs(self, run_ids):
        if not run_ids:
            return
        with self._io_lock:
            run_id_set = set(run_ids)
            changed = False
            for outer_key in list(self.writes.keys()):
                writes = self.writes.get(outer_key, {})
                for inner_key, value in list(writes.items()):
                    task_id = value[0]
                    if task_id in run_id_set:
                        del writes[inner_key]
                        changed = True
                if not writes:
                    del self.writes[outer_key]
            if changed:
                self._flush()

    def copy_thread(self, source_thread_id: str, target_thread_id: str) -> None:
        with self._io_lock:
            if source_thread_id not in self.storage:
                return
            self.storage[target_thread_id] = pickle.loads(pickle.dumps(self.storage[source_thread_id]))
            for key, value in list(self.writes.items()):
                if key[0] == source_thread_id:
                    self.writes[(target_thread_id, key[1], key[2])] = pickle.loads(pickle.dumps(value))
            for key, value in list(self.blobs.items()):
                if key[0] == source_thread_id:
                    self.blobs[(target_thread_id, key[1], key[2], key[3])] = pickle.loads(pickle.dumps(value))
            self._flush()

    def prune(self, thread_ids, *, strategy: str = "keep_latest") -> None:
        with self._io_lock:
            if strategy == "delete":
                for thread_id in thread_ids:
                    super().delete_thread(thread_id)
                self._flush()
                return
            if strategy != "keep_latest":
                raise ValueError(f"Unsupported prune strategy: {strategy}")

            changed = False
            for thread_id in thread_ids:
                namespaces = self.storage.get(thread_id, {})
                for checkpoint_ns, checkpoints in list(namespaces.items()):
                    if len(checkpoints) <= 1:
                        continue
                    latest_checkpoint_id = max(checkpoints.keys())
                    for checkpoint_id in list(checkpoints.keys()):
                        if checkpoint_id == latest_checkpoint_id:
                            continue
                        del checkpoints[checkpoint_id]
                        self.writes.pop((thread_id, checkpoint_ns, checkpoint_id), None)
                        changed = True
                    for key in list(self.blobs.keys()):
                        if key[0] == thread_id and key[1] == checkpoint_ns:
                            changed = True
                    if changed:
                        latest_tuple = self.get_tuple(
                            {
                                "configurable": {
                                    "thread_id": thread_id,
                                    "checkpoint_ns": checkpoint_ns,
                                    "checkpoint_id": latest_checkpoint_id,
                                }
                            }
                        )
                    keep_versions = set()
                    if latest_tuple is not None:
                        keep_versions = {
                            (thread_id, checkpoint_ns, channel, version)
                            for channel, version in latest_tuple.checkpoint["channel_versions"].items()
                        }
                    for blob_key in list(self.blobs.keys()):
                        if blob_key[0] == thread_id and blob_key[1] == checkpoint_ns and blob_key not in keep_versions:
                            del self.blobs[blob_key]
        if changed:
            self._flush()
