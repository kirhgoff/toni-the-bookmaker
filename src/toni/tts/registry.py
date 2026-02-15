"""TTS engine registry and factory functions."""

from typing import Type

from toni.tts.base import TTSEngine

_ENGINES: dict[str, Type[TTSEngine]] = {}


def register_engine(name: str) -> callable:
    """Decorator to register a TTS engine."""

    def decorator(cls: Type[TTSEngine]) -> Type[TTSEngine]:
        _ENGINES[name] = cls
        return cls

    return decorator


def get_engine(name: str) -> TTSEngine:
    """Get an instance of a TTS engine by name.

    Args:
        name: The engine name (e.g., 'pocket', 'kani').

    Returns:
        An instance of the requested TTS engine.

    Raises:
        ValueError: If the engine is not found or dependencies are missing.
    """
    if name == "pocket":
        from toni.tts.pocket import PocketTTSEngine

        return PocketTTSEngine()
    elif name == "kani":
        from toni.tts.kani import KaniTTSEngine

        return KaniTTSEngine()
    else:
        available = list_engines()
        raise ValueError(
            f"Unknown TTS engine: '{name}'. Available engines: {available}"
        )


def list_engines() -> list[str]:
    """List all available TTS engine names."""
    return ["pocket", "kani"]
