"""
Conversation memory for the chatbot.

Stores the last N turns (human + AI) in RAM for the current session.
Resets when the app reloads (not persistent across restarts).
"""

from dataclasses import dataclass, field
from collections import deque


@dataclass
class ConversationMemory:
    max_turns: int = 10
    _history: deque = field(default_factory=lambda: deque(maxlen=10))

    def __post_init__(self):
        self._history = deque(maxlen=self.max_turns)

    def add_turn(self, human: str, ai: str) -> None:
        self._history.append({"human": human, "ai": ai})

    def as_context_string(self) -> str:
        """Returns the conversation history formatted as a plain-text block."""
        if not self._history:
            return ""
        lines = []
        for turn in self._history:
            lines.append(f"Human: {turn['human']}")
            lines.append(f"Assistant: {turn['ai']}")
        return "\n".join(lines)

    def clear(self) -> None:
        self._history.clear()

    @property
    def is_empty(self) -> bool:
        return len(self._history) == 0


def get_memory(max_turns: int = 10) -> ConversationMemory:
    return ConversationMemory(max_turns=max_turns)
