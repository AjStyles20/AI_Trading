from langchain_core.messages import HumanMessage, SystemMessage

STRATEGY_SYSTEM_PROMPT = """You are Astral AI, an expert quantitative trading strategy developer.
When given a natural language request, generate a restricted Python trading strategy using the provided Pandas alias pd and NumPy alias np.
Your code should:
1. Accept a DataFrame with columns: 'open', 'high', 'low', 'close', 'volume'.
2. Return a DataFrame with an additional 'signal' column: 1 for BUY, -1 for SELL, 0 for HOLD.
3. Add a 'position_size_pct' column (0-100) and include basic risk controls when appropriate.
4. Include brief comments explaining the logic.
5. Be ready to pass to a backtesting engine.\n6. Do NOT import modules, access files/network/environment, use eval/exec/open/getattr, or use dunder attributes.\n7. Define exactly one top-level function named strategy(df).

Output ONLY the Python code. No markdown fences.
"""

class StrategyGenerator:
    def __init__(self, llm):
        self.llm = llm

    def generate(self, prompt: str) -> str:
        """Generates a Python trading strategy from a natural language prompt."""
        if not self.llm:
            raise RuntimeError("AI strategy generation requires a configured model.")
        
        messages = [
            SystemMessage(content=STRATEGY_SYSTEM_PROMPT),
            HumanMessage(content=f"Create a strategy for: {prompt}")
        ]
        response = self.llm.invoke(messages)
        return self._sanitize_code(response.content)

    def generate_from_graph(self, nodes: list, edges: list) -> str:
        """Generates a strategy from a visual node graph structure."""
        if not self.llm:
            raise RuntimeError("AI graph export requires a configured model.")
            
        flow_description = "The user has built a strategy visually with the following nodes:\n"
        for idx, node in enumerate(nodes):
            flow_description += f"- Node {idx} ({node.get('id')}): {node.get('type')}\n"
            
        flow_description += "\nConnections between logic:\n"
        for edge in edges:
            flow_description += f"- Source node {edge.get('source')} -> Target node {edge.get('target')}\n"
            
        flow_description += "\nPlease write a Pandas trading strategy that implements this exact visual flow. Return only the python code block."
        
        messages = [
            SystemMessage(content=STRATEGY_SYSTEM_PROMPT),
            HumanMessage(content=flow_description)
        ]
        response = self.llm.invoke(messages)
        return self._sanitize_code(response.content)

    def _sanitize_code(self, content: str) -> str:
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2:
                lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
            text = "\n".join(lines)
        return text.strip()
