# TradingAgents-A股版 使用与接入指南

这份文档面向两类读者：

- 本地手工使用的研究人员：通过 CLI 交互式运行。
- 需要从另一个项目接入的工程方：通过 Python 代码稳定调用。

如果你是下游系统接入方，推荐直接使用 `TradingPlatform.run_agent(...)`。  
不要把 `TradingAgentsGraph` 当成对外稳定接口；它更适合框架内部调试和图级实验。

## 0. 给 Code Agent 的 30 秒接入版

如果你的目标是“让另一个项目里的 code agent 立刻调起来”，只看这段就够了。

### 0.1 必备环境变量

```bash
export ZAI_API_KEY=你的智谱Key
```

可选但推荐：

```bash
export MX_APIKEY=你的东方财富妙想Key
```

说明：

- LLM 默认就是 `zhipu + GLM-5.1`，不需要再改 provider。
- 妙想 key 不写死在代码里，只从 `MX_APIKEY` 或 `EASTMONEY_APIKEY` 读取。
- 如果没有配置妙想 key，相关数据工具会自动从 `mx` 回退到 `akshare`。

### 0.2 稳定调用入口

不要直接调用图对象。  
稳定入口只有这一条：

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
```

### 0.3 先读哪些结果

```python
result.decision.action.value
result.decision.rationale
result.outputs["report_file"]
result.outputs["report_pdf_file"]
result.outputs["report_dir"]
```

业务上建议这样理解：

- `action`：最终标准动作，只会是 `BUY` / `HOLD` / `SELL`
- `rationale`：最终组合经理结论
- `report_file`：本次完整 Markdown 报告
- `report_pdf_file`：本次完整 PDF 报告
- `report_dir`：本次全部持久化产物目录

### 0.4 默认模型和默认数据源

当前默认配置已经内置：

- `llm_provider = zhipu`
- `backend_url = https://open.bigmodel.cn/api/coding/paas/v4`
- `deep_think_llm = GLM-5.1`
- `quick_think_llm = GLM-5.1`

当前默认数据源路由：

- `get_news = mx,akshare`
- `get_market_news = mx,akshare`
- `get_company_announcements = mx,akshare`
- `get_fundamentals = mx,akshare`

含义：

- 优先用东方财富妙想
- 妙想不可用时自动回退到 `akshare`
- 行情和技术指标链路仍以现有本地数据流为主，不依赖妙想

### 0.5 快速模式

如果你是系统接入方，默认建议开：

```python
context={"quick_mode": True}
```

效果：

- `max_debate_rounds = 1`
- `max_risk_discuss_rounds = 1`

这样会显著缩短总耗时，更适合服务化场景。

## 1. 业务定位

本项目不是一个“直接下单”的交易系统，而是一个“多 Agent 研究决策引擎”。

它的业务输出本质上是：

- 对某个 A 股标的在某个交易日做一次完整研究；
- 生成多角色分析过程；
- 输出最终交易建议；
- 将过程和结论持久化为标准报告目录，便于下游系统消费、审计和复盘。

最终建议使用三态输出：

- `BUY`：看多，建议建仓或加仓。
- `HOLD`：中性，建议继续持有或继续观察。
- `SELL`：看空，建议减仓、清仓，或不进入多头仓位。

注意：

- 底层原始信号可能出现 `OVERWEIGHT` / `UNDERWEIGHT`；
- 平台层会将其规范化为 `BUY` / `SELL`；
- 下游系统通常只需要消费标准化后的 `BUY` / `HOLD` / `SELL`。

## 2. 全流程在做什么

一次完整分析的业务链路如下：

1. `Market Analyst`
   读取行情、技术指标、量价结构，形成市场面判断。
2. `Social Analyst`
   读取新闻/情绪相关信息，形成舆情和市场情绪判断。
3. `News Analyst`
   读取公司新闻、市场新闻、公司公告，形成事件驱动判断。
4. `Fundamentals Analyst`
   读取财务报表、经营数据、基本面信息，形成基本面判断。
5. `Bull Researcher` / `Bear Researcher`
   分别从多头和空头视角辩论。
6. `Research Manager`
   汇总研究团队观点，形成投资计划。
7. `Trader`
   把研究结论转换为更接近执行层的交易计划。
8. `Aggressive` / `Conservative` / `Neutral Analyst`
   做风险辩论。
9. `Portfolio Manager`
   形成最终组合层决策。
10. `Report Finalizer`
   整理最终面向用户的报告字段。

对应的持久化报告目录也分成这四层：

- `1_analysts`：四类基础分析师报告。
- `2_research`：研究团队最终投资计划。
- `3_trading`：交易员执行计划。
- `4_portfolio`：组合经理最终交易决策。

## 3. 运行前准备

### 3.1 安装

