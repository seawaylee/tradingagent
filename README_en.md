<div align="center">

# TradingAgents-A Share Edition

Multi-Agent LLM Trading Research Framework (Open-Source Derivative for China A-Share)

Author Homepage & Contact: <https://michaelyuancb.github.io/>

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache%202.0-2EA043)
![Market](https://img.shields.io/badge/Market-A--Share-D7263D)
![Data](https://img.shields.io/badge/Data-AkShare-0052CC)

</div>

<p align="center">
  <a href="./README.md"><img alt="中文" src="https://img.shields.io/badge/语言-中文-red"></a>
  <a href="./README_en.md"><img alt="English" src="https://img.shields.io/badge/Language-English-blue"></a>
</p>

<p align="center">
  <a href="#positioning">Positioning</a> ·
  <a href="#key-features">Features</a> ·
  <a href="#role-collaboration-maps-upstream-images-with-attribution">Role Maps</a> ·
  <a href="#key-differences-vs-historical-version">Differences</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#open-source-compliance">Compliance</a>
</p>

<p align="center">
  <img src="assets/schema.png" alt="TradingAgents A-Share Architecture" width="92%" />
</p>

## Positioning

`TradingAgents-A Share Edition` is a derivative open-source implementation based on [TradingAgents](https://github.com/TauricResearch/TradingAgents?tab=readme-ov-file), focused on **China A-share research context** and **multi-agent collaborative decision workflows**.  
The goal is not to promise returns, but to provide a reproducible, explainable, and extensible research framework.

Use cases:

- A-share multi-factor and multi-role research workflow experiments
- Collaboration mechanism validation for LLM agents in finance tasks
- Teaching demos, course labs, and strategy prototyping

## Key Features

- A-share data pipeline: AkShare by default for market, news, announcements, and fundamentals-related tools.
- End-to-end multi-agent loop: analysts, researchers, trader, risk control, and portfolio manager.
- Unified multi-provider LLM support: OpenAI, Azure OpenAI, Anthropic, Google, xAI, OpenRouter, Ollama, and Zhipu.
- CLI out of the box: choose symbol, trade date, analysts, and model settings interactively.
- Research-first outputs: transparent process and post-run review instead of black-box alpha claims.

## Role Collaboration Maps (Upstream Images with Attribution)

<p align="center">
  <img src="assets/analyst.png" alt="Analyst Team" width="100%" />
</p>

> Figure 1 Source: Upstream `TauricResearch/TradingAgents` official README (Analyst Team)
> Reference: https://github.com/TauricResearch/TradingAgents/blob/main/assets/analyst.png

<p align="center">
  <img src="assets/researcher.png" alt="Research Team" width="72%" />
</p>

> Figure 2 Source: Upstream `TauricResearch/TradingAgents` official README (Research Team)
> Reference: https://github.com/TauricResearch/TradingAgents/blob/main/assets/researcher.png

<p align="center">
  <img src="assets/trader.png" alt="Trader" width="72%" />
</p>

> Figure 3 Source: Upstream `TauricResearch/TradingAgents` official README (Trader)
> Reference: https://github.com/TauricResearch/TradingAgents/blob/main/assets/trader.png

<p align="center">
  <img src="assets/risk.png" alt="Risk and Portfolio" width="72%" />
</p>

> Figure 4 Source: Upstream `TauricResearch/TradingAgents` official README (Risk & Portfolio)
> Reference: https://github.com/TauricResearch/TradingAgents/blob/main/assets/risk.png

## Key Differences vs Historical Version

| Dimension | Historical Version | Current Version (A-Share) |
|---|---|---|
| Market context | US stocks as primary context | China A-share as primary context |
| Data backbone | Legacy US-stock-oriented data routes | AkShare-first A-share data routes |
| Research language | Primarily English context | Optimized for Chinese research context |
| Engineering target | Original framework release | Derivative release for local reproducible research |

## CLI Preview

<p align="center">
  <img src="assets/tradingagents_a/tradingagents_a_start.png" alt="CLI Start Screen" width="100%" />
</p>

<p align="center">
  <img src="assets/tradingagents_a/tradingagents_a_fin.png" alt="Financial Analysis Screen" width="100%" />
</p>

<p align="center">
  <img src="assets/tradingagents_a/tradingagents_results.png" alt="Trading Decision Screen" width="100%" />
</p>

## Quick Start

### 1) Install

```bash
git clone https://gitee.com/yuanchengbo1/trading-agents-a.git
cd trading-agents-a

pip install -e .
```

### 2) Configure Environment Variables

```bash
cp .env.example .env
```

Common model API keys (configure as needed):

```bash
export OPENAI_API_KEY=...
export AZURE_API_KEY=...
export GOOGLE_API_KEY=...
export ANTHROPIC_API_KEY=...
export XAI_API_KEY=...
export OPENROUTER_API_KEY=...
export ZAI_API_KEY=...
```

### 3) Start CLI

```bash
tradingagents
# or
python -m cli.main
```

## Python Usage Example

```python
from tradingagents.agent_core.types import AgentRunRequest
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.platform import TradingPlatform

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "zhipu"
config["backend_url"] = "https://open.bigmodel.cn/api/coding/paas/v4"
config["deep_think_llm"] = "GLM-5.1"
config["quick_think_llm"] = "GLM-5.1"

platform = TradingPlatform(config=config)
platform.register_trading_agents_agent(debug=False)

result = platform.run_agent(
    "tradingagents",
    AgentRunRequest(
        symbol="600570",
        trade_date="2026-04-03",
        context={"quick_mode": True},
    ),
)

print(result.decision.action.value)
print(result.outputs["report_file"])
print(result.outputs["report_pdf_file"])
```

## Project Structure

- `tradingagents/agents/`: role-specific agent implementations
- `tradingagents/graph/`: multi-agent state orchestration and workflow routing
- `tradingagents/dataflows/`: A-share data tools and routing
- `tradingagents/llm_clients/`: multi-provider LLM client wrappers
- `cli/`: interactive command-line interface
- `tests/`: unit tests

## Development and Testing

```bash
python -m unittest discover tests
python main.py
```

## Open-Source Compliance

This repository is a derivative work released under Apache-2.0.

1. Upstream reference: `TauricResearch/TradingAgents`.
2. This repository is not affiliated with the upstream team and does not represent upstream official positions.
3. Upstream naming appears for source attribution only and does not imply endorsement.
4. Historical document snapshot is preserved in `README_legacy.md`.
5. Review this repo's `LICENSE` and all third-party dependency licenses before redistribution or commercial use.
6. Some README images are sourced from upstream README assets and are explicitly attributed.
7. The architecture overview image `assets/schema.png` references upstream asset: `https://github.com/TauricResearch/TradingAgents/blob/main/assets/schema.png`.

## Disclaimer

This project is for research, engineering experiments, and educational demonstration only. It is not financial advice. Any live-trading decision and associated risk are solely the responsibility of the user.

## Developer and Contribution

- Secondary developer: [michaelyuan](https://michaelyuancb.github.io/)
- If this project helps you, consider giving it a star and sharing it
