"""The swappable detector interface.

Every detection method — pretrained transformer, locally trained statistical
model, or the Stage-1 mock — implements exactly this. The API layer only
ever talks to this interface, so swapping or upgrading a model can never
change the API contract.
"""
from abc import ABC, abstractmethod


class Detector(ABC):
    #: short machine name reported in `meta.method`
    name: str = "abstract"
    #: human-readable model identifier reported in `meta.model_name`
    model_name: str = "abstract"
    version: str = "0"

    @abstractmethod
    def score_sentences(self, sentences: list[str]) -> list[float]:
        """Return P(AI-generated) in [0, 1] for each sentence, same order."""

    def available(self) -> bool:
        """Cheap availability probe used by the fallback chain."""
        return True