```bash
git clone <your-repo-url>
cd tradingagent
pip install -e .
```

### 3.2 推荐环境变量

如果你使用智谱 `GLM-5.1`，推荐显式设置：

```bash
export ZAI_API_KEY=你的智谱Key
```

如果你希望新闻、公告、市场新闻、部分基本面优先走东方财富妙想，再配置：

```bash
export MX_APIKEY=你的东方财富妙想Key
```

当前项目默认配置已经是：

- `llm_provider = zhipu`
- `backend_url = https://open.bigmodel.cn/api/coding/paas/v4`
- `deep_think_llm = GLM-5.1`
- `quick_think_llm = GLM-5.1`

默认工具路由中，这几类会优先使用 `mx`，失败后自动回退 `akshare`：

- `get_news`
- `get_market_news`
- `get_company_announcements`
- `get_fundamentals`

报告默认落盘根目录可以通过环境变量覆盖：

```bash
export TRADINGAGENTS_REPORT_DIR=/your/persistent/report/root
```

## 4. CLI 调用方式

CLI 适合人工研究和手工验证，不适合服务化集成。

### 4.1 启动命令

```bash
tradingagents
```

或：

```bash
python -m cli.main
```

### 4.2 CLI 输入内容

CLI 会依次询问：

1. 股票代码
2. 分析日期
3. 是否修改配置
4. 如果修改配置，会继续询问：
   - 内部推理语言
   - 最终输出语言
   - 启用哪些分析师
   - 研究深度
   - LLM provider
   - 模型与 provider 专属参数

最后会询问两件事：

1. 是否保存报告
2. 是否在终端展示完整报告

### 4.3 CLI 输入格式

股票代码推荐直接传纯数字：

- `600570`
- `000001`
- `300750`

系统也能识别这些形式：

- `600570.SH`
- `000001.SZ`
- `sh600570`
- `SZ000001`

分析日期格式必须是：

```text
YYYY-MM-DD
```

并且不能晚于当天。

### 4.4 CLI 产出

如果你选择保存报告，默认会写入：

```text
reports/<ticker>_<timestamp>/
```

例如：

```text
reports/600570_20260406_011703/
```

目录结构如下：

```text
reports/600570_20260406_011703/
├── 1_analysts
│   ├── fundamentals_report.md
│   ├── market_report.md
│   ├── news_report.md
│   └── sentiment_report.md
├── 2_research
│   └── investment_plan.md
├── 3_trading
│   └── trader_investment_plan_report.md
├── 4_portfolio
│   └── final_trade_decision_report.md
├── complete_report.pdf
└── complete_report.md
```

其中：

- `complete_report.md` 是聚合后的总报告，适合直接给人看。
- `complete_report.pdf` 是和 `complete_report.md` 同内容的 PDF 版本，适合归档、传阅和外部系统挂载。
- `4_portfolio/final_trade_decision_report.md` 是最接近“最终结论”的文件，适合下游系统抓取。

## 5. 代码调用方式

代码调用是下游系统接入的推荐方案。

### 5.1 最小示例

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
print(result.decision.rationale)
print(result.outputs["report_file"])
print(result.outputs["report_pdf_file"])
print(result.outputs["report_dir"])
```

### 5.2 推荐的服务化封装

```python
from tradingagents.agent_core.types import AgentRunRequest
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.platform import TradingPlatform


def analyze_stock(symbol: str, trade_date: str) -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "zhipu"
    config["backend_url"] = "https://open.bigmodel.cn/api/coding/paas/v4"
    config["deep_think_llm"] = "GLM-5.1"
    config["quick_think_llm"] = "GLM-5.1"
    config["report_output_dir"] = "/data/tradingagents/reports"

    platform = TradingPlatform(config=config)
    platform.register_trading_agents_agent(debug=False)

    result = platform.run_agent(
        "tradingagents",
        AgentRunRequest(
            symbol=symbol,
            trade_date=trade_date,
            context={
                "persist_report": True,
                "quick_mode": True,
            },
        ),
    )

    return {
        "symbol": result.decision.symbol,
        "trade_date": result.decision.trade_date,
        "action": result.decision.action.value,
        "rationale": result.decision.rationale,
        "report_file": result.outputs.get("report_file"),
        "report_pdf_file": result.outputs.get("report_pdf_file"),
        "report_dir": result.outputs.get("report_dir"),
        "raw_signal": result.outputs.get("raw_signal"),
    }
