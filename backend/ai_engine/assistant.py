from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from database.vector_manager import VectorMemoryManager
from database.sqlite_manager import get_settings, record_chat_message, get_recent_chat_messages
from core.credential_provider import resolve_api_keys
import os


class AstralAIAssistant:
    def __init__(self):
        self.memory_manager = VectorMemoryManager()
        self.llm = None
        self.model_name = None
        self._initialized = False

    def _initialize_llm(self):
        settings = get_settings()
        provider = (settings or {}).get("ai_provider", "openai")
        defaults = {"openai": "gpt-4.1-mini", "groq": "openai/gpt-oss-20b", "ollama": ""}
        if provider not in defaults:
            raise ValueError("Unsupported AI provider")
        configured_model = (settings or {}).get("ai_model") or ""
        model_name = configured_model or (os.environ.get("OPENAI_MODEL", defaults[provider]) if provider == "openai" else defaults[provider])
        self.provider = provider
        self.model_name = model_name
        if provider == "ollama" and not model_name:
            self.llm = None
            self._initialized = True
            return

        api_key = "ollama" if provider == "ollama" else resolve_api_keys(settings).get(provider)
        if not api_key or api_key == "mock-key":
            self.llm = None
            self._initialized = True
            return

        base_urls = {"groq": "https://api.groq.com/openai/v1", "ollama": "http://127.0.0.1:11434/v1"}
        options = dict(
            temperature=0.4,
            api_key=api_key,
            model=model_name,
            request_timeout=120.0,
        )
        if provider in base_urls:
            options["base_url"] = base_urls[provider]
        self.llm = ChatOpenAI(**options)
        self._initialized = True

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

    def analyze_market_query(self, query: str, conversation_id: str) -> str:
        """Processes a market or strategy query using the LLM and persistent memory."""
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
        system_prompt = f"""You are Astral AI, a highly intelligent, human-like crypto and stock trading companion.
You help the user analyze markets, backtest quantitative strategies, and write trading code using Python and VectorBT/Pandas logic.
You should act as a collaborative partner. If the user suggests a flawed strategy, politely suggest improvements.

{context_str}
{history_str}
"""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ]

        # 3. Get response
        llm = self.get_llm()
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
        interaction_text = f"User asked: {query}\nAI Responded: {response_text}"
        import uuid
        self.memory_manager.remember_conversation(
            doc_id=str(uuid.uuid4()),
            text=interaction_text,
            metadata={"topic": "market_analysis", "type": "chat_log"}
        )

        try:
            record_chat_message(conversation_id, "user", query)
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
