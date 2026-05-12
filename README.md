<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

# TradingAgents: 多智能体 LLM 金融交易框架

> 基于 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 的个人增强版本

## 改进内容

在原版基础上做了以下增强：

- **Finnhub 数据源集成** — 新增 Finnhub 数据供应商，支持股票行情、技术指标、财务报表、新闻、内部交易等全品类数据，免费层 60 次/分钟
- **MiniMax 模型支持** — 新增 MiniMax（M2.7/M2.5/M2.1/M2）作为 LLM Provider，默认使用 MiniMax-M2.7
- **API 请求自动重试** — LLM 调用遇到 429/500/502/503/529 等服务端错误时自动指数退避重试（最多 6 次），不再因服务端过载导致整个分析流程崩溃
- **数据源容错回退** — 当首选数据源（如 Finnhub）失败或限流时，自动回退到其他可用数据源（yfinance / Alpha Vantage）
- **yfinance 调用增强** — 对 Yahoo Finance API 的 TypeError、ConnectionError 等瞬态错误增加重试，提升数据获取稳定性
- **UTF-8 编码修复** — 报告文件写入统一使用 UTF-8 编码，解决中文内容写入乱码问题
- **Docker 国内镜像** — Dockerfile 使用阿里云镜像源，适配国内网络环境
- **上游同步** — 已配置 upstream 远程仓库，可随时同步原项目更新

## 框架概述

TradingAgents 模拟真实交易公司的运作方式，部署多个专业化的 LLM 智能体协同工作：基本面分析师、情绪分析师、新闻分析师、技术分析师、交易员、风险管理团队，共同评估市场状况并做出交易决策。

> 本框架仅供研究用途，不构成任何金融、投资或交易建议。

### 分析师团队
- **基本面分析师** — 评估公司财务和业绩指标，发现内在价值和潜在风险
- **情绪分析师** — 分析社交媒体和公众情绪，衡量短期市场情绪
- **新闻分析师** — 监控全球新闻和宏观经济指标，解读事件对市场的影响
- **技术分析师** — 使用技术指标（如 MACD、RSI）检测交易模式

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### 研究员团队
- 多空研究员通过结构化辩论，对分析师团队的见解进行批判性评估，平衡潜在收益与风险

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 交易员智能体
- 综合分析师和研究员的报告，基于全面的市场洞察做出交易决策

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### 风险管理与投资组合经理
- 风险管理团队持续评估市场波动性、流动性等风险因素
- 投资组合经理审批/驳回交易提案

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## 安装

### 克隆项目

```bash
git clone https://github.com/Hunter-Han-SF/TradingAgents.git
cd TradingAgents
```

### 创建虚拟环境

```bash
conda create -n tradingagents python=3.13
conda activate tradingagents
```

### 安装依赖

```bash
pip install .
```

### Docker 部署

```bash
cp .env.example .env  # 填入你的 API Key
docker compose run --rm tradingagents
```

## API Key 配置

复制 `.env.example` 为 `.env`，填入你使用的 API Key：

```bash
cp .env.example .env

python -m cli.main  
```

### 支持的 LLM 提供商

| 提供商 | 环境变量 | 模型示例 |
|--------|----------|----------|
| MiniMax | `MINIMAX_API_KEY` | MiniMax-M2.7, MiniMax-M2.5 |
| OpenAI | `OPENAI_API_KEY` | GPT-5.4, GPT-5.4-mini |
| DeepSeek | `DEEPSEEK_API_KEY` | DeepSeek-V3 |
| 通义千问 | `DASHSCOPE_API_KEY` | Qwen 系列 |
| 智谱 GLM | `ZHIPU_API_KEY` | GLM 系列 |
| Google | `GOOGLE_API_KEY` | Gemini 3.x |
| Anthropic | `ANTHROPIC_API_KEY` | Claude 4.x |
| xAI | `XAI_API_KEY` | Grok 4.x |
| OpenRouter | `OPENROUTER_API_KEY` | 多模型路由 |
| Ollama | 无需 Key | 本地模型 |

### 支持的数据源

| 数据源 | 环境变量 | 说明 |
|--------|----------|------|
| Finnhub | `FINNHUB_API_KEY` | 免费 60 次/分钟，数据全面 |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | 免费层有限额 |
| Yahoo Finance | 无需 Key | 无限制，但偶尔不稳定 |

## 使用方式

### CLI 交互界面

```bash
tradingagents          # 安装后直接运行
python -m cli.main     # 从源码运行
```

启动后可选择股票代码、分析日期、LLM 提供商、研究深度等参数。

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Python API

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "minimax"
config["deep_think_llm"] = "MiniMax-M2.7"
config["quick_think_llm"] = "MiniMax-M2.7"
config["data_vendors"] = {
    "core_stock_apis": "finnhub",
    "technical_indicators": "finnhub",
    "fundamental_data": "finnhub",
    "news_data": "finnhub",
}

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-01-15")
print(decision)
```

完整配置选项见 `tradingagents/default_config.py`。

## 同步上游更新

```bash
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

## 致谢

- 原项目：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
- 论文：[TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138)

## Citation

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```
