<div align="center">

# TradingAgents

Multi-agent LLM trading analysis framework for China A-share and Hong Kong stock research

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
  <a href="#positioning">Positioning</a> ·
  <a href="#current-capabilities">Capabilities</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#stable-integration-entry">Integration</a> ·
  <a href="#report-artifacts">Reports</a> ·
  <a href="#project-structure">Structure</a>
</p>

<p align="center">
  <img src="assets/schema.png" alt="TradingAgents Architecture" width="92%" />
</p>

## Positioning

This repository is a research-oriented multi-agent trading analysis framework, not an auto-execution trading system.

It is designed to do three things well:

- Generate a complete research conclusion for a given symbol and trade date instead of a single rating line.
- Persist multi-role analysis into a stable report directory that downstream systems can consume and audit.
- Unify model access, data routing, runtime config, and report persistence behind one integration surface.

The primary market context is **China A-share**, with **Hong Kong stock** dataflow support already added to the repository.

## Current Capabilities

- End-to-end multi-agent loop: analysts, researchers, trader, risk management, and portfolio manager.
- A-share and HK coverage: symbol-aware dataflow routing for CN A-share and Hong Kong stocks.
- Stable platform entry: use `TradingPlatform.run_agent(...)` instead of wiring directly to the graph layer.
- Multi-provider LLM support: OpenAI, Azure OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama, Qwen, and Zhipu.
- Primary/secondary LLM fallback: automatically switch to a backup provider/model when the primary model fails or returns empty content.
- Vendor fallback for data tools: selected tools prefer Eastmoney MX and fall back to AkShare automatically.
- Standard report persistence: both code path and CLI can emit the same `report_dir`, Markdown report, and PDF report.
- Quick mode: lower debate depth for service-style integrations.
- Resume and runtime resilience: local checkpoints can recover, and corrupted checkpoint files are quarantined instead of breaking the run.

Current defaults live in [`tradingagents/default_config.py`](./tradingagents/default_config.py):

- `llm_provider = "zhipu"`
- `deep_think_llm = "GLM-5.1"`
- `quick_think_llm = "GLM-5.1"`
- `allow_vendor_fallback = True`
- `get_news / get_market_news / get_company_announcements / get_fundamentals = "mx,akshare"`

## Key Differences vs Earlier Repo State

| Dimension | Earlier expectation | Current repository |
|---|---|---|
| Market coverage | Primarily A-share | A-share first, with HK dataflow support added |
| Public entry point | Graph object and CLI centric | `TradingPlatform.run_agent(...)` recommended |
| Report output | Mostly terminal-facing | Stable `report_dir` + Markdown + PDF |
| Data strategy | Single vendor style config | Tool-level routing with automatic fallback |
| LLM strategy | One provider at a time | Multi-provider plus backup LLM fallback |
| Runtime stability | Basic local state | Checkpoint restore, corruption quarantine, atomic checkpoint flush |

## Quick Start

### 1) Clone

```bash
git clone git@github.com:seawaylee/tradingagent.git
cd tradingagent
```

### 2) Install

Recommended with `uv`:

```bash
uv sync
```

Or editable install:

```bash
pip install -e .
```

### 3) Configure environment variables

```bash
cp .env.example .env
```

Configure as needed:

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

Notes:

- A valid LLM key is enough to get started. The current default path uses `ZAI_API_KEY`.
- If `MX_APIKEY` or `EASTMONEY_APIKEY` is configured, news, announcements, market news, and some fundamentals tools will prefer Eastmoney MX.
- If MX is unavailable, the tool chain falls back to `akshare`.

### 4) Run the CLI

```bash
tradingagents
```

or:

```bash
python -m cli.main
```

## Stable Integration Entry

Downstream systems should not treat `TradingAgentsGraph` as the stable public API.  
Use [`TradingPlatform`](./tradingagents/platform.py) instead.

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

Recommended outputs to consume:

- `result.decision.action.value`
- `result.decision.rationale`
- `result.outputs["report_file"]`
- `result.outputs["report_pdf_file"]`
- `result.outputs["report_dir"]`

For deeper integration details, see [`docs/integration.md`](./docs/integration.md).

## Report Artifacts

When `persist_report=True`, the repository writes a stable report layout:

```text
reports/<symbol>_<trade_date>_<timestamp>/
├── 1_analysts/
├── 2_research/
├── 3_trading/
├── 4_portfolio/
├── complete_report.md
└── complete_report.pdf
```

Where:

- `1_analysts/`: market, sentiment, news, and fundamentals analysis
- `2_research/`: research team investment plan
- `3_trading/`: trader execution plan
- `4_portfolio/`: final portfolio decision
- `complete_report.*`: full aggregated report

The repository already includes sample outputs under [`reports/`](./reports).

## Project Structure

- `tradingagents/agents/`: role-specific agent implementations
- `tradingagents/graph/`: multi-agent graph orchestration
- `tradingagents/implementations/`: platform-facing agent wrappers
- `tradingagents/dataflows/`: A-share and HK dataflows plus vendor routing
- `tradingagents/llm_clients/`: multi-provider LLM clients
- `tradingagents/runtime_support.py`: checkpoints, snapshots, and runtime error handling
- `tradingagents/reporting.py`: report rendering and persistence
- `cli/`: interactive CLI entrypoint
- `docs/`: usage and integration docs
- `tests/`: test suite

## Development and Testing

Recommended:

```bash
uv run python -m pytest
```

or:

```bash
python -m unittest discover tests
```

If your local interpreter is older than Python `3.10`, both runtime and tests will break on syntax and dependency requirements.

## Open-Source Notes

- This repository is released under Apache-2.0.
- `README_legacy.md` is retained only as a historical document snapshot.
- Some architecture images in the README are adapted from upstream open-source assets and remain attributed where needed.

## Disclaimer

This project is for research, engineering experiments, and education only. It is not investment advice. Any live-trading decision and associated risk remain the user's responsibility.
