import os
import chromadb

DATA_DIR = os.path.join(os.environ.get("ASTRAL_DATA_DIR") or os.path.dirname(__file__), 'chroma_data')

class VectorMemoryManager:
    """Manages the AI's persistent memory using ChromaDB."""
    
    def __init__(self, client=None):
        # Initialize local persistent client (tests pass their own).
        self.client = client or chromadb.PersistentClient(path=DATA_DIR)
        
        # Collection for past conversations and decisions
        self.conversations = self.client.get_or_create_collection(
            name="conversations",
            metadata={"hnsw:space": "cosine"} # Default similarity search
        )
        
        # Collection for market context and sentiment snapshots
        self.market_memory = self.client.get_or_create_collection(
            name="market_memory",
            metadata={"hnsw:space": "cosine"}
        )

    def remember_conversation(self, doc_id: str, text: str, metadata: dict):
        """Stores a conversation or decision in long-term memory."""
        self.conversations.add(
            documents=[text],
            metadatas=[metadata],
            ids=[doc_id]
        )

    def recall_conversations(self, query: str, n_results=3):
        """Finds related past conversations based on new user prompt."""
        results = self.conversations.query(
            query_texts=[query],
            n_results=n_results
        )
        return results

    def list_memories(self, limit: int = 200) -> list[dict]:
        """Stored conversations, newest first. Older entries have no date."""
        found = self.conversations.get(include=["documents", "metadatas"])
        items = [
            {
                "id": memory_id,
                "text": text or "",
                "created_at": (metadata or {}).get("created_at"),
                "topic": (metadata or {}).get("topic"),
            }
            for memory_id, text, metadata in zip(found["ids"], found["documents"], found["metadatas"])
        ]
        items.sort(key=lambda item: item["created_at"] or "", reverse=True)
        return items[:limit]

    def count_memories(self) -> int:
        return self.conversations.count()

    def forget(self, memory_id: str) -> bool:
        """Delete one stored conversation. Returns False if it did not exist."""
        if not self.conversations.get(ids=[memory_id])["ids"]:
            return False
        self.conversations.delete(ids=[memory_id])
        return True

    def forget_all(self) -> int:
        """Delete every stored conversation; returns how many were removed."""
        ids = self.conversations.get()["ids"]
        if ids:
            self.conversations.delete(ids=ids)
        return len(ids)

if __name__ == "__main__":
    memory = VectorMemoryManager()
    print("Vector database connected to:", DATA_DIR)
    
    # Example usage
    memory.remember_conversation(
        doc_id="test_01",
        text="User likes MACD indicator for short term scalping.",
        metadata={"topic": "preferences", "timestamp": "2026-03-13"}
    )
    
    result = memory.recall_conversations("What indicators does the user prefer?")
    print("Recall result:", result)
