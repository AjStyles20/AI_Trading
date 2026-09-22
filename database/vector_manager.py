import os
import chromadb

DATA_DIR = os.path.join(os.path.dirname(__file__), 'chroma_data')

class VectorMemoryManager:
    """Manages the AI's persistent memory using ChromaDB."""
    
    def __init__(self):
        # Initialize local persistent client
        self.client = chromadb.PersistentClient(path=DATA_DIR)
        
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
