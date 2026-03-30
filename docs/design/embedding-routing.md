# Design: Embedding-Based Routing

**Status:** Proposal
**Author:** Pantheon review backlog (Athena + Eris)
**Date:** 2026-03-29

## Problem

`classify_agents()` in `skill.py` uses regex signal matching to route tasks to specialists:

```python
def _signal_matches(signal: str, task: str) -> bool:
    return bool(re.search(r"\b" + re.escape(signal) + r"\b", task))
```

Each skill declares `routing_signals` (keyword lists) in its SKILL.md metadata. The router counts signal matches and returns top-scored agents.

### Limitations

1. **Synonyms** — "auth middleware" won't match a signal for "security" or "authentication"
2. **Context** — "pipeline" matches mokosh (CI/CD) even when discussing data pipelines (seshat)
3. **Novel phrasing** — "make the API faster" won't match performance-related signals unless "performance" is an explicit signal
4. **Scaling** — adding new signals is manual and error-prone; overlapping signals cause incorrect routing
5. **Co-occurrence hacks** — `_CO_OCCURRENCE_BOOSTS` is a hardcoded disambiguation workaround (currently only for mokosh)

## Proposed Design

### Similarity-Based Routing

Replace keyword matching with semantic similarity between the task description and each skill's capability description.

```
score(task, skill) = cosine_similarity(embed(task), embed(skill.description + skill.signals))
```

### Embedding Model

Use a lightweight, local embedding model that runs without GPU:

| Model | Dims | Size | Speed | Quality |
|-------|------|------|-------|---------|
| `all-MiniLM-L6-v2` | 384 | 80MB | ~5ms/query | Good for short text |
| `bge-small-en-v1.5` | 384 | 130MB | ~8ms/query | Better multilingual |
| `nomic-embed-text-v1.5` | 768 | 270MB | ~12ms/query | Best quality |

Recommended: `all-MiniLM-L6-v2` — smallest footprint, fast enough for interactive routing, good quality for short task descriptions.

### Architecture

```
                    +-----------------+
   task text  --->  |  embed(task)    |
                    +-----------------+
                            |
                            v
                    +-----------------+
                    | cosine_sim(     |     +-------------------+
                    |   task_vec,     | <-- | skill_embeddings  |
                    |   skill_vecs[]  |     | (precomputed)     |
                    | )               |     +-------------------+
                    +-----------------+
                            |
                            v
                    +-----------------+
                    | ranked agents   |
                    +-----------------+
```

### Precomputed Skill Embeddings

Skill embeddings are computed once at startup (or cached to disk):

```python
class EmbeddingRouter:
    def __init__(self, skills: dict[str, Skill], model_name: str = "all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
        self._skill_texts = {
            name: f"{skill.description}. {' '.join(skill.routing_signals)}"
            for name, skill in skills.items()
        }
        self._skill_embeddings = {
            name: self._model.encode(text)
            for name, text in self._skill_texts.items()
        }
        self._cache_path = Path(".cache/skill_embeddings.npz")
        self._save_cache()

    def classify(self, task: str, top_n: int = 5) -> list[tuple[str, float]]:
        task_vec = self._model.encode(task)
        scores = {
            name: cosine_similarity(task_vec, skill_vec)
            for name, skill_vec in self._skill_embeddings.items()
        }
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return ranked[:top_n]
```

### Fallback to Signal Matching

When the embedding model is unavailable (not installed, startup failure), fall back to the current regex-based routing:

```python
def classify_agents(task, skills, top_n=5, min_confidence=0):
    try:
        router = EmbeddingRouter(skills)
        return router.classify(task, top_n)
    except ImportError:
        # sentence-transformers not installed
        return _classify_signals(task, skills, top_n, min_confidence)
```

### Hybrid Scoring

Optionally combine both approaches for higher confidence:

```python
signal_score = signal_match_count / max_possible_signals
embed_score = cosine_similarity(task_vec, skill_vec)
final_score = 0.3 * signal_score + 0.7 * embed_score
```

This preserves the value of explicit signal matches (high precision) while adding semantic understanding (high recall).

### Dependency Strategy

```toml
# pyproject.toml
[project.optional-dependencies]
embeddings = ["sentence-transformers>=3.0", "numpy>=1.26"]
```

Installation: `pip install pantheon[embeddings]`

The embedding extra is never required. Signal-based routing remains the zero-dependency default.

## Evaluation

### Routing Accuracy Test

Build a test set of (task_description, expected_agents) pairs from the existing eval suite:

```python
ROUTING_TESTS = [
    ("review this Go code for race conditions", ["brigid", "kali"]),
    ("write a GitHub Actions workflow for CI", ["mokosh"]),
    ("analyze these access logs for anomalies", ["seshat", "kali"]),
    ("make the API docs better", ["aphrodite"]),
    ("is this CUDA kernel memory-safe?", ["oya", "kali"]),
]
```

Compare signal-based vs embedding-based vs hybrid routing accuracy against these ground-truth labels.

### Expected Improvements

- **Synonym handling** — "auth" correctly routes to kali even without an explicit "auth" signal
- **Disambiguation** — "data pipeline" routes to seshat, "CI pipeline" routes to mokosh, based on semantic context
- **Novel phrasing** — "speed up the database queries" routes to seshat without needing "performance" as a signal
- **Reduced maintenance** — fewer manual signal additions needed as the embedding captures semantic meaning

## What Could Go Wrong

1. **Model download on first use** — `sentence-transformers` downloads the model on first import (~80MB). Mitigation: document this; add `pantheon doctor --check-embeddings` to pre-download.

2. **Startup latency** — loading the model takes 1-3 seconds. Mitigation: lazy initialization (load on first `classify()` call, not at import); cache embeddings to disk.

3. **Embedding drift** — if SKILL.md descriptions change, cached embeddings become stale. Mitigation: hash skill texts and invalidate cache on change.

4. **Short query ambiguity** — very short task descriptions ("fix bug") produce low-confidence embeddings. Mitigation: require minimum similarity threshold; fall back to signal matching below threshold.

5. **Torch dependency weight** — `sentence-transformers` pulls in PyTorch (~2GB). Mitigation: explore ONNX runtime alternative (`optimum` or direct `onnxruntime` inference) to avoid the PyTorch dependency. This is the biggest adoption barrier.

6. **Over-routing** — semantic similarity may surface plausible but incorrect specialists (e.g., "write a poem" routing to calliope because it handles "creative text"). Mitigation: enforce minimum confidence thresholds; keep negative signals (explicit exclusion patterns).

## Decision

Recommended approach: implement as an optional extra (`pantheon[embeddings]`) with signal-matching fallback. Start with pure embedding scoring, then evaluate hybrid scoring if accuracy on the routing test set warrants it. Investigate ONNX runtime as a lighter alternative to full PyTorch before committing to `sentence-transformers`.