```

### 5.3 自定义报告目录

如果下游系统希望自己控制这次运行的落盘路径，可以通过 `context` 传入：

```python
result = platform.run_agent(
    "tradingagents",
    AgentRunRequest(
        symbol="600570",
        trade_date="2026-04-03",
        context={
            "report_save_path": "/data/reports/stock_jobs/job_12345",
        },
    ),
)
```

此时会直接写到你指定的目录，而不是自动生成 `reports/<ticker>_<timestamp>`。

### 5.4 只要结果，不落报告

```python
result = platform.run_agent(
    "tradingagents",
    AgentRunRequest(
        symbol="600570",
        trade_date="2026-04-03",
        context={
            "persist_report": False,
        },
    ),
)
```

但对于生产接入，不建议关闭持久化。  
建议把报告目录作为审计和复盘材料保留下来。

## 6. 代码接口契约

### 6.1 输入：`AgentRunRequest`

定义位置：`tradingagents.agent_core.types.AgentRunRequest`

字段如下：

| 字段 | 类型 | 是否必填 | 说明 |
|---|---|---|---|
| `symbol` | `str` | 是 | 股票代码。推荐直接传纯数字，如 `600570`。 |
| `trade_date` | `str` | 是 | 分析日期，格式必须是 `YYYY-MM-DD`。 |
| `context` | `dict[str, Any]` | 否 | 可选扩展参数。 |

`context` 当前真正生效且建议关注的字段：

| 字段 | 类型 | 默认值 | 业务含义 |
|---|---|---|---|
| `persist_report` | `bool` | `True` | 是否将本次结果持久化为标准报告目录。 |
| `quick_mode` | `bool` | `False` | 快速模式。强制 `max_debate_rounds=1`、`max_risk_discuss_rounds=1`。 |
| `report_base_dir` | `str` | `config["report_output_dir"]` | 报告根目录。 |
| `report_save_path` | `str` | `None` | 指定本次运行的精确报告目录。 |
| `confidence` | `float` | `None` | 透传到 `decision.confidence`，便于下游系统补充置信度字段。 |
| `quantity` | `float` | `1.0` | 透传到 `decision.quantity`，主要用于后续回测。 |
| `decision_time` | `str` | `None` | 透传到 `decision.decision_time`，主要用于回测时定位入场时间。 |
| `holding_period_bars` | `int` | `1` | 透传到 `decision.holding_period_bars`，主要用于回测。 |

### 6.2 输出：`AgentRunResult`

定义位置：`tradingagents.agent_core.types.AgentRunResult`

主要字段如下：

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_name` | `str` | 当前运行的 agent 名称，默认是 `tradingagents`。 |
| `decision` | `AgentDecision \| None` | 标准化后的交易决策。 |
| `outputs` | `dict[str, Any]` | 原始补充产物。 |

### 6.3 输出：`AgentDecision`

| 字段 | 类型 | 说明 |
|---|---|---|
| `agent_name` | `str` | 当前 agent 名称。 |
| `symbol` | `str` | 请求中的股票代码。 |
| `trade_date` | `str` | 请求中的分析日期。 |
| `action` | `DecisionAction` | 标准化动作：`BUY` / `HOLD` / `SELL`。 |
| `rationale` | `str` | 最终组合经理报告，一般等于 `final_trade_decision_report`。 |
| `confidence` | `float \| None` | 透传字段。 |
| `quantity` | `float` | 透传字段。 |
| `decision_time` | `str \| None` | 透传字段。 |
| `holding_period_bars` | `int` | 透传字段。 |
| `metadata` | `dict[str, Any]` | 原始信号、启用分析师、报告路径等元数据。 |

### 6.4 `outputs` 里有什么

目前代码调用路径会返回这些关键字段：

| 键 | 类型 | 说明 |
|---|---|---|
| `raw_signal` | `str` | 图层原始信号，可能是 `BUY` / `SELL` / `HOLD` / `OVERWEIGHT` / `UNDERWEIGHT`。 |
| `final_state` | `dict[str, Any]` | LangGraph 最终状态，包含所有阶段报告。 |
| `report_file` | `str` | `complete_report.md` 的绝对路径。 |
| `report_pdf_file` | `str` | `complete_report.pdf` 的绝对路径。 |
| `report_dir` | `str` | 本次报告目录的绝对路径。 |
| `quick_mode` | `bool` | 本次运行是否启用了快速模式。 |

建议下游系统把接口消费分成两层：

- 稳定对外契约：`decision`、`report_file`、`report_dir`
- 调试与扩展信息：`outputs["final_state"]`

原因很简单：

- `decision` 和报告目录是稳定业务产物；
- `final_state` 属于内部图状态，适合调试，不建议做强绑定字段依赖。

## 7. 可调配置及业务含义

### 7.1 LLM 配置

| 配置项 | 说明 |
|---|---|
| `llm_provider` | 模型提供方。当前推荐 `zhipu`。 |
| `backend_url` | 提供方基础地址。智谱当前使用 `https://open.bigmodel.cn/api/coding/paas/v4`。 |
| `quick_think_llm` | 快速思考模型。 |
| `deep_think_llm` | 深度思考模型。 |

