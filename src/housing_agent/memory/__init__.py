"""Versioned, human-governed project memory."""

from housing_agent.memory.models import DecisionEvent, MemorySnapshot
from housing_agent.memory.store import DecisionLogStore

__all__ = [
    "DecisionEvent",
    "DecisionLogStore",
    "MemorySnapshot",
    "compile_memory",
    "memory_compiler_node",
]


def __getattr__(name: str):
    """Load compiler objects lazily to keep package initialization acyclic."""
    if name in {"compile_memory", "memory_compiler_node"}:
        from housing_agent.memory import compiler

        return getattr(compiler, name)
    raise AttributeError(name)
