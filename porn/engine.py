"""Version dispatch: preserved recordings keep their original deterministic rules."""
from . import legacy_engine
from .errors import GameError

DEFAULT_VERSION = 4
SUPPORTED_VERSIONS = (1, 2, 3, 4)


def _implementation(state):
    version = state.get("engine_version", 1)
    if version == 1:
        return legacy_engine
    if version == 2:
        from . import engine_v2
        return engine_v2
    if version == 3:
        from . import engine_v3
        return engine_v3
    if version == 4:
        from . import engine_v4
        return engine_v4
    raise GameError("UNSUPPORTED_ENGINE_VERSION", "Unknown stored rules version", status=409)


def create_state(*, engine_version=DEFAULT_VERSION, **kwargs):
    if type(engine_version) is not int or engine_version not in (2, 3, 4):
        raise GameError("INVALID_ENGINE_VERSION", "New sessions support engine_version 2, 3 or 4")
    return _implementation({"engine_version": engine_version}).create_state(**kwargs)


def observe(state):
    return _implementation(state).observe(state)


def transition(state, action):
    return _implementation(state).transition(state, action)


def available_actions(state):
    return _implementation(state).available_actions(state)


def rules(engine_version=DEFAULT_VERSION):
    if type(engine_version) is not int or engine_version not in SUPPORTED_VERSIONS:
        raise GameError("INVALID_ENGINE_VERSION", "Unknown rules version")
    return _implementation({"engine_version": engine_version}).rules()


def export_library(state):
    implementation = _implementation(state)
    return implementation.export_library(state) if hasattr(implementation, "export_library") else []


def rules_for_state(state):
    return _implementation(state).rules()
