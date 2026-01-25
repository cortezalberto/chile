"""
RAG Services - AI chatbot and retrieval-augmented generation.

Provides:
- RAGService: Menu chatbot with semantic search
- OllamaClient: LLM integration for embeddings and chat
"""

from .service import (
    RAGService,
    OllamaClient,
    ollama_client,
    close_ollama_client,
)

__all__ = [
    "RAGService",
    "OllamaClient",
    "ollama_client",
    "close_ollama_client",
]
