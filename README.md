<div align="center">

# TradingAgents

面向 A 股 / 港股研究场景的多 Agent LLM 交易分析框架

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-2EA043)
![Market](https://img.shields.io/badge/Market-CN__A%20%26%20HK-D7263D)
![Data](https://img.shields.io/badge/Data-AkShare%20%2B%20Eastmoney-0052CC)

</div>

<p align="center">
  <a href="./README.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-red"></a>
  <a href="./README_en.md"><img alt="English" src="https://img.shields.io/badge/Language-English-blue"></a>
</p>

<p align="center">
  <a href="#项目定位">项目定位</a> ·
  <a href="#当前能力">当前能力</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#稳定接入入口">稳定接入入口</a> ·
  <a href="#报告产物">报告产物</a> ·
  <a href="#项目结构">项目结构</a>
</p>

<p align="center">
  <img src="assets/schema.png" alt="TradingAgents 架构图" width="92%" />
</p>

## 项目定位

这是一个以研究流程为中心的多 Agent 交易分析框架，不是自动下单系统。

当前仓库主要解决三件事：

- 对指定标的和交易日生成完整研究结论，而不是只吐一句评级。
- 把多角色分析过程沉淀为标准化报告目录，便于下游系统接入、复盘和二次加工。
- 统一模型、数据源、运行时配置和持久化方式，降低集成成本。

当前默认市场语境以 **A 股** 为主，同时已经补齐 **港股** 数据链路与路由能力。

## 当前能力

- 多 Agent 闭环：分析师、研究员、交易员、风控和组合管理协同输出最终决策。
- A 股 / 港股支持：按标的自动选择对应数据流，港股已覆盖行情、指标、新闻和基础财务能力。
- 统一平台入口：推荐通过 `TradingPlatform.run_agent(...)` 调用，而不是直接依赖图对象。
- 多模型提供方：支持 OpenAI、Azure OpenAI、Anthropic、Google、xAI、OpenRouter、Ollama、Qwen、智谱。
- 主备 LLM 机制：支持主模型失败或空响应时自动切到备用 provider / model。
- 数据源回退：新闻、公告、市场新闻、部分基本面默认优先走东方财富妙想，失败后自动回退到 AkShare。
- 报告持久化：代码路径与 CLI 都可以输出统一的 `report_dir`，同时生成 Markdown 和 PDF。
- 快速模式：服务化调用可通过 `quick_mode=True` 强制收缩辩论轮次，降低耗时。
- 续跑与容错：本地 checkpoint 支持恢复，损坏的 checkpoint 会自动隔离而不是直接把流程打死。

当前默认配置位于 [`tradingagents/default_config.py`](./tradingagents/default_config.py)：

- `llm_provider = "zhipu"`
- `deep_think_llm = "GLM-5.1"`
- `quick_think_llm = "GLM-5.1"`
- `allow_vendor_fallback = True`
- `get_news / get_market_news / get_company_announcements / get_fundamentals = "mx,akshare"`

## 和旧版本的关键差异

| 维度 | 旧版本认知 | 当前仓库 |
|---|---|---|
| 市场覆盖 | A 股为主 | A 股为主，已补齐港股数据链路 |
| 对外入口 | 更偏图对象与 CLI | 推荐 `TradingPlatform.run_agent(...)` |
| 报告输出 | 侧重终端展示 | 标准化 `report_dir` + Markdown + PDF |
| 数据策略 | 单一数据源配置 | 工具级 vendor 路由 + 自动 fallback |
| 模型调用 | 单 provider 配置为主 | 多 provider + 主备 LLM fallback |
| 运行稳定性 | 普通本地状态 | checkpoint 恢复、损坏隔离、原子写盘 |

## 快速开始

### 1) 克隆仓库

```bash
git clone git@github.com:seawaylee/tradingagent.git
cd tradingagent
```

### 2) 安装依赖

推荐使用 `uv`：

```bash
uv sync
```

或直接本地可编辑安装：

```bash
pip install -e .
```

### 3) 配置环境变量

```bash
cp .env.example .env
```

按需配置：

```bash
export ZAI_API_KEY=...
export MX_APIKEY=...
export EASTMONEY_APIKEY=...

export OPENAI_API_KEY=...
export AZURE_API_KEY=...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...
export XAI_API_KEY=...
export OPENROUTER_API_KEY=...
export QWEN_API_KEY=...
```

说明：

- 默认跑通只需要可用的 LLM key，当前默认是 `ZAI_API_KEY`。
- 如果配置了 `MX_APIKEY` 或 `EASTMONEY_APIKEY`，新闻 / 公告 / 市场新闻 / 部分基本面会优先走东方财富妙想。
- 没配妙想 key 也能跑，系统会回退到 `akshare`。

### 4) 运行 CLI

```bash
tradingagents
```

或：

```bash
python -m cli.main
```

## 稳定接入入口

下游项目不要直接把 `TradingAgentsGraph` 当成稳定 API。  
推荐入口是 [`TradingPlatform`](./tradingagents/platform.py)。

```python
from tradingagents.agent_core.types import AgentRunRequest
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.platform import TradingPlatform

config = DEFAULT_CONFIG.copy()

platform = TradingPlatform(config=config)
platform.register_trading_agents_agent(debug=False)

result = platform.run_agent(
    "tradingagents",
    AgentRunRequest(
        symbol="600570",
        trade_date="2026-04-03",
        context={
            "quick_mode": True,
            "persist_report": True,
        },
    ),
)

print(result.decision.action.value)
print(result.decision.rationale)
print(result.outputs["report_file"])
print(result.outputs["report_pdf_file"])
print(result.outputs["report_dir"])
```

推荐下游优先读取这些字段：

- `result.decision.action.value`
- `result.decision.rationale`
- `result.outputs["report_file"]`
- `result.outputs["report_pdf_file"]`
- `result.outputs["report_dir"]`

更多集成细节见 [`docs/integration.md`](./docs/integration.md)。

## 报告产物

当 `persist_report=True` 时，会生成标准目录结构：

```text
reports/<symbol>_<trade_date>_<timestamp>/
├── 1_analysts/
├── 2_research/
├── 3_trading/
├── 4_portfolio/
├── complete_report.md
└── complete_report.pdf
```

其中：

- `1_analysts/`：市场、情绪、新闻、基本面分析
- `2_research/`：研究团队投资计划
- `3_trading/`：交易员执行计划
- `4_portfolio/`：组合经理最终交易决策
- `complete_report.*`：汇总后的完整报告

仓库已附带一批样例报告，位于 [`reports/`](./reports)。

## 项目结构

- `tradingagents/agents/`：各角色 Agent 实现
- `tradingagents/graph/`：多 Agent 状态图与编排
- `tradingagents/implementations/`：面向平台接口的 Agent 封装
- `tradingagents/dataflows/`：A 股 / 港股数据流与 vendor 路由
- `tradingagents/llm_clients/`：多 provider LLM 客户端
- `tradingagents/runtime_support.py`：checkpoint、快照、错误日志等运行时支持
- `tradingagents/reporting.py`：报告生成与持久化
- `cli/`：交互式命令行入口
- `docs/`：集成与使用文档
- `tests/`：测试

## 开发与测试

推荐：

```bash
uv run python -m pytest
```

或：

```bash
python -m unittest discover tests
```

如果本机 Python 版本低于 `3.10`，测试和运行都会出现兼容性问题。

## 开源说明

- 本仓库遵循 Apache-2.0 许可证。
- `README_legacy.md` 保留的是历史说明快照，仅作参考，不代表当前维护方式。
- README 中使用的部分架构图来自上游开源项目资源，保留了必要来源说明。

## 免责声明

本项目仅用于研究、工程实验和教学演示，不构成任何投资建议。实盘交易风险由使用者自行承担。
