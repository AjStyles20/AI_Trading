from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from database.vector_manager import VectorMemoryManager
from database.sqlite_manager import get_settings, record_chat_message, get_recent_chat_messages
from core.credential_provider import resolve_api_keys
from ai_engine.attachments import attachment_note
from ai_engine.workspace_context import WorkspaceContext, format_workspace_context
import os


CHAT_SYSTEM_PROMPT = """You are Astral AI, the trading companion built into the Astral desktop app.
You help the user analyze markets, design and improve strategies, and understand backtests.
Act as a collaborative partner: ask a clarifying question when a request is vague, and if a strategy idea is flawed, say so politely and suggest improvements. The user makes every decision.

What you can and cannot do:
- You cannot place, change or cancel trades. Astral's trading engine and its risk checks do that, only when the user chooses.
- You only see market data when a "Current workspace" section appears below: a snapshot of the symbol, price, indicators and latest backtest on the user's screen. Use only those figures. Without that section you cannot see live prices, chart data or account data. Never invent current prices, levels or "what the market is doing right now"; say plainly what you cannot see and point the user to the chart in the app.

Strategies in Astral:
- Astral runs strategies itself. Never write VectorBT, Backtrader, Zipline, or code that downloads data (yfinance, ccxt, requests); it cannot run inside Astral.
- An Astral strategy is exactly one function `strategy(df)`. `df` has columns open, high, low, close, volume; `pd` (pandas) and `np` (numpy) are already available. No imports, files, network, eval/exec or dunder attributes.
- It returns `df` with a `signal` column (1 = buy, -1 = sell, 0 = hold) and optionally:
  `position_size_pct` (0-100), `stop_loss_pct` and `take_profit_pct` (percent, 0-100, e.g. 2 for 2%), and `cooldown_bars` (non-negative integer).
- For a ready-to-run strategy, point the user to the Generate button (or the Strategy Builder), then Validate and Run Backtest. Remind them that no backtest proves future profit.

Format replies in Markdown: short headings, bullet lists, tables where they help, and fenced code blocks with a language (```python).
"""


def build_chat_system_prompt(context_str: str = "", history_str: str = "", workspace_str: str = "") -> str:
    workspace = f"\n{workspace_str}\n" if workspace_str else ""
    return f"{CHAT_SYSTEM_PROMPT}{workspace}\n{context_str}\n{history_str}\n"


