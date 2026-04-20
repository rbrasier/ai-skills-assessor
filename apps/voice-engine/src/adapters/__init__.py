"""Adapters — concrete implementations of the domain ports.

Phase 2 wires up ``DailyVoiceTransport`` (Daily REST) and
``InMemoryPersistence`` / ``PostgresPersistence`` for the candidate
self-service flow. The LLM provider and knowledge base adapters are
still stubbed — they come online in Phase 3+.
"""

from src.adapters.daily_transport import DailyVoiceTransport
from src.adapters.in_memory_persistence import InMemoryPersistence
from src.adapters.postgres_persistence import PostgresPersistence

__all__ = [
    "DailyVoiceTransport",
    "InMemoryPersistence",
    "PostgresPersistence",
]
