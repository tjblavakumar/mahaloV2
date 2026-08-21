"""Project-scoped conversation history manager."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

# Key for messages not associated with any project
_GLOBAL_KEY = "__global__"


class ContextManager:
    def __init__(self, max_history: int = 20):
        self.max_history: int = max_history
        # Per-project history: project_id -> deque of messages
        self._histories: Dict[str, Deque[Dict[str, object]]] = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        # Legacy single-deque for backward compat (used when no project_id)
        self._history: Deque[Dict[str, object]] = deque(maxlen=max_history)

    def _get_deque(self, project_id: Optional[str] = None) -> Deque[Dict[str, object]]:
        if project_id:
            return self._histories[project_id]
        return self._history

    def add_message(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, object]] = None,
        project_id: Optional[str] = None,
    ):
        message: Dict[str, object] = {"role": role, "content": content, "timestamp": "now"}
        if metadata:
            message["metadata"] = metadata
        self._get_deque(project_id).append(message)

    def get_conversation_history(
        self,
        last_n: Optional[int] = 10,
        project_id: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        items = list(self._get_deque(project_id))
        if last_n is not None:
            return items[-last_n:]
        return items

    def clear(self, project_id: Optional[str] = None):
        """Clear history for a specific project, or all history if project_id is None."""
        if project_id:
            self._histories.pop(project_id, None)
        else:
            self._histories.clear()
            self._history.clear()


context_manager = ContextManager()
