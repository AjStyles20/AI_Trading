# Astral AI: guide to the AI features

This guide explains what the AI in Astral does, which providers you can use,
how to set each one up, what it costs and what leaves your computer, and how to
use it safely. Pick whichever provider suits you; you can switch at any time in
**Settings** without losing anything else.

> **Short version:** the AI is a writing and explaining assistant. It never
> places trades, it is not connected to the trading loop, and its output is a
> hypothesis to test, not advice. Everything in Astral except the AI features
> works without any AI provider.

---

## 1. What the AI does

| Feature | Where in the app | What it does | Works without AI? |
|---|---|---|---|
| **Chat** | Left sidebar | Answers trading and strategy questions; remembers earlier conversations | No |
| **Generate strategy** | Bottom panel: describe a strategy, then **Generate** | Writes a Python strategy (`strategy(df)`) from your description | No |
| **AI export** | Strategy Builder | Turns your visual node graph into a strategy | Yes: **Local Export** builds one without AI |
| **Strategy summary** | Bottom panel | Explains a strategy's logic, risk controls and gaps in plain English | No |
| **Backtest summary** | Bottom panel | Explains return, drawdown, win rate, red flags, and one idea to test next | No |
| **News sentiment** | Badge above the chart | Rates recent Yahoo Finance headlines as bullish, bearish or neutral | Shows a placeholder **NEUTRAL +0.50** |

### What the AI does **not** do

- **It does not trade.** It cannot submit, cancel or change orders. The trading
  loop, risk checks and kill switch never consult it.