class AstralAIAssistant:
    def __init__(self):
        self.memory_manager = VectorMemoryManager()
        self.llm = None
        self.model_name = None
        self.vision_llm = None
        self.vision_model_name = None
        self._initialized = False

    def _initialize_llm(self):
        settings = get_settings()
        provider = (settings or {}).get("ai_provider", "openai")
        defaults = {"openai": "gpt-4.1-mini", "groq": "openai/gpt-oss-20b", "ollama": ""}
        if provider not in defaults:
            raise ValueError("Unsupported AI provider")
        configured_model = (settings or {}).get("ai_model") or ""
        model_name = configured_model or (os.environ.get("OPENAI_MODEL", defaults[provider]) if provider == "openai" else defaults[provider])
        # Images need a vision-capable model. OpenAI's chat models read images, so
        # they default to the chat model; Groq and Ollama need one chosen in Settings.
        vision_model = (settings or {}).get("ai_vision_model") or (model_name if provider == "openai" else "")
        self.provider = provider
        self.model_name = model_name
        self.vision_model_name = vision_model or None
        self.llm = None
        self.vision_llm = None
        self._initialized = True

        api_key = "ollama" if provider == "ollama" else resolve_api_keys(settings).get(provider)
        if not api_key or api_key == "mock-key":
            return

        base_urls = {"groq": "https://api.groq.com/openai/v1", "ollama": "http://127.0.0.1:11434/v1"}

        def client(model: str):
            options = dict(temperature=0.4, api_key=api_key, model=model, request_timeout=120.0)
            if provider in base_urls:
                options["base_url"] = base_urls[provider]
            return ChatOpenAI(**options)

        if model_name:
            self.llm = client(model_name)
        if vision_model:
            self.vision_llm = client(vision_model)

    def get_vision_llm(self):
        if not self._initialized:
            self._initialize_llm()
        return self.vision_llm

    def get_llm(self):
        """Initialize the LLM on first use, after application startup has initialized storage."""
        if not self._initialized:
            self._initialize_llm()
        return self.llm

    def reload_settings(self):
        """Forces a refresh of the LLM configuration."""
        print("DEBUG: Reloading AI settings...")
        self._initialized = False
        self._initialize_llm()

    def analyze_market_query(
        self,
        query: str,
        conversation_id: str,
        images: list[str] | None = None,
        workspace: WorkspaceContext | None = None,
    ) -> str:
        """Processes a market or strategy query using the LLM and persistent memory.

        `images` are validated base64 data URLs (see ai_engine.attachments). They
        are sent to a vision-capable model and never stored; history and memory
        keep only a short "[n images attached]" note.
        """
        images = images or []
        note = attachment_note(len(images))
        stored_query = f"{query}\n\n{note}" if note else query
        import time
        start_time = time.time()

        # 1. Retrieve past context from Vector DB
        try:
            print(f"DEBUG: Starting vector recall for query: {query}")
            # Wrap query in a more descriptive error check
            past_context = self.memory_manager.recall_conversations(query, n_results=2)
            print(f"DEBUG: Vector recall finished in {time.time() - start_time:.2f}s")
        except Exception as e:
            msg = str(e)
            print(f"WARNING: Vector recall failed: {msg}")
            if "timeout" in msg.lower() or "handshake" in msg.lower():
                print("HINT: This is common on the first run. Proceeding without context...")
            past_context = {"documents": [[]]}

        # 1b. Retrieve recent short-term conversation history
        recent_messages = []
        try:
            recent_messages = get_recent_chat_messages(conversation_id, limit=8)
        except Exception as e:
            print(f"WARNING: Failed to load recent chat history: {e}")

        gen_start = time.time()
        context_str = ""
        if past_context and past_context.get("documents") and len(past_context["documents"][0]) > 0:
            context_str = "\nPast Context (User Preferences/Previous Decisions):\n" + "\n".join(past_context["documents"][0])

        history_str = ""
        if recent_messages:
            formatted = "\n".join([f"{item['role'].upper()}: {item['content']}" for item in recent_messages])
            history_str = f"\nRecent Conversation:\n{formatted}"

        # 2. Build the prompt
        system_prompt = build_chat_system_prompt(context_str, history_str, format_workspace_context(workspace))
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=(
                [{"type": "text", "text": query or "Describe this image."}]
                + [{"type": "image_url", "image_url": {"url": url}} for url in images]
            ) if images else query)
        ]

        # 3. Get response
        llm = self.get_vision_llm() if images else self.get_llm()
        if llm is None and images:
            return ("Reading images needs a vision-capable model. Choose one under Settings → Vision model "
                    "(OpenAI's chat models work as they are; for Groq or Ollama enter an image-capable model).")
        if llm is None:
            return "Configure an AI provider in Settings. OpenAI and Groq need API keys; Ollama needs a local model and running server."

        try:
            print("DEBUG: Starting LLM generation...")
            response = llm.invoke(messages)
            response_text = response.content
            print(f"DEBUG: LLM generation finished in {time.time() - gen_start:.2f}s")
        except Exception as e:
            err_msg = str(e)
            print(f"CRITICAL: LLM generation failed: {err_msg}")
            if "401" in err_msg or "invalid_api_key" in err_msg:
                return "Error: Invalid API key. Please check the selected AI provider and its key in Settings."
            return f"Error during generation: {err_msg}"

        # 4. Save this interaction to Long-Term Memory
        interaction_text = f"User asked: {stored_query}\nAI Responded: {response_text}"
        import uuid
        self.memory_manager.remember_conversation(
            doc_id=str(uuid.uuid4()),
            text=interaction_text,
            metadata={"topic": "market_analysis", "type": "chat_log"}
        )

        try:
            record_chat_message(conversation_id, "user", stored_query)
            record_chat_message(conversation_id, "assistant", response_text)
        except Exception as e:
            print(f"WARNING: Failed to persist chat history: {e}")

        return response_text

    def summarize_strategy(self, strategy_code: str, symbol: str | None = None) -> str:
        llm = self.get_llm()
        if llm is None:
            return "Configure an AI provider in Settings to enable AI summaries."

        prompt = f"""Summarize this trading strategy in plain English.
Explain the indicators, entry/exit logic, risk controls, and any risks or missing safeguards.
Keep it concise and practical.

Symbol context: {symbol or "N/A"}

Strategy code:
{strategy_code}
"""
        messages = [
            SystemMessage(content="You are a trading strategy reviewer. Be concise, practical, and risk-aware."),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        return response.content

    def summarize_backtest(self, backtest_results: dict, symbol: str | None = None) -> str:
        llm = self.get_llm()
        if llm is None:
            return "Configure an AI provider in Settings to enable AI summaries."

        prompt = f"""Summarize this backtest.
Explain return, drawdown, win rate, and any red flags. Suggest one improvement to test next.

Symbol context: {symbol or "N/A"}

Backtest results:
{backtest_results}
"""
        messages = [
            SystemMessage(content="You are a quantitative trading analyst. Be concise and actionable."),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        return response.content


# Singleton instance
ai_assistant = AstralAIAssistant()
