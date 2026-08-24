"""Primary method: pretrained HuggingFace sequence classifier.

Model: Hello-SimpleAI/chatgpt-detector-roberta — a RoBERTa-base fine-tuned
on the HC3 corpus (human vs ChatGPT answers to the same questions). Chosen
because (a) it is trained for exactly this binary task, (b) its training
data is public so its blind spots are documentable, and (c) RoBERTa-base is
small enough (~500 MB) to serve on CPU with acceptable latency.

Loading is lazy and failure-tolerant: if weights are absent and the machine
is offline, `available()` returns False and the registry falls back to the
statistical model without changing the API contract.
"""
import logging
import os
import threading

from .base import Detector

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get(
    "AIDETECT_HF_MODEL", "Hello-SimpleAI/chatgpt-detector-roberta"
)

# id2label values that mean "AI-generated" across common detector checkpoints
_AI_LABELS = {"chatgpt", "ai", "fake", "generated", "machine", "gpt2", "label_1"}


class HFDetector(Detector):
    name = "hf-transformer"
    version = "1.0"

    def __init__(self, model_id: str = DEFAULT_MODEL):
        self.model_name = model_id
        self._lock = threading.Lock()
        self._model = None
        self._tokenizer = None
        self._ai_index = 1
        self._load_failed = False

    def _load(self) -> bool:
        with self._lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False
            try:
                import torch  # noqa: F401
                from transformers import (AutoModelForSequenceClassification,
                                          AutoTokenizer)
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self._model = AutoModelForSequenceClassification.from_pretrained(
                    self.model_name
                )
                self._model.eval()
                id2label = getattr(self._model.config, "id2label", {}) or {}
                for idx, label in id2label.items():
                    if str(label).lower() in _AI_LABELS:
                        self._ai_index = int(idx)
                        break
                return True
            except Exception as exc:  # network down, missing weights, OOM…
                logger.warning("HF detector unavailable: %s", exc)
                self._load_failed = True
                return False

    def cached_locally(self) -> bool:
        """Cheap probe: are the weights already loaded or in the local HF
        cache? Used by /health so a status check never triggers a download."""
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        try:
            from transformers import AutoConfig
            AutoConfig.from_pretrained(self.model_name, local_files_only=True)
            return True
        except Exception:
            return False

    def available(self) -> bool:
        return self._load()

    def score_sentences(self, sentences: list[str]) -> list[float]:
        if not self._load():
            raise RuntimeError("HF model could not be loaded")
        import torch

        scores: list[float] = []
        batch_size = 16
        with torch.no_grad():
            for i in range(0, len(sentences), batch_size):
                batch = sentences[i : i + batch_size]
                enc = self._tokenizer(
                    batch, truncation=True, max_length=512,
                    padding=True, return_tensors="pt",
                )
                logits = self._model(**enc).logits
                probs = torch.softmax(logits, dim=-1)[:, self._ai_index]
                scores.extend(float(p) for p in probs)
        return scores
