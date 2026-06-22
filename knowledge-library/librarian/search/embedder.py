"""The embedding seam. FakeEmbedder is deterministic and dependency-free (tests).
OllamaEmbedder talks to a local Ollama over stdlib HTTP, prepending the query
instruction for queries only (spec §6). ensure_model preflights reachability and
auto-pulls a missing model. All vectors are L2-normalized so downstream cosine is
a dot product."""
import json
import subprocess
import urllib.error
import urllib.request

import numpy as np

from librarian.search.settings import QUERY_INSTRUCTION


def _l2(vecs):
    arr = np.asarray(vecs, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms


class FakeEmbedder:
    """Deterministic test embedder: a fixed 16-dim vector per text, L2-normalized.
    is_query is accepted (interface parity) but ignored."""
    dim = 16

    def embed(self, texts, *, is_query=False):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, t in enumerate(texts):
            for i, ch in enumerate(t):
                out[r, i % self.dim] += (ord(ch) % 17) + 1
        return _l2(out)


class OllamaEmbedder:
    def __init__(self, settings):
        self.settings = settings
        self.dim = None

    def _post(self, path, payload):
        req = urllib.request.Request(
            self.settings.ollama_host + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def embed(self, texts, *, is_query=False):
        texts = list(texts)
        inputs = [QUERY_INSTRUCTION + t for t in texts] if is_query else texts
        data = self._post("/api/embed",
                          {"model": self.settings.embed_model, "input": inputs})
        vecs = _l2(data["embeddings"])
        if vecs.shape[0]:
            self.dim = int(vecs.shape[1])
        return vecs


def _list_models(settings):
    """Model names known to Ollama, plus their bare (tag-stripped) forms."""
    req = urllib.request.Request(settings.ollama_host + "/api/tags")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    names = {m["name"] for m in data.get("models", [])}
    return names | {n.split(":")[0] for n in names}


def ensure_model(settings, *, runner=subprocess.run, log=print):
    """Preflight for indexing (spec §6): confirm Ollama is up and the model is
    present, auto-pulling a missing model when auto_pull is on. Raises
    RuntimeError with remediation otherwise."""
    try:
        present = _list_models(settings)
    except (urllib.error.URLError, OSError) as e:
        raise RuntimeError(
            f"Ollama unreachable at {settings.ollama_host} ({e}). "
            f"Start it with `ollama serve`.") from e
    model = settings.embed_model
    if model in present or model.split(":")[0] in present:
        return
    if not settings.auto_pull:
        raise RuntimeError(
            f"model {model!r} not found in Ollama and auto_pull is off. "
            f"Run `ollama pull {model}`.")
    log(f"pulling {model} (first run; this downloads the model)…")
    result = runner(["ollama", "pull", model])
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(f"`ollama pull {model}` failed "
                           f"(exit {result.returncode}).")
