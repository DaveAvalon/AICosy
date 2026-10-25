"""Optional research extension boundary; the MVP never fabricates probe data."""
from typing import Protocol


class ProbeCollector(Protocol):
    def collect(self, *, session_id: str, state_version: int, model_id: str,
                action_probabilities: dict | None = None) -> dict:
        """Return researcher-supplied measurements with provenance and availability.

        Runs in a separate researcher process. It must not mutate game state or
        treat measurements as proof of subjective emotion. No collector ships
        with this MVP; commercial API hidden activations are unavailable.
        """
        ...
