# Eval Coverage

Pantheon uses [skillgrade](https://github.com/mgechev/skillgrade) for automated agent evaluation. Each eval tests whether an agent fulfills its SKILL.md claims by running structured tasks inside sandboxed environments and scoring outputs with deterministic and LLM-based graders.

## Coverage

| Agent | Eval | Notes |
|-------|------|-------|
| aphrodite | yes | |
| athena | yes | |
| brigid | yes | |
| calliope | yes | |
| demeter | yes | |
| eris | yes | |
| freya | yes | |
| iris | yes | |
| kali | yes | |
| maat | yes | |
| mokosh | yes | |
| nisaba | yes | |
| nuwa | yes | |
| pele | yes | |
| saraswati | yes | |
| seshat | yes | |
| themis | yes | |
| amaterasu | **no** | Requires DirectX/HLSL toolchain not available in Docker |
| aurora | **no** | Requires Vulkan SDK and SPIR-V toolchain |
| cybele | **no** | Requires C++ compiler and build system in sandbox |
| danu | **no** | Requires C compiler and system headers in sandbox |
| frigg | **no** | Requires PowerShell runtime in Docker |
| oya | **no** | Requires CUDA toolkit and NVIDIA driver |
| vesta | **no** | Requires .NET SDK in Docker |

17 of 24 agents have eval coverage. The 7 missing agents are compiled-language or platform-specific specialists that require specialized toolchains not available in the default `python:3.12-slim` Docker base image.

## Framework Structure

```
evals/
  _template/           # Scaffold for new evals
    eval.yaml          # Task definitions and grader config
  bin/                 # Shared tooling
    claude             # Agent wrapper for skillgrade
    improve.py         # Self-improvement pipeline
    run-remaining.sh   # Batch runner
    summarize.py       # Result aggregation
  <agent>/             # Per-agent eval directory
    eval.yaml          # Task definitions, graders, thresholds
    fixtures/          # Input files for tasks
    graders/           # Deterministic grader scripts
```

### eval.yaml

Each `eval.yaml` defines:

- **skill** — path to the agent's SKILL.md directory
- **defaults** — agent runtime, provider, trial count, timeout, pass threshold
- **tasks** — list of structured tasks, each with:
  - `instruction` — what the agent should do
  - `workspace` — fixture files mapped into the sandbox
  - `graders` — scoring functions (deterministic scripts + LLM rubrics) with weights

### Graders

- **Deterministic** (`type: deterministic`) — shell scripts that check concrete outcomes (file exists, content matches, lint passes). Typically weighted 0.6-0.7.
- **LLM rubric** (`type: llm_rubric`) — qualitative assessment against a rubric. Typically weighted 0.3-0.4.

## Adding a New Eval

```bash
make eval-init SKILL=<agent-name>
```

This scaffolds `evals/<agent-name>/` from the template. Then:

1. Edit `evals/<agent-name>/eval.yaml` — design tasks that test the agent's core claims
2. Add input files to `evals/<agent-name>/fixtures/`
3. Write deterministic graders in `evals/<agent-name>/graders/`
4. Run: `make eval-skill SKILL=<agent-name>`

### Design Principles

- Tasks should test the agent's **methodology**, not just output format
- Include at least one deterministic grader for concrete verification
- LLM rubrics should assess qualitative aspects the agent's SKILL.md claims to deliver
- Keep fixture files minimal — just enough to exercise the skill
- Set thresholds realistically (default: 0.8) and adjust based on task difficulty

## Running Evals

```bash
# Run all evals
make eval

# Run a single agent's eval
make eval-skill SKILL=athena

# Preview eval configuration
make eval-preview
```

Results are written to `results/` (git-ignored).
