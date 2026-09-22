from langchain_core.messages import HumanMessage, SystemMessage
# Can swap this with ChatOllama for local LLMs or ChatOpenAI for OpenAI
from langchain_openai import ChatOpenAI
from database.vector_manager import VectorMemoryManager
from database.sqlite_manager import get_settings, record_chat_message, get_recent_chat_messages
import os


class AstralAIAssistant:
    def __init__(self):
        self.memory_manager = VectorMemoryManager()
        self.llm = None
        self.model_name = None
        self._initialize_llm()

    def _initialize_llm(self):
        settings = get_settings()
        api_key = settings.get("api_keys", {}).get("openai") if settings else None
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

        # Fallback to env var if in dev mode
        if not api_key or api_key == "mock-key":
            api_key = os.environ.get("OPENAI_API_KEY", "mock-key")

        if not api_key or api_key == "mock-key":
            self.llm = None
            self.model_name = model_name
            return

        self.model_name = model_name
        self.llm = ChatOpenAI(
            temperature=0.4,
            api_key=api_key,
            model=model_name,
            request_timeout=60.0 # Prevent infinite hanging
        )

    def reload_settings(self):
        """Forces a refresh of the LLM configuration."""
        print("DEBUG: Reloading AI settings...")
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
        if self.llm is None:
            return "Please provide a valid OpenAI API Key in the Settings menu (Settings icon) to start using the full intelligence of Astral AI."

        try:
            print("DEBUG: Starting LLM generation...")
            response = self.llm.invoke(messages)
            response_text = response.content
            print(f"DEBUG: LLM generation finished in {time.time() - gen_start:.2f}s")
        except Exception as e:
            err_msg = str(e)
            print(f"CRITICAL: LLM generation failed: {err_msg}")
            if "401" in err_msg or "invalid_api_key" in err_msg:
                return "Error: Invalid API Key. Please check your OpenAI key in settings."
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
        if self.llm is None:
            return "Add your OpenAI API key in Settings to enable AI summaries."

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
        response = self.llm.invoke(messages)
        return response.content

    def summarize_backtest(self, backtest_results: dict, symbol: str | None = None) -> str:
        if self.llm is None:
            return "Add your OpenAI API key in Settings to enable AI summaries."

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
        response = self.llm.invoke(messages)
        return response.content


# Singleton instance
ai_assistant = AstralAIAssistant()