当前推荐配置：

```python
config["llm_provider"] = "zhipu"
config["backend_url"] = "https://open.bigmodel.cn/api/coding/paas/v4"
config["quick_think_llm"] = "GLM-5.1"
config["deep_think_llm"] = "GLM-5.1"
```

### 7.2 分析范围配置

| 配置项 | 说明 |
|---|---|
| `selected_analysts` | 默认启用哪些分析师，可选值：`market`、`social`、`news`、`fundamentals`。 |
| `max_debate_rounds` | 多空研究员辩论轮次。越高越慢、越贵。 |
| `max_risk_discuss_rounds` | 风险辩论轮次。越高越慢、越贵。 |
| `timeout` | 数据或模型调用的超时时间。 |

对于服务化接入，建议从较保守的配置开始：

```python
config["selected_analysts"] = ["market", "social", "news", "fundamentals"]
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
```

原因：

- 更快；
- 更稳定；
- 更容易控制模型成本；
- 先跑通全链路，再考虑增加辩论深度。

### 7.3 报告持久化配置

| 配置项 | 说明 |
|---|---|
| `report_output_dir` | 代码调用默认报告根目录。 |
| `TRADINGAGENTS_REPORT_DIR` | `report_output_dir` 的环境变量版本。 |

默认值是仓库根目录下的：

```text
reports/
```

## 8. 报告文件的业务意义

### `1_analysts/market_report.md`

业务意义：  
市场面与技术面判断，关注价格趋势、均线、MACD、RSI、成交量、波动等。

适用场景：

- 技术分析解释
- 盘面环境判断
- 执行择时辅助

### `1_analysts/sentiment_report.md`

业务意义：  
情绪面和舆情面判断，关注市场情绪变化与外部情绪扰动。

适用场景：

- 舆情摘要
- 风险偏好观察
- 事件热度判断

### `1_analysts/news_report.md`

业务意义：  
公司新闻、市场新闻、公司公告的事件解释层。

适用场景：

- 事件驱动研究
- 公告快速摘要
- 新闻对交易决策的因果解释

### `1_analysts/fundamentals_report.md`

业务意义：  
财务报表和经营面的解释层，关注收入、利润、现金流、资产负债、经营质量等。

适用场景：

- 基本面研究
- 中期逻辑验证
- 估值与经营质量判断

### `2_research/investment_plan.md`

业务意义：  
研究团队在多空辩论后的综合结论，属于“研究结论层”。

### `3_trading/trader_investment_plan_report.md`

业务意义：  
把研究结论转换成更接近交易执行的话术和计划，属于“交易计划层”。

### `4_portfolio/final_trade_decision_report.md`

业务意义：  
最终可交付的组合层决策，最适合给下游系统作为主结论读取。

### `complete_report.md`

业务意义：  
将前面所有关键阶段按顺序汇总成一份完整报告，适合人工查阅、归档和审计。

## 9. 下游项目接入建议

### 推荐接入策略

1. 下游系统只调用 `TradingPlatform.run_agent(...)`
2. 只把 `AgentRunResult.decision` 作为在线主返回
3. 同时保存 `report_file` / `report_dir` 到你自己的任务记录表
4. 如需额外调试，再读取 `outputs["final_state"]`

### 不推荐的接入方式

- 不要直接依赖 CLI 交互流程
- 不要把 `tmp_run_logs/` 当成正式产出目录
- 不要强依赖 `eval_results/` 或图调试日志格式
- 不要把 `final_state` 当成长期稳定 JSON Schema

原因：

- CLI 是给人交互的，不是给系统调用的；
- `tmp_run_logs/` 和 `eval_results/` 更偏调试；
- 真正稳定且适合持久化消费的是 `reports/` 和 `AgentRunResult`。

## 10. 常见问题

### Q1：下游应该读哪个文件作为最终结论？

优先级建议如下：

1. `AgentRunResult.decision.action`
2. `AgentRunResult.decision.rationale`
3. `4_portfolio/final_trade_decision_report.md`
4. `complete_report.md`

### Q2：股票代码到底传什么格式？

推荐直接传纯数字，例如：

- `600570`
- `000001`

系统会自动规范化为 A 股标准后缀形式。

### Q3：服务集成时应该用 CLI 还是代码？

用代码。  
CLI 只适合人工调试和演示。

### Q4：如果我要持久化到自己的任务目录怎么办？

在 `AgentRunRequest.context` 里传：

```python
{
    "report_save_path": "/your/task/output/path"
}
```

### Q5：如果我只想拿最终动作和最终报告，不想解析一大坨状态怎么办？

直接读：

```python
result.decision.action.value
result.decision.rationale
result.outputs["report_file"]
```

这就是推荐的最小消费集合。