- **It does not see the app's data (yet).** When you ask "Analyze AAPL trend",
  the model receives only your text: no prices, indicators or backtest results.
  It answers from general knowledge, which can be out of date or wrong. See
  [Known limitations](#9-known-limitations-and-planned-improvements).
- **It does not see your accounts.** No broker keys, balances or positions are
  sent to it.

---

## 2. Choosing a provider

Astral supports three providers. All three use the same features; they differ
in cost, privacy, speed and what your computer needs.

| | **Groq** | **OpenAI** | **Ollama** (local) |
|---|---|---|---|
| **Cost** | Free tier with usage limits; paid plans available | Pay per use (billed per token) | Free |
| **API key** | Yes (free) | Yes (paid account) | No |
| **Where it runs** | Groq's servers | OpenAI's servers | Your own computer |
| **What leaves your computer** | Your prompts and the code/results you ask about | Same | Nothing: requests go to `127.0.0.1` |
| **Speed** | Very fast | Fast | Depends entirely on your hardware |
| **Hardware needed** | None | None | A capable PC (see below) |
| **Default model** | `openai/gpt-oss-20b` | `gpt-4.1-mini` | None: you must enter one |
| **Best for** | Getting started at no cost | Best answer quality, if you are happy to pay | Privacy, offline use, no running costs |

### Which one should I pick?

- **Starting out, or on a modest PC:** use **Groq**. It is free and puts no load
  on your computer.
- **You want the strongest answers and accept a small cost:** use **OpenAI**.
- **You want nothing to leave your machine:** use **Ollama**, but only on a
  computer that can run it (below).

### Can my computer run Ollama?

Local models need memory and processing power. As a rough guide:

| Your computer | Ollama experience |
|---|---|
| 4 GB RAM, low-power CPU, no graphics card | **Not recommended.** Very slow, and it starves the rest of the app of memory. |
| 8 GB RAM | Small models only (about 1–3 billion parameters); usable but slow, with basic answers |
| 16 GB RAM or a graphics card with 6 GB+ memory | Mid-size models (about 7–8 billion parameters); a good experience |
| 32 GB RAM or a strong graphics card | Larger models; answers approach hosted-model quality |

Check Ollama's model library for each model's memory needs before downloading.

### Other providers

The app currently supports exactly these three providers. Other services that
use the same OpenAI-compatible interface (for example OpenRouter, Together AI,
or LM Studio running locally) would need a small code change in
`backend/ai_engine/assistant.py` to add their address. Ask for it if you want
one; Astral deliberately never switches providers on its own.

---

## 3. Setting up a provider

All setup happens in the app: click the **⚙ (Settings)** icon next to the
AstralAI name. When a provider is configured, the **AI SETUP NEEDED** badge
changes to show the provider's name.

### Groq (free tier)

1. Sign in at <https://console.groq.com/keys> and create an API key.
2. In Astral: **Settings → AI provider → Groq**.
3. Paste the key into **Groq API Key**.
4. Optionally enter a model ID (leave it empty for the default,
   `openai/gpt-oss-20b`). Groq lists its current models in its console.
5. **Save.** Try the chat.

Groq's free tier limits how many requests and tokens you can use per minute and
per day. If you hit a limit, wait a little or reduce how often you ask.

### OpenAI (paid)

1. Create an API key at <https://platform.openai.com/api-keys>. Add billing to
   your OpenAI account.
2. **Set a monthly spending limit** in your OpenAI billing settings before you
   start, so costs cannot surprise you.
3. In Astral: **Settings → AI provider → OpenAI**, paste the key, optionally
   enter a model ID (default `gpt-4.1-mini`), and **Save**.

### Ollama (local, no key)

1. Install Ollama from <https://docs.ollama.com/quickstart>.
2. Download a model that fits your computer:
   ```bash
   ollama pull <model-name>
   ```
3. Make sure Ollama is running. It listens on `127.0.0.1:11434`.
4. In Astral: **Settings → AI provider → Ollama**, and type the **exact model
   name** you pulled (required; there is no default). **Save.**

The Astral installer does not include Ollama or any model, and does not start
Ollama for you.

### Switching providers

Change the provider in Settings and save. The new choice applies to the next AI
request; nothing else in the app changes. Keys for providers you are not using
stay stored securely and are not sent anywhere.

---

## 4. How your keys are stored

- Keys you enter in Settings are saved in the **Windows Credential Manager**
  (the operating system's secure store), under the name `AstralAI`. They are not
  written to Astral's database.
- Settings never shows a saved key again; it shows `********` instead.
- **Advanced:** environment variables take priority over saved keys, which is
  useful for development:

  | Provider | Environment variable |
  |---|---|
  | OpenAI | `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`) |
  | Groq | `GROQ_API_KEY` |

- To remove a key, clear it in Settings and save, or delete the `AstralAI`
  entry in Windows Credential Manager.

---

## 5. Privacy: what is sent where

| Action | Sent to the provider |
|---|---|
| Chat | Your message, plus a few recent messages and related past conversations for context |
| Generate strategy | Your strategy description |
| AI export | The node types and connections in your graph |
| Strategy summary | The strategy code and the symbol |
| Backtest summary | The backtest results and the symbol |
| News sentiment | Up to five recent headlines for the symbol |

**Never sent:** broker API keys, balances, positions, orders, or your trade
history.

**Stored on your computer:** chat history (in Astral's database) and a
long-term chat memory (a local ChromaDB store in Astral's data folder). Neither
is uploaded anywhere. With Ollama, nothing at all leaves your computer.

**Rule of thumb:** never type secrets (API keys, passwords, account numbers)
into the chat. The chat is sent to the provider and saved to local memory.

---

## 6. Using the AI well

### Writing strategy requests

Be specific. Name the indicators, the entry and exit rules, and the risk
controls:

> "EMA 12/26 crossover on 1h candles. Buy when the 12 crosses above the 26 and
> RSI(14) is below 65. Sell on the opposite cross or if RSI goes above 75. Stop
> loss 2%, take profit 4%, position size 25%."

works far better than "make me a profitable bitcoin strategy".

### The safe workflow for any AI-generated strategy

1. **Read the code.** Make sure it does what you asked. The AI can misread a
   request or invent logic.
2. **Validate:** use **Validate** to check that it runs in the restricted runtime.
3. **Backtest** with realistic fees and slippage.
4. **Check it out of sample:** use the walk-forward and out-of-sample evaluation,
   not just one good-looking backtest.
5. **Paper trade** it. The kill switch stays armed until you choose otherwise.
6. **Only then** consider anything further, following the maturity gates in the
   README.

Use **Backtest summary** to get a plain-English read of results and a
suggestion for what to try next, then test that suggestion the same way.

### Healthy scepticism

- An AI answer is a **starting point**, not a fact. Models can sound confident
  and be wrong.
- No AI output, backtest or optimizer score proves a strategy will make money.
- Until the chat can see live data, double-check any price, level or "current
  trend" it mentions against the chart.

---

## 7. Safety rules

These are built into the project and are not negotiable:

- **The AI never places trades.** Orders go only through the guarded submission
  path with its risk checks and kill switch.
- **Generated strategies are Python code** run in a restricted runtime. That
  runtime blocks imports, file, network and environment access, but it is **not
  an operating-system sandbox**. Run only strategies generated by Astral's own
  AI or written by you. **Never paste in strategy code from strangers.**
- **Prefer the declarative strategy format** (the visual builder) where you can.
- **Astral never switches AI providers silently.** If your chosen provider is
  unavailable, AI features report that clearly instead of sending your data
  elsewhere.
- **Paper trading is the default.** Nothing about the AI changes that.

---

## 8. Troubleshooting

| What you see | Likely cause | What to do |
|---|---|---|
| **AI SETUP NEEDED** badge | No provider configured | Set one up (section 3) |
| "Configure an AI provider in Settings…" | Missing key, or no Ollama model name | Add the key or model name in Settings and save |
| "Error: Invalid API key…" | Key is wrong, revoked, or for another provider | Create a new key and paste it again |
| **Generate** returns an error (HTTP 503) | No provider configured | Configure one, or use **Local Export** in the Strategy Builder |
| Error mentioning **429** / rate limit | Groq free-tier or OpenAI limit reached | Wait and retry; ask less often; or upgrade your plan |
| Error mentioning connection to `127.0.0.1:11434` | Ollama is not running | Start Ollama, then retry |
| Ollama error about the model | The model name does not match what you pulled | Run `ollama list` and copy the exact name into Settings |
| Very slow answers with Ollama | The model is too large for your computer | Use a smaller model, or switch to Groq |
| The first chat message is slow | The local chat memory is starting up for the first time | Wait; later messages are faster |
| Sentiment badge always **NEUTRAL +0.50** | No provider configured (it is a placeholder) | Configure a provider |

---

## 9. Known limitations and planned improvements

| Limitation | Effect | Planned fix |
|---|---|---|
| Chat does not receive app data | Answers about "the trend" are not based on the chart you see | Send the current symbol, live price, timeframe, indicator values and last backtest with each question |
| AI export sends only the graph's shape | Indicator periods and thresholds you set in the builder are guessed | Include each node's settings in the export |
| Sentiment shows **NEUTRAL +0.50** without a provider | Looks like a real reading when it is not | Show "needs AI" instead |
| Sentiment uses only five headlines | A thin sample; easily skewed | Use more sources and show the headlines used |
| Only three providers | Other OpenAI-compatible services need a code change | Add a "custom provider" option if wanted |

---

## 10. For developers

| Piece | Location |
|---|---|
| Provider selection, chat, summaries, memory | `backend/ai_engine/assistant.py` |
| Strategy generation prompts | `backend/ai_engine/strategy_generator.py` |
| Endpoints | `backend/main.py`: `/api/chat`, `/api/strategy`, `/api/strategy/build`, `/api/ai/summary/strategy`, `/api/ai/summary/backtest` |
| Sentiment | `core/research_service.py`, served by `/api/research/sentiment/{symbol}` |
| Settings (`ai_provider`, `ai_model`) and key storage | `backend/settings_api.py`, `core/credential_provider.py` |
| Long-term chat memory | `database/vector_manager.py` (ChromaDB) |
| Settings UI | `frontend/src/components/Sidebar.tsx` |

All three providers are reached through LangChain's `ChatOpenAI` client: Groq
at `https://api.groq.com/openai/v1` and Ollama at
`http://127.0.0.1:11434/v1`. The AI tests live in
`backend/tests/test_ai_providers.py` and
`backend/tests/test_ai_strategy_generation.py`.
