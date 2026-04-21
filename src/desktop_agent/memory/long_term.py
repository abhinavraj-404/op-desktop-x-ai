"""Long-term memory backed by ChromaDB vector database.

Stores strategies, task outcomes, and knowledge with semantic search,
replacing the old flat JSON approach that could only do keyword matching.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from desktop_agent.config import get_settings
from desktop_agent.log import get_logger

log = get_logger(__name__)


class LongTermMemory:
    """Persistent memory with semantic search via ChromaDB."""

    def __init__(self) -> None:
        self._client = None
        self._strategies = None
        self._tasks = None
        self._knowledge = None

    def _ensure_db(self) -> None:
        if self._client is not None:
            return

        import chromadb

        settings = get_settings()
        db_path = Path(settings.memory.vector_db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(db_path))

        # Collections
        self._strategies = self._client.get_or_create_collection(
            name="strategies",
            metadata={"description": "Learned action strategies and their outcomes"},
        )
        self._tasks = self._client.get_or_create_collection(
            name="completed_tasks",
            metadata={"description": "History of completed tasks"},
        )
        self._knowledge = self._client.get_or_create_collection(
            name="knowledge",
            metadata={"description": "General knowledge and app-specific tips"},
        )
        log.info("vector_db_initialized", path=str(db_path))

    # ── Strategies ────────────────────────────────────────────────

    def add_strategy(
        self, task_type: str, strategy: str, *, success: bool, steps: int = 0
    ) -> None:
        self._ensure_db()
        doc_id = f"strat_{int(time.time() * 1000)}"
        self._strategies.add(
            documents=[f"{task_type}: {strategy}"],
            metadatas=[{"success": success, "steps": steps, "timestamp": time.time()}],
            ids=[doc_id],
        )

        # Trim old entries
        settings = get_settings()
        count = self._strategies.count()
        if count > settings.memory.max_long_term_strategies:
            # Remove oldest entries
            results = self._strategies.get(
                limit=count - settings.memory.max_long_term_strategies,
                include=["metadatas"],
            )
            if results["ids"]:
                self._strategies.delete(ids=results["ids"])

    def get_relevant_strategies(self, query: str, n: int = 5) -> list[dict]:
        """Semantic search for strategies relevant to a query."""
        self._ensure_db()
        if self._strategies.count() == 0:
            return []

        results = self._strategies.query(
            query_texts=[query],
            n_results=min(n, self._strategies.count()),
            include=["documents", "metadatas", "distances"],
        )

        strategies = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            strategies.append({
                "text": doc,
                "success": meta.get("success", False),
                "relevance": 1.0 - min(dist, 1.0),  # Convert distance to similarity
            })
        return strategies

    # ── Task History ──────────────────────────────────────────────

    def record_task(
        self, task: str, *, steps: int, success: bool, plan: list[str] | None = None
    ) -> None:
        self._ensure_db()
        doc_id = f"task_{int(time.time() * 1000)}"
        metadata: dict[str, Any] = {
            "steps": steps,
            "success": success,
            "timestamp": time.time(),
        }
        if plan:
            metadata["plan"] = json.dumps(plan[:15])

        self._tasks.add(
            documents=[task],
            metadatas=[metadata],
            ids=[doc_id],
        )

    def get_similar_tasks(self, query: str, n: int = 5) -> list[dict]:
        """Find past tasks similar to the given query."""
        self._ensure_db()
        if self._tasks.count() == 0:
            return []

        results = self._tasks.query(
            query_texts=[query],
            n_results=min(n, self._tasks.count()),
            include=["documents", "metadatas", "distances"],
        )

        tasks = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            tasks.append({
                "task": doc,
                "success": meta.get("success", False),
                "steps": meta.get("steps", 0),
                "relevance": 1.0 - min(dist, 1.0),
            })
        return tasks

    # ── General Knowledge ─────────────────────────────────────────

    def store_knowledge(self, topic: str, content: str) -> None:
        """Store a piece of knowledge (app tip, workflow, etc.)."""
        self._ensure_db()
        doc_id = f"know_{hash(topic) & 0xFFFFFFFF}"
        # Upsert to avoid duplicates on same topic
        self._knowledge.upsert(
            documents=[f"{topic}: {content}"],
            metadatas=[{"topic": topic, "timestamp": time.time()}],
            ids=[doc_id],
        )

    def recall_knowledge(self, query: str, n: int = 5) -> list[str]:
        """Semantic search for relevant knowledge."""
        self._ensure_db()
        if self._knowledge.count() == 0:
            return []

        results = self._knowledge.query(
            query_texts=[query],
            n_results=min(n, self._knowledge.count()),
            include=["documents"],
        )
        return results["documents"][0]

    # ── Prompt Formatting ─────────────────────────────────────────

    def format_for_prompt(self, task: str) -> str:
        """Render relevant long-term memory as text for the LLM prompt.
        
        Skips DB queries if collections are empty to avoid embedding overhead.
        """
        self._ensure_db()
        
        # Skip expensive embedding queries on empty collections
        if (self._strategies.count() == 0 
            and self._tasks.count() == 0 
            and self._knowledge.count() == 0):
            return ""
        
        parts: list[str] = []

        strategies = self.get_relevant_strategies(task, n=5)
        if strategies:
            lines = []
            for s in strategies:
                icon = "✓" if s["success"] else "✗"
                lines.append(f"  {icon} {s['text']} (relevance: {s['relevance']:.0%})")
            parts.append("## Relevant Past Strategies\n" + "\n".join(lines))

        past_tasks = self.get_similar_tasks(task, n=3)
        if past_tasks:
            lines = []
            for t in past_tasks:
                icon = "✓" if t["success"] else "✗"
                lines.append(f"  {icon} \"{t['task'][:80]}\" ({t['steps']} steps)")
            parts.append("## Similar Past Tasks\n" + "\n".join(lines))

        knowledge = self.recall_knowledge(task, n=3)
        if knowledge:
            parts.append("## Relevant Knowledge\n" + "\n".join(f"  - {k}" for k in knowledge))

        return "\n\n".join(parts) if parts else ""
