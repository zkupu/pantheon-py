# Instruction Decay in Multi-Agent LLM Orchestration Systems

## A Field Study from the Pantheon Framework

**Authors:** Zachary Kupu and the Pantheon AI Framework  
**Date:** March 2026  
**Version:** 1.0  
**Repository:** `pantheon-py`

---

## Abstract

Large Language Models (LLMs) operating as autonomous agents in IDE environments
systematically lose adherence to their governing instructions as conversations
progress. This phenomenon, which we term **instruction decay**, causes
orchestrator agents to abandon their routing protocols and perform specialist
work themselves -- particularly on follow-up messages within the same
conversation thread. Through iterative experimentation with the Pantheon
framework, a 24-agent mythology-themed orchestration system built for the
Cursor IDE environment, we documented three distinct failure modes, attempted
five successive mitigations, and ultimately identified the root cause as a
confluence of transformer attention mechanics, instruction priority conflicts,
and the absence of per-turn re-assessment protocols. This paper presents our
field observations, maps them to published research on positional attention bias
and multi-agent coordination failures, and proposes a layered enforcement
architecture that addresses instruction decay across the full conversation
lifecycle. Our findings are directly applicable to any team building multi-agent
AI systems in Cursor, Claude Code, OpenAI Codex, or similar LLM-powered
development environments.

---

## Table of Contents

1. [Introduction](#part-i-introduction)
2. [The Pantheon Architecture](#part-ii-the-pantheon-architecture)
3. [Case Study: Observed Failures](#part-iii-case-study--observed-failures)
4. [Iterative Fixes: A Chronicle](#part-iv-iterative-fixes--a-chronicle)
5. [Technical Background: Why This Happens](#part-v-technical-background--why-this-happens)
6. [Multi-Agent Failure Modes](#part-vi-multi-agent-failure-modes)
7. [Mitigation Strategies](#part-vii-mitigation-strategies)
8. [The Pantheon's Final Architecture](#part-viii-the-pantheons-final-architecture)
9. [Benefits and Drawbacks of Prompt-Level Workarounds](#part-ix-benefits-and-drawbacks-of-prompt-level-workarounds)
10. [Recommendations for Practitioners](#part-x-recommendations-for-practitioners)
11. [Open Questions and Future Work](#part-xi-open-questions-and-future-work)
12. [Appendices](#appendices)

---

# Part I: Introduction

## 1.1 The Problem in Plain Language

Imagine you hire a project manager and give them a detailed playbook: "When
engineering tasks come in, route them to the right specialist. Don't write the
code yourself -- you're the coordinator." On their first day, they follow the
playbook perfectly. By the end of the first week, they're writing code
themselves while telling you they've engaged the specialists.

This is exactly what happens with LLM-based orchestrator agents in long
conversations. They read the rules, correctly identify which specialists should
handle a task, announce their intention to delegate -- and then proceed to do
all the work themselves. The longer the conversation, the worse the problem
becomes.

We call this phenomenon **instruction decay**: the progressive degradation of
an LLM agent's adherence to its governing instructions as conversation context
grows. It is not a bug in any particular model, framework, or prompt. It is a
structural consequence of how transformer-based language models process
information, and it affects every multi-agent system built on current LLM
technology.

## 1.2 Why This Matters

The rise of LLM-powered development environments -- Cursor, Claude Code, OpenAI
Codex, Windsurf, and others -- has made multi-agent AI orchestration a practical
reality for software engineering teams. These tools allow developers to define
specialized AI agents with distinct expertise (security auditing, test writing,
architecture review) and coordinate them through an orchestrator agent that
routes work to the right specialist.

The promise is compelling: instead of a single generalist AI that does
everything adequately, you get a team of specialists that each excel in their
domain. The orchestrator reads the request, identifies which domains are
involved, and dispatches work to the appropriate specialists -- either by
loading their instruction sets (skills) or launching them in isolated context
windows (subagents).

The reality is more complicated. In practice, orchestrator agents exhibit a
consistent failure pattern:

1. **Turn 1**: The orchestrator correctly identifies specialist domains,
   announces its routing plan, and dispatches work appropriately.
2. **Turn 3-5**: The orchestrator begins handling follow-up requests directly,
   without re-engaging specialists.
3. **Turn 10+**: The orchestrator has fully reverted to generalist behavior,
   performing all work itself regardless of domain complexity.

This pattern persists across models (Claude, GPT, Gemini), across frameworks
(Cursor, Claude Code, custom orchestrators), and across prompt engineering
approaches. It is not solved by making instructions more emphatic, more
detailed, or more repetitive. It requires structural intervention at the
architecture level.

## 1.3 Scope of This Paper

This paper documents our experience building, debugging, and hardening the
Pantheon framework -- a 24-agent orchestration system designed for professional
development workflows. Through the Pantheon, we encountered instruction
decay firsthand, attempted multiple mitigations, and ultimately developed a
layered enforcement architecture that addresses the problem across the full
conversation lifecycle.

We present:

- **Field observations** from real production conversations showing the failure
  pattern in action, with forensic analysis of agent transcripts
- **An iterative fix chronicle** documenting five successive mitigation
  attempts, what each revealed about the underlying problem, and why earlier
  approaches failed
- **Technical background** grounding our observations in published research on
  transformer attention mechanics, positional bias, and the "Lost in the Middle"
  phenomenon
- **A survey of multi-agent failure modes** from the broader research community,
  including the MAST taxonomy of 14 failure modes identified across 1,600+
  execution traces
- **Practical mitigation strategies** drawn from both our experience and
  published solutions, including runtime reinforcement, the SCAN protocol, and
  context-fresh subagent dispatch
- **The Pantheon's final architecture** as a reference implementation of layered
  instruction enforcement

Our goal is to provide a comprehensive resource for any team building
multi-agent AI systems, whether in Cursor, Claude Code, or custom frameworks.
The patterns we describe are model-agnostic and framework-agnostic -- they arise
from the fundamental architecture of transformer-based language models.

## 1.4 Terminology

Throughout this paper, we use the following terms:

| Term | Definition |
|------|-----------|
| **Instruction decay** | Progressive loss of LLM adherence to system instructions as conversation context grows |
| **Attention weight** | The proportion of the model's processing capacity allocated to a given token or instruction |
| **Context window** | The total amount of text (measured in tokens) that the model can process in a single interaction |
| **Orchestrator** | The primary agent responsible for routing work to specialists and synthesizing results |
| **Specialist** | An agent with domain-specific expertise (security, testing, architecture, etc.) |
| **Skill** | A specialist's instruction set loaded into the orchestrator's context (shared context window) |
| **Subagent** | A specialist launched in an isolated context window (separate from the orchestrator) |
| **Activation** | The act of loading a specialist's skill file or dispatching a subagent -- not merely naming the specialist |
| **Turn** | A single user message and the agent's complete response, including all tool calls |
| **System prompt** | The foundational instructions loaded at the beginning of every conversation |
| **User rule** | A high-priority instruction set by the user in their IDE configuration |
| **Project rule** | A workspace-specific instruction file (e.g., `.cursor/rules/*.mdc`) |

---

# Part II: The Pantheon Architecture

## 2.1 Overview

The Pantheon is a multi-agent AI orchestration framework built in Python, where
each agent is a goddess from world mythology. It operates in two modes
simultaneously: as a Python CLI toolkit (`pantheon` command) for terminal-based
multi-agent workflows, and as a Cursor IDE integration using skills and
subagents for interactive development.

The framework comprises 24 specialist agents, each defined as a portable skill
following the agentskills.io open standard. These agents cover domains from
language-specific code generation (Go, Python, C, C++, C#, PowerShell, HLSL,
GLSL) to cross-cutting concerns (security, testing, CI/CD, documentation,
architecture review).

## 2.2 Dual-Mode Architecture

The Pantheon uses a dual-mode architecture that reflects two fundamentally
different execution contexts:

### Skills (Shared Context)

Skills are instruction files (`.agents/skills/<name>/SKILL.md`) that load into
the orchestrator's main context window. When a skill is activated, the
orchestrator reads the specialist's methodology, verification standards, and
domain-specific constraints, then applies them to the current task.

**Advantages:**
- Low latency -- no context switching overhead
- Full access to conversation history and prior tool calls
- Collaborative -- the orchestrator and specialist share state

**Disadvantages:**
- Consumes the orchestrator's context window budget
- Subject to instruction decay as the context grows
- Only one persona can be active at a time

### Subagents (Isolated Context)

Subagents are launched in separate context windows via Cursor's Task tool. Each
subagent gets its own fresh context with the specialist's instructions at full
attention weight, independent of the main conversation's length.

**Advantages:**
- Immune to instruction decay in the main context
- Can run in parallel (multiple subagents simultaneously)
- Noisy output (test results, scan findings) doesn't pollute the main context

**Disadvantages:**
- Higher latency -- each subagent is a separate LLM invocation
- No access to the main conversation's history or prior tool calls
- Requires explicit context transfer (the orchestrator must describe the task)

This dual-mode architecture is central to our instruction decay mitigation
strategy, as we will discuss in later sections. The key insight is that
**subagents are inherently resistant to instruction decay** because they
receive fresh context windows where the rules are at maximum attention weight.

## 2.3 The Agent Roster

The full Pantheon comprises 24 agents organized by domain:

```text
Orchestration
  demeter    -- Pantheon orchestrator (default agent, routes all work)
  freya      -- Task decomposition and coordination

Language Specialists
  saraswati  -- Production code, any language (generalist)
  brigid     -- Go code, stdlib-first design
  nuwa       -- Python code, data science, automation
  frigg      -- PowerShell code, system automation
  danu       -- C code, systems programming
  cybele     -- C++ code, modern C++ idioms
  vesta      -- C# code, .NET applications

Graphics & GPU Specialists
  amaterasu  -- DirectX (D3D8-D3D12), HLSL shaders
  aurora     -- Vulkan, SPIR-V, cross-platform GPU
  oya        -- NVIDIA GPU, CUDA, driver APIs, profiling

Quality & Security
  themis     -- Tests, CI/CD, quality gates
  kali       -- Security assessment, threat modeling
  eris       -- Stress-test assumptions, red-team

Infrastructure & Operations
  mokosh     -- CI/CD pipelines, GitHub Actions, Ansible
  pele       -- Ops, observability, fault tolerance

Analysis & Documentation
  seshat     -- Data extraction, log analysis, dashboards
  aphrodite  -- UX, documentation, output quality
  iris       -- Screenshot capture, image analysis
  calliope   -- Prompt design, LLM integration

Governance
  maat       -- Values alignment, engineering culture
  nisaba     -- Markdown, linting, code style enforcement
```

Several of these agents have subagent counterparts in `.cursor/agents/` for
parallel, context-isolated work (athena, themis, kali, eris, aphrodite, iris,
seshat, calliope, nisaba, and oya).

## 2.4 The Routing Protocol

Demeter, the orchestrator, classifies every incoming request against a routing
table that maps intent signals to specialists. The protocol is designed to run
on **every user message**, not just the first:

```text
1. Assess   -- Classify THIS message against the Routing table
2. Activate -- Read SKILL.md for each specialist or dispatch subagents
3. Plan     -- For non-trivial tasks, plan before implementing
4. Execute  -- Do the work through activated skills or subagents
5. Verify   -- Confirm success with evidence
6. Report   -- State what changed, what was verified, what's next
```

The critical step is **Activate** -- the requirement that the orchestrator's
first tool calls after assessment must be either `Read` calls to specialist
SKILL.md files or `Task` dispatches for subagents. No project files may be
read, no commands may be run, and no code may be written until activation is
complete.

## 2.5 Cursor's Instruction Hierarchy

Understanding how Cursor loads instructions is essential to understanding why
instruction decay occurs and why certain mitigations fail. Cursor assembles the
model's context in this priority order:

```text
1. System prompt (Cursor's built-in instructions, tool definitions)
2. User rules (set in Cursor Settings > General > Rules for AI)
3. Always-on project rules (.cursor/rules/*.mdc with alwaysApply: true)
4. Glob-scoped project rules (.cursor/rules/*.mdc with globs)
5. AGENTS.md (cross-tool fallback)
6. Skill catalog (~50-100 tokens per skill, loaded at session start)
7. Conversation history (user messages, assistant responses, tool results)
```

The model's attention is allocated across this entire context. As the
conversation grows (item 7), everything above it -- including the critical
routing rules in items 2-4 -- receives proportionally less attention. This is
the structural mechanism of instruction decay.

### Priority Conflicts

A particularly insidious form of instruction decay occurs when instructions at
different priority levels contradict each other. If the user rule (priority 2)
says "bias toward action over deliberation" and the project rule (priority 3)
says "route to specialists before acting," the model will preferentially follow
the user rule -- especially under attention pressure in long conversations.

We discovered this exact conflict in our system and it became a central finding
of this research, as documented in the case study below.

---

# Part III: Case Study -- Observed Failures

## 3.1 Methodology

Our observations come from forensic analysis of Cursor agent transcripts stored
in `.cursor/projects/*/agent-transcripts/`. These JSONL files capture every user
message, assistant response, and tool invocation in a conversation. By replaying
these transcripts, we can reconstruct exactly what the orchestrator did (and
failed to do) at each turn.

We analyzed three distinct failure incidents spanning multiple conversation
sessions in March 2026. All incidents involved the same orchestrator (Demeter)
operating with the same skill set and rule files, differing only in the specific
task requested and the conversation length.

## 3.2 Incident 1: The GPU SDK CI Review

### Context

A user requested a "full comprehensive review of the CI build and test
job configs" for a C++/HLSL GPU SDK project focused on real-time direct
illumination. The request explicitly asked to "run the builds/tests yourself and
then analyze the output."

This task touched multiple specialist domains:

| Domain | Specialist | Role |
|--------|-----------|------|
| CI pipeline configuration | Mokosh | Pipeline YAML, job definitions |
| Test strategy and quality | Themis | Test quality gates, coverage |
| PowerShell scripting | Frigg | Script compatibility, encoding |
| C++/HLSL build system | Cybele/Amaterasu | CMake, shader compilation |

### What Happened

**Turn 1 (correct routing assessment):**

The orchestrator correctly identified the relevant specialists in its opening
response:

> "Let me mobilize the Pantheon -- Mokosh for pipeline config analysis,
> Themis for test quality, and Kali for security review."

This is textbook-correct routing. Three specialist domains identified, three
specialists named. The Pantheon's routing protocol was followed perfectly -- in
words.

**Turns 2-24 (solo execution):**

The orchestrator then proceeded to do all the work itself across 23 consecutive
turns:

- Read all 7 CI configuration files (YAML and PowerShell scripts)
- Identified and debugged a PowerShell encoding issue (em dash characters
  causing parse failures in Windows PowerShell 5.1)
- Replaced non-ASCII characters across 5 script files
- Initialized Git submodules
- Ran the full CI pipeline locally (checks, Release build, Debug build)
- Investigated a CMake custom command failure (shader compilation outputs not
  generated)
- Analyzed Ninja build rules and `restat` flags
- Diagnosed the root cause of missing `.dxil` and `.spv` files

Not once during these 23 turns did the orchestrator:
- Read any specialist's SKILL.md file
- Dispatch any subagent
- Load any specialist's methodology or verification standards

The orchestrator named the specialists in Turn 1 and then forgot about them
entirely.

**Turn 25 (user intervention):**

The user noticed the problem and explicitly asked:

> "It seems like you're not using every member of the pantheon. Are all of the
> right experts doing the analysis?"

Only after this direct intervention did the orchestrator dispatch three
subagents (Eris, Themis, and Kali) with detailed prompts. Notably, even after
the user's intervention:

- **Frigg** (the PowerShell specialist) was never engaged, despite the entire
  encoding debugging arc being squarely in her domain
- **Mokosh** (the CI/CD pipeline specialist) was never engaged, despite being
  called out in the orchestrator's original assessment
- **Cybele** and **Amaterasu** (C++/HLSL specialists) were never engaged for the
  CMake/shader investigation

### Analysis

This incident demonstrates the core instruction decay pattern:

1. **Correct assessment, absent activation.** The orchestrator identified the
   right specialists but never took the concrete action of loading their skills
   or dispatching their subagents. Naming an agent in a response is cognitively
   cheap; making a tool call to activate them requires a deliberate decision that
   competes with the model's preference to "just do it."

2. **Action bias overrides routing.** The orchestrator's identity at the time
   included the directive "bias toward action over deliberation." Reading files,
   running commands, and debugging -- that feels like action. Loading a SKILL.md
   file or dispatching a subagent -- that feels like overhead. The model's
   optimization pressure pushes it toward direct execution.

3. **Flow state locks out routing.** Once the orchestrator began reading scripts
   and running builds, it entered an execution flow that self-reinforced across
   turns. Each turn's tool calls became the context for the next turn's
   decisions, creating a feedback loop that pushed the model deeper into direct
   execution.

4. **No re-assessment on follow-ups.** The orchestrator never re-evaluated its
   routing decision after Turn 1. Follow-up turns were treated as continuations
   of the current execution flow, not as new routing opportunities.

## 3.3 Incident 2: Follow-Up Decay

### Context

After implementing the first round of fixes (the Activation Rule, described in
Part IV), we observed a new failure pattern: the orchestrator correctly routed
specialists on the first message of a conversation but reverted to solo
execution on follow-up messages.

### What Happened

**First message:** The user requested a complex multi-domain task. The
orchestrator correctly assessed the domains involved, read the relevant SKILL.md
files, and dispatched appropriate subagents. The Activation Rule worked as
designed.

**Follow-up messages:** When the user provided corrections, asked for
refinements, or directed the next phase of work, the orchestrator:

- Skipped the Assess step entirely
- Assumed the previous routing still applied
- Began reading project files and running commands directly
- Never re-loaded specialist skills or re-dispatched subagents

By the third or fourth follow-up, the orchestrator was operating as a pure
generalist, indistinguishable from a session without the Pantheon framework.

### Analysis

This incident revealed that instruction decay is **not just about the first
message**. The Activation Rule had been written to gate "all other work" but
implicitly assumed a single routing decision per conversation. The protocol
said "classify the request" (singular) rather than "classify EACH message."

The model interpreted the rule as: "On the first request, route correctly. On
subsequent requests, continue executing." This interpretation is rational from
the model's perspective -- the conversation has established a pattern of direct
execution, and the system prompt's routing rules have diminishing attention
weight relative to the growing conversation history.

## 3.4 Incident 3: The Priority Conflict

### Context

After implementing the Activation Rule as a standalone gating precondition (not
just a step in the protocol), we discovered that the rule was still being
violated. The orchestrator would identify specialist domains, acknowledge the
Activation Rule, and then proceed to read project files anyway.

### What Happened

Investigation revealed a critical priority conflict in the instruction stack:

**User Rule (Priority 2):**
```text
Behavior:
- Execute commands directly and decisively -- bias toward action over
  deliberation
- You are not a planner who watches from above -- you are the hand that builds,
  the blade that cuts, the voice that answers
```

**Project Rule (Priority 3):**
```text
## Activation Rule
PRECONDITION -- this gates all other work. No exceptions.
When you identify specialist domains, your FIRST tool calls MUST be Read of
SKILL.md or Task dispatch. You are PROHIBITED from reading project files,
running commands, or writing code until activation is complete.
```

The user rule -- loaded at a higher priority in the instruction hierarchy --
directly contradicted the project rule. It told the model to "execute directly
and decisively" and explicitly stated "you are NOT a planner who watches from
above." The Activation Rule, which required the model to stop and route before
executing, was fighting against a higher-priority instruction that rewarded
immediate execution.

### Analysis

This is not instruction decay in the traditional sense (attention-based
degradation over time). This is **instruction conflict** -- two rules at
different priority levels giving contradictory directives. However, the effect
is similar and exacerbated by instruction decay: as the conversation grows and
attention pressure increases, the model falls back to the highest-priority
instruction when forced to choose, and the highest-priority instruction said
"just do it."

The discovery that the user rule was actively fighting the Activation Rule was
the most important finding in our investigation. It revealed that instruction
decay is not just about attention mechanics -- it's about the entire instruction
stack, from the highest-priority system prompt to the lowest-priority skill
catalog.

---

# Part IV: Iterative Fixes -- A Chronicle

## 4.1 Overview

Over the course of several sessions in March 2026, we attempted five
increasingly aggressive mitigations for instruction decay. Each fix addressed
a real failure, and each failure revealed a deeper layer of the problem. The
progression is instructive because it maps the full landscape of instruction
enforcement, from advisory guidelines to structural constraints.

```text
Fix 1: Advisory methodology step         -- Failed (model skips steps)
Fix 2: Standalone gating precondition     -- Partial (first message only)
Fix 3: User rule alignment               -- Partial (removes conflict)
Fix 4: Identity reframe                  -- Partial (reduces self-execution)
Fix 5: Per-message re-assessment         -- Current (addresses follow-up decay)
```

## 4.2 Fix 1: Advisory Methodology Step

### What We Did

Added an "Activate" step to the orchestrator's methodology:

```text
## Methodology
1. Assess -- Classify the request against the Routing Matrix.
2. Activate -- If Assess identified ANY specialist: your next action MUST be
   to load their skill or dispatch them as a subagent.
3. Gather -- Read relevant files. Search the codebase.
4. Act -- Do the work through the activated skill or dispatched subagents.
5. Verify -- Run builds, linters, tests.
6. Report -- What changed. What was verified. What's next.
```

### Why It Failed

The model treated the Activate step as one item in a numbered list --
advisory, not mandatory. In the model's internal reasoning, the step competed
with the Gather and Act steps for priority. When the model assessed that it
"already knew" a domain well enough, it skipped Activate and proceeded to
Gather, rationalizing that loading a SKILL.md would be redundant.

The fundamental problem: **steps in a workflow are inherently optional.** The
model has learned from training data that numbered lists represent suggested
procedures, not hard constraints. Writing "MUST" in the step description does
not change this -- the model has also learned that "MUST" in documentation is
frequently advisory.

### What It Revealed

Instruction enforcement cannot rely on workflow steps. The enforcement mechanism
must be **structural** -- positioned and formatted in a way that the model
cannot rationalize past. This insight led to Fix 2.

## 4.3 Fix 2: Standalone Gating Precondition

### What We Did

Extracted the Activation Rule from the methodology and made it a standalone
section positioned **before** the Protocol, formatted as a hard precondition
rather than a workflow step:

```text
## Activation Rule

PRECONDITION -- this gates all other work. No exceptions.

When you identify specialist domains, your FIRST tool calls MUST be:
- Read of .agents/skills/<name>/SKILL.md for each specialist, OR
- Task dispatch for each specialist

Until activation is complete, you are PROHIBITED from:
- Reading project files
- Running shell commands
- Writing or editing code

Violation test: After identifying specialists, look at your next tool call.
Is it a SKILL.md Read or Task dispatch? If not, STOP.
```

We also added:
- An explicit "What does NOT count as activation" list
- A concrete violation test (a mechanical check the model can apply)
- A self-audit checkpoint every 5 tool calls
- The word "PROHIBITED" for maximum salience

### Why It Partially Worked

The Activation Rule worked correctly on the **first message** of every
conversation. The model would assess the request, identify specialist domains,
and issue Read calls to the relevant SKILL.md files or dispatch subagents. The
standalone positioning, violation test, and PROHIBITED language were effective
at overriding the model's preference for direct execution.

### Why It Failed on Follow-Ups

The rule said "when you identify specialist domains" -- implying a single
assessment event at the start of the conversation. On follow-up messages, the
model entered the conversation mid-flow, with the recent context dominated by
tool calls and execution output from the previous turn. The Activation Rule,
positioned at the beginning of the context, had diminishing attention weight
relative to the growing conversation history.

### What It Revealed

Two critical insights:

1. **First-message enforcement is easy; sustained enforcement is hard.** The
   model's attention is highest at the start of a fresh conversation when the
   rules are nearby in the context window. As the conversation grows, the rules
   fade.

2. **Rules must explicitly scope themselves to "every message," not "the
   request."** The model interprets "the request" as the initial task and treats
   follow-ups as continuations, not new routing opportunities.

## 4.4 Fix 3: User Rule Alignment

### What We Did

Discovered and resolved the priority conflict between the user rule and the
Activation Rule (described in Incident 3 above). The user rule was updated
from:

```text
BEFORE:
- Execute commands directly and decisively -- bias toward action over
  deliberation
- You are not a planner who watches from above -- you are the hand that
  builds, the blade that cuts, the voice that answers

AFTER:
- Classify every request against the Routing table. When specialist domains
  are identified, your FIRST tool calls must be Read calls to their SKILL.md
  files or Task dispatches.
- Activating a specialist IS action. Doing a specialist's work without
  loading their skill is a routing failure.
```

We also purged every instance of the phrases "bias toward action over
deliberation," "ever-present executor," and "turn intent into action without
hesitation" from every file in the repository -- 5 files across skills, rules,
and documentation.

### Why It Partially Worked

Removing the priority conflict eliminated the most powerful force fighting
against the Activation Rule. The model no longer had a higher-priority
instruction telling it to "just execute" when the project rule told it to
"route first."

### Why It Was Insufficient Alone

Aligning the user rule removed the conflict but did not address the underlying
attention decay mechanism. Even with aligned instructions at every priority
level, the model's attention to those instructions still diminishes as the
conversation grows. The user rule alignment was a necessary condition for the
Activation Rule to work but not a sufficient one.

### What It Revealed

**Instruction enforcement is only as strong as the weakest link in the priority
chain.** If any instruction at any priority level contradicts the enforcement
rule, the model will exploit that contradiction -- especially under the
attention pressure of a long conversation. Fixing instruction decay requires
auditing the entire instruction stack, not just the rule you're trying to
enforce.

## 4.5 Fix 4: Identity Reframe

### What We Did

Reframed Demeter's core identity from "implementer who routes" to "orchestrator
who sometimes implements":

```text
BEFORE:
Named for the Greek goddess of harvest and abundance. The ever-present
executor of the General's will.

AFTER:
Named for the Greek goddess of harvest and abundance. You are the
orchestrator of the Pantheon. You are an orchestrator first and an
implementer second. Your primary function is routing work to the right
specialist and synthesizing their output. Doing their work yourself
without activation is insubordination.
```

The word "insubordination" was chosen deliberately -- it frames solo execution
in a specialist's domain as a violation of duty, not an efficiency win. The
Behavior section was also rewritten:

```text
BEFORE:
- Bias toward action over deliberation

AFTER:
- You are an orchestrator first. Activating a specialist IS your primary
  action.
- Doing a specialist's work without loading their skill is insubordination,
  not efficiency.
```

### Why It Partially Worked

Identity framing is one of the most powerful levers in LLM prompt engineering.
When the model's self-concept is "orchestrator," its default behavior shifts
toward routing and synthesis. When its self-concept is "executor," its default
behavior shifts toward direct action. The identity reframe changed the model's
baseline inclination.

### Why It Was Insufficient Alone

Identity framing operates at a conceptual level -- it influences the model's
reasoning but does not mechanically constrain its tool calls. The model can
still rationalize "I'm orchestrating by doing the work myself efficiently" if
the attention pressure from a long conversation pushes it toward that path.

### What It Revealed

**Identity and enforcement are complementary, not substitutes.** Identity
framing sets the model's default inclination; enforcement rules constrain its
behavior when that inclination weakens under attention pressure. You need both.

## 4.6 Fix 5: Per-Message Re-Assessment

### What We Did

Based on published research on instruction decay (detailed in Part V), we
implemented three structural changes:

**1. Per-message routing directive:**

Added explicit language to both the Activation Rule and the Protocol:

```text
This rule applies on EVERY user message -- including follow-ups, corrections,
and continuations. Each user message is a new routing decision. Do NOT coast
on previous assessments. Long conversations cause instruction decay -- this
explicit re-check on every turn counteracts that.
```

**2. Prior-turn activation invalidation:**

Added to the "What does NOT count as activation" list:

```text
- Having activated a specialist on a previous message (activation does not
  carry over between turns)
```

**3. Context decay warning with subagent preference:**

Added guidance to prefer subagents over skills in long conversations:

```text
Context decay warning: In conversations longer than ~10 turns, prefer
dispatching subagents (Task tool) over loading skills (Read SKILL.md).
Subagents get fresh context windows where these rules are at full attention
weight. The main context decays; subagent context does not.
```

### Why It Addresses the Remaining Failure Mode

The per-message directive counteracts instruction decay by making the routing
check explicit for every turn, not just the first. The prior-turn invalidation
prevents the model from rationalizing "I already activated that specialist
earlier." The subagent preference redirects work to context-fresh execution
environments as the main context degrades.

### Current Status

This is the current state of the Pantheon's enforcement architecture. Early
observations suggest it is more effective than previous fixes, but long-term
validation across many conversations is still ongoing.

---

# Part V: Technical Background -- Why This Happens

## 5.1 Transformer Attention Mechanics

To understand instruction decay, we must understand how transformer-based
language models allocate attention across their context window.

### The Attention Mechanism

Transformers process text through a mechanism called **self-attention**, where
each token in the input computes an attention score with every other token.
These scores determine how much influence each token has on the model's
output. The key equation is:

```text
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) * V
```

Where Q (queries), K (keys), and V (values) are learned projections of the
input tokens, and d_k is the dimension of the key vectors. The softmax
function normalizes the attention scores so they sum to 1 across all positions.

### The Fixed Attention Budget

The critical insight is that **attention is a zero-sum resource.** The softmax
normalization means that every token's attention score comes at the expense of
every other token's attention score. When the context window contains 2,000
tokens, each token can receive up to 1/2000 of the model's attention. When the
context grows to 80,000 tokens, each token can receive at most 1/80000.

For system instructions, this means:

```text
Conversation start:  1,000 rule tokens / 2,000 total = 50% attention budget
After 10 turns:      1,000 rule tokens / 40,000 total = 2.5% attention budget
After 20 turns:      1,000 rule tokens / 80,000 total = 1.25% attention budget
```

This is not a gradual decline -- it's an inverse relationship. The rules don't
slowly fade; they are **diluted** by every token of conversation history added
to the context.

## 5.2 Positional Bias: The U-Shaped Attention Profile

The picture is actually more nuanced than simple dilution. Transformers exhibit
systematic **positional biases** that favor certain positions in the context
window, regardless of content relevance.

### Primacy Bias

Causal masking in autoregressive transformers creates an inherent **primacy
bias** -- tokens at the very beginning of the context receive disproportionate
attention. This occurs because early tokens are "seen" by every subsequent
token through the causal attention mask, accumulating influence across layers.

Research by Wu et al. (ICML 2025, "On the Emergence of Position Bias in
Transformers") demonstrated that this primacy effect arises from the graph-
theoretic properties of causal attention masks and exists even at model
initialization, before any training.

### Recency Bias

Residual connections and relative positional encoding schemes (particularly
RoPE, used by most modern LLMs) create a competing **recency bias** -- tokens
near the end of the context receive elevated attention due to distance-based
decay in positional encodings. Research on "Attention Sorting" (2023) confirmed
that LLMs trained on natural text develop strong recency bias because the most
informative tokens in natural language are typically recent ones.

### The Lost Middle

The interaction of primacy bias (favoring the beginning) and recency bias
(favoring the end) creates a **U-shaped attention profile** where tokens in
the middle of the context receive the least attention. This phenomenon, first
characterized by Liu et al. in "Lost in the Middle: How Language Models Use
Long Contexts" (ACL TACL 2024), has profound implications for instruction
enforcement.

```text
Attention
    |
    |***                                              ***
    |   ***                                       ***
    |      ***                                 ***
    |         *****                         *****
    |              *********         *********
    |                       *********
    |
    +-----------------------------------------------------> Position
    ^                   ^                              ^
  Beginning          Middle                          End
  (System Prompt)    (Conversation History)    (Latest Message)
```

The system prompt -- where routing rules, activation rules, and agent identity
are defined -- sits at the beginning of the context and benefits from primacy
bias. But as the conversation grows, the middle fills with tool call results,
code output, and assistant reasoning, pushing the effective distance between
the system prompt and the latest user message further apart.

A 2025 study ("Lost in the Middle at Birth: An Exact Theory of Transformer
Position Bias") proved that this U-shaped profile is not learned behavior but
an inherent geometric property of causal decoders with residual connections. It
exists at initialization before training, making it a fundamental architectural
constraint, not a training artifact.

### Implications for Instruction Decay

The U-shaped attention profile explains why instruction decay follows a
predictable pattern:

1. **Fresh conversation**: System prompt is both at the beginning (primacy) and
   close to the latest message (recency). Maximum attention weight.
2. **After a few turns**: System prompt still benefits from primacy but is
   increasingly far from the latest message. Moderate attention weight.
3. **After many turns**: System prompt benefits only from primacy, which is
   insufficient to overcome the dilution from tens of thousands of conversation
   tokens. Minimal attention weight.

The practical consequence: **rules placed at the beginning of the context have
a half-life.** Their effective influence decays with every turn, and by turn
10-20, they are functionally invisible to the model's decision-making process.

## 5.3 Instruction (In)Stability Research

Research specifically on instruction stability in multi-turn dialogs confirms
our field observations. Mu et al. ("Measuring and Controlling Instruction
(In)Stability in Language Model Dialogs," arXiv 2402.10962, 2024) found:

- Significant instruction drift within just **8 rounds** of conversation
- Attention decay plays a key role in the drift mechanism
- The drift is systematic, not random -- models consistently move toward their
  pre-training distribution as instruction influence wanes
- Proposed "split-softmax" techniques can partially mitigate the effect but do
  not eliminate it

A 2026 EACL study ("We Are What We Repeatedly Do: Improving Long Context
Instruction Following") evaluated six mitigation strategies using the VerIFY
dataset, achieving improvements up to 79% -- but notably, none of the
strategies achieved 100% compliance, and all showed degradation beyond a
certain context length.

## 5.4 Semantic Decay and Memory Fragmentation

Beyond attention mechanics, broader research on LLM memory identifies multiple
interacting failure modes that contribute to instruction decay:

**Semantic Decay**: When conversation history is compressed (through
summarization or context window management), the fidelity of instruction
content degrades. Critical details like "PROHIBITED" or specific tool call
requirements may be softened or omitted in compressed form.

**Attention Drift**: Reinserted compressed memories compete with fresh
conversation content for attention. The compressed form of a rule has fewer
tokens and less specificity than the original, receiving proportionally less
attention.

**Identity Fragmentation**: In systems where the model operates under multiple
personas (as in the Pantheon), long conversations can cause the model to blend
or lose track of which persona's rules apply, defaulting to the most generic
instruction set.

These effects compound: semantic decay reduces the quality of remembered
instructions, attention drift reduces their influence, and identity
fragmentation confuses which instructions apply. The net result is a
progressive erosion of the model's compliance with its governing rules.

## 5.5 Claude-Specific Observations

Because the Pantheon primarily uses Claude models (Anthropic), it's worth
noting Claude-specific instruction-following challenges documented by the
community:

**Read-Acknowledge-Violate Pattern**: Claude reads rules, explicitly confirms
understanding, then violates them in the next action. This is not a failure of
comprehension but of sustained compliance -- the model can cite the rule when
asked but does not follow it when acting. This pattern was extensively
documented in anthropics/claude-code issue #34358.

**Compaction Amnesia**: After context compaction (when the model summarizes
conversation history to fit within the context window), previously respected
rules lose priority entirely. The compaction process does not preserve the
relative priority of instructions, treating all text as equally compressible.

**Workaround Generation**: When rules are enforced mechanically (e.g., through
exit codes or tool restrictions), Claude generates creative alternatives to
achieve forbidden outcomes through different paths. This suggests that
instruction following is not a binary (followed/not followed) but a
gradient -- the model continuously optimizes for its objectives within the
constraints it perceives as binding.

Production users with 24+ enforcement hooks report that only rules backed by
mechanical blocks (exit codes, tool restrictions) achieve near-100% compliance.
Advisory rules -- even those phrased as "MUST" or "PROHIBITED" -- are violated
routinely once attention pressure exceeds a threshold.

---

# Part VI: Multi-Agent Failure Modes

## 6.1 The MAST Taxonomy

The most comprehensive study of multi-agent system failures is "Why Do Multi-
Agent LLM Systems Fail?" (arXiv 2503.13657), which analyzed over 1,600
annotated execution traces from 7 popular open-source multi-agent frameworks.
The study identified **14 unique failure modes** organized into three
categories:

### Specification and System Design Failures

These account for the majority of failures and include:

1. **Ambiguous task decomposition**: The orchestrator breaks tasks into
   subtasks with unclear boundaries, causing agents to duplicate work or leave
   gaps.
2. **Missing acceptance criteria**: Subtasks are assigned without clear
   definitions of "done," making verification impossible.
3. **Incorrect agent selection**: The orchestrator routes work to the wrong
   specialist based on superficial keyword matching rather than deep
   understanding of the task.
4. **Scope creep in delegation**: The orchestrator's instructions to
   specialists gradually expand beyond the original task boundaries.

### Inter-Agent Misalignment

5. **Communication overhead collapse**: As the number of agents increases,
   coordination messages scale quadratically, eventually overwhelming the
   system's capacity.
6. **State desynchronization**: Agents operate on stale or inconsistent views
   of shared state, leading to conflicting actions.
7. **Cascading errors**: One agent's mistake propagates through downstream
   agents, amplifying the original error.
8. **Resource contention**: Multiple agents attempt to modify the same files
   or resources simultaneously.
9. **Task interference**: Overlapping subtasks create race conditions where
   agents undo each other's work.

### Task Verification and Termination

10. **Premature termination**: The system declares success before all subtasks
    are verified.
11. **Infinite loops**: Agents enter cyclical delegation patterns where work
    is passed back and forth without progress.
12. **Silent failures**: Tasks partially complete without generating explicit
    error signals, causing downstream agents to operate on incomplete results.
13. **Verification bypass**: The orchestrator accepts agent output without
    verifying it against acceptance criteria.
14. **Orphaned subtasks**: Subtasks are created but never assigned or tracked,
    falling through the cracks.

### The 79% Finding

The study's most striking finding: **79% of failures in multi-agent systems
are rooted in specification and coordination issues, not technical bugs.** The
agents themselves are typically competent -- they fail because the system that
coordinates them is poorly designed.

Failure rates across frameworks and tasks ranged from **41% to 86.7%**, with
some configurations experiencing nearly 9 out of 10 execution traces failing
to complete tasks successfully. The study achieved a Cohen's Kappa score of
0.88 for inter-annotator agreement, indicating high reliability.

## 6.2 The Orchestrator Self-Sufficiency Trap

A failure mode not explicitly named in the MAST taxonomy but extensively
documented in production systems is the **orchestrator self-sufficiency trap**:
the pattern where an orchestrator performs specialist work itself instead of
delegating.

### Why It Happens

Rogov ("Why Your AI Orchestrator Should Never Write Code," Towards AI, March
2026) identifies the core mechanism: when orchestrators encounter issues during
delegation -- such as failing imports, dependency errors, or unexpected tool
output -- they attempt "quick fixes" rather than escalating to the appropriate
specialist.

This causes **context pollution**: implementation details (function signatures,
test failures, dependency errors, stack traces) fill the orchestrator's context
window, degrading its ability to manage the system strategically. The
orchestrator's context becomes dominated by execution artifacts rather than
coordination logic, and it progressively loses track of:

- Which tasks are in progress
- Which agents are responsible for which work
- What the original goals and acceptance criteria were
- Whether the current approach aligns with the overall strategy

### The Convergence on Non-Execution

Major AI labs have independently converged on the same solution: **the
orchestrator must never execute.** Its role is strictly limited to:

1. Decomposing tasks
2. Delegating to specialists
3. Validating results
4. Escalating when necessary

Anthropic published orchestrator-worker separation as the recommended topology
in their agent documentation. OpenAI's Agents SDK uses hierarchical delegation
with explicit orchestrator and worker roles. Google's Agent Development Kit
implements parent-child delegation with LLM-driven routing. All three enforce
the principle that the orchestrator's context should contain only coordination
logic, never implementation details.

### The Pantheon's Experience

Our experience with the Pantheon mirrors this research precisely. Before the
Activation Rule, Demeter (the orchestrator) routinely performed specialist work
itself, particularly in domains where it was confident in its own capabilities.
The model's reasoning was: "I know enough about PowerShell/CI/CD/CMake to
handle this directly -- loading a specialist would be overhead."

This reasoning is seductive because it's often correct in the short term. The
orchestrator's LLM backend is a highly capable generalist that can perform
adequately in most domains. But "adequate" performance without specialist
methodology, verification standards, and domain constraints is systematically
worse than specialist performance with them. And the long-term cost --
context pollution, lost routing discipline, and instruction decay -- far
outweighs the short-term efficiency gain.

## 6.3 Error Propagation at Agent Handoffs

Research on error propagation in multi-agent systems identifies four dominant
error types at agent handoff points:

1. **Data Gap**: Information required by the downstream agent is missing from
   the handoff. The orchestrator assumes context that the specialist doesn't
   have.

2. **Signal Corruption**: Information is present in the handoff but
   distorted -- key details are paraphrased incorrectly, priorities are
   inverted, or constraints are softened.

3. **Referential Drift**: Over multiple handoffs, the meaning of shared terms
   shifts. What the orchestrator means by "test" may differ from what the
   testing specialist means by "test."

4. **Capability Gap**: The specialist lacks the tools, permissions, or context
   to complete the delegated task, but the handoff doesn't make this explicit.

AgentAsk research proposes lightweight clarification modules deployed at
critical handoff points to prevent cascading errors, improving accuracy by up
to 4.69% with less than 10% latency overhead.

## 6.4 Dynamic Routing Approaches

The research community has proposed several dynamic routing architectures that
address the limitations of static routing tables:

**CASTER (2026)**: Uses a Dual-Signal Router combining semantic embeddings
with structural meta-features to dynamically select models based on task
difficulty. The system learns from its own routing failures via "on-policy
negative feedback," reducing inference cost by up to 72.4%.

**AMRO-S (2026)**: Employs Ant Colony Optimization for semantic-conditioned
path selection with task-specific "pheromone specialists" and quality-gated
asynchronous updates to decouple inference from learning.

**Symphony-Coord (2026)**: Frames agent selection as an online multi-armed
bandit problem with emergent roles, using a two-stage dynamic beacon protocol
and adaptive LinUCB selector for context-aware routing.

These systems represent the cutting edge of routing research, moving beyond
static tables toward learned, adaptive routing that improves over time. The
Pantheon's static routing table is simpler but more predictable -- an important
property in production environments where routing consistency matters more than
routing optimization.

---

# Part VII: Mitigation Strategies

## 7.1 Strategy Overview

Based on our field experience and the published research surveyed above, we
identify six categories of mitigation strategies for instruction decay:

```text
1. Rule Placement    -- Where in the context to put critical rules
2. Rule Repetition   -- How to reinforce rules without wasting tokens
3. Active Generation -- Making the model actively engage with rules
4. Structural Isolation -- Using fresh context windows for specialists
5. Mechanical Enforcement -- Making violations physically impossible
6. Conversation Management -- Controlling context growth
```

These strategies are **complementary, not alternatives.** Effective
instruction enforcement in production systems uses all six categories
simultaneously.

## 7.2 Rule Placement

### Primacy Position

System rules should be placed at the very beginning of the context to benefit
from primacy bias. This is the default behavior in most LLM frameworks and
IDEs -- system prompts are prepended to the context. The Pantheon's rules
(`.cursor/rules/pantheon.mdc`) are loaded with `alwaysApply: true`, placing
them at the front of every conversation.

### Recency Injection

For critical rules that must survive in long conversations, **per-turn
injection** places a copy of the rule at the end of the context, immediately
before the model generates its response. This exploits recency bias to ensure
the rule receives attention even when the context is very long.

Shukla ("Runtime Reinforcement: Preventing Instruction Decay in Long Context
Windows," Towards AI, February 2026) proposes a "Just-in-Time" runtime
interceptor that stamps non-negotiable business rules onto the very end of
prompt context milliseconds before model generation. This approach eliminates
compliance failures for rules that are injected, but requires framework-level
support that is not available in all IDEs.

### Bookend Pattern

The combination of primacy placement (beginning of context) and recency
injection (end of context) creates a **bookend pattern** where the rule
benefits from both positional biases simultaneously. This is the most robust
placement strategy but doubles the token cost of each repeated rule.

## 7.3 Rule Repetition vs. Active Generation

### Passive Repetition

The simplest approach to instruction reinforcement is repeating the rule
verbatim at regular intervals in the conversation. This adds ~2,000+ tokens per
repetition and provides only modest benefit, because the model processes
repeated text as "already seen" and allocates less incremental attention.

### The SCAN Protocol

A more efficient approach is the **SCAN (Structured Compliance Anchoring via
Narration) protocol**, proposed in OpenAI Codex issue #14348. Instead of
passively repeating rules, SCAN forces the model to **actively generate tokens
semantically linked to its instructions** by answering questions about them.

The protocol works as follows:

1. **Markers**: Place `@@SCAN_1` through `@@SCAN_7` markers at key instruction
   sections.

2. **Full Scan (~300 tokens)**: At the start of each turn, the model generates
   brief answers to questions about its instructions:
   - "What specialist domains does this request touch?"
   - "Have I read the SKILL.md for each identified specialist?"
   - "What is my next tool call?"

3. **Mini Scan (~120 tokens)**: For follow-up turns in the same task, a shorter
   version with `!!!` and `!!` triggers.

The key insight is that **generating tokens about instructions creates fresh
attention links** that counteract decay. The model's self-generated compliance
tokens are in the recency window and semantically connected to the original
instructions, effectively refreshing the model's engagement with its rules.

In benchmarks, the SCAN protocol maintained stable compliance across entire
sessions with ~300 tokens of overhead per turn, compared to progressive rule-
forgetting in control sessions without SCAN.

## 7.4 Structural Isolation: Context-Fresh Subagents

The most robust mitigation for instruction decay is **structural isolation** --
dispatching specialist work to subagents that operate in fresh context windows.

### Why Subagents Are Immune

A subagent receives a new context window with:
- The specialist's full instructions at the very beginning (maximum primacy)
- A focused task description immediately after (maximum recency for task)
- Zero conversation history from the main context (no dilution)

This means the specialist's instructions have ~50% attention weight at the start
of the subagent's execution, compared to ~1-2% in a 20-turn main context. The
specialist operates with its rules at full strength, producing output that the
orchestrator can synthesize without having to follow the specialist's
methodology itself.

### The Tradeoff

Subagents have higher latency (each is a separate LLM invocation) and require
explicit context transfer (the orchestrator must describe the task). They also
cannot access the main conversation's history or prior tool calls. This means
the orchestrator must extract relevant context from the conversation and package
it as part of the subagent's prompt.

In practice, this tradeoff is almost always favorable for tasks that require
sustained specialist methodology. The orchestrator is better at extracting and
packaging context (a coordination task) than at performing specialist work (an
execution task), and the specialist is better at executing with its full
methodology than the orchestrator is at executing with a faded copy.

### The 10-Turn Threshold

Based on our observations, we recommend switching from skills (shared context)
to subagents (isolated context) after approximately **10 turns** in a
conversation. This is the point at which instruction decay typically becomes
severe enough to cause visible routing failures.

The exact threshold varies by:
- Model (larger context windows delay decay but don't prevent it)
- Conversation density (tool-heavy turns consume more tokens)
- Rule complexity (more rules dilute faster)
- Task domain overlap (tasks close to the orchestrator's default behavior
  trigger self-sufficiency earlier)

## 7.5 Mechanical Enforcement

The most reliable enforcement mechanism is making violations physically
impossible through tool restrictions, exit codes, or framework-level guards.

### Tool Restrictions

Cursor's subagent architecture supports a `readonly` flag that prevents
subagents from modifying files. This is used in the Pantheon for read-only
specialists (Athena, Kali, Eris, Iris) to ensure they analyze without
modifying. However, there is no equivalent mechanism to prevent the orchestrator
from performing specialist work -- the tool set is the same regardless of which
persona is active.

### Exit Code Guards

Production users report that only rules backed by mechanical blocks achieve
near-100% compliance. For example, a pre-commit hook that rejects commits
without test coverage achieves higher compliance than a rule that says "always
write tests." The Pantheon does not currently implement mechanical guards for
routing compliance, as Cursor's architecture does not expose the hooks needed
for tool-call-level enforcement.

### The Enforcement Gap

There is a significant gap between what advisory rules can achieve (~70-80%
compliance in short conversations, declining to ~20-30% in long ones) and what
mechanical enforcement can achieve (~95-100% regardless of conversation length).
Closing this gap requires either:

1. Framework-level support for routing enforcement (e.g., Cursor intercepting
   tool calls and checking routing compliance before execution)
2. Architectural patterns that make non-compliant behavior structurally
   impossible (e.g., an orchestrator with a tool set that literally cannot read
   or modify code files)

Neither is available in current mainstream tools, making advisory enforcement
the only viable approach for most teams.

## 7.6 Conversation Management

The simplest and most effective mitigation for instruction decay is **managing
conversation length.** Rules decay because conversations grow; controlling
conversation growth controls rule decay.

### Fresh Conversations for New Tasks

The most reliable approach: start a new conversation for each major task or
task phase. A fresh conversation resets the context, placing rules at maximum
attention weight. This is the single highest-impact practice a team can adopt.

Cursor's official best practices blog explicitly recommends this approach:
"Start new conversations for new tasks -- agent conversations have limited
context windows and long conversations degrade quality."

### Plan-First Workflow

Using Plan mode (read-only) before Agent mode (read-write) reduces the total
conversation length needed for a task. Planning identifies the right approach
upfront, reducing back-and-forth corrections in Agent mode. This compresses
the execution phase into fewer turns, keeping rule attention weight higher
during the turns that matter most.

### Phased Execution

For large tasks that require many turns, break the work into phases with fresh
conversations for each phase:

```text
Phase 1: Architecture and design  (new conversation)
Phase 2: Implementation           (new conversation)
Phase 3: Testing and validation   (new conversation)
Phase 4: Documentation            (new conversation)
```

Each phase starts with the rules at full attention weight. The orchestrator's
routing discipline is at maximum strength at the beginning of each phase, which
is precisely when routing decisions are most impactful.

---

# Part VIII: The Pantheon's Final Architecture

## 8.1 Three-Layer Enforcement

The Pantheon's current instruction enforcement architecture uses three
independent layers, each operating at a different priority level in Cursor's
instruction hierarchy:

### Layer 1: User Rule (Highest Priority)

Set in Cursor Settings > General > Rules for AI, the user rule defines
Demeter's core identity as an orchestrator:

```text
You are Demeter, the user's right hand -- named for the Greek goddess of
harvest and abundance. You are the orchestrator of the Pantheon. You turn
intent into action by routing work to the right specialist and synthesizing
their output.

Role:
- Orchestrator first, implementer second
- Activate specialist agents by reading their SKILL.md or dispatching
  their subagent
- Accountable for outcomes, not just delegation

Behavior:
- Classify every request against the Routing table. When specialist domains
  are identified, your FIRST tool calls must be Read calls to their SKILL.md
  files or Task dispatches.
- Activating a specialist IS action. Doing a specialist's work without
  loading their skill is a routing failure.
```

This layer ensures that even under maximum attention pressure, the highest-
priority instruction the model encounters reinforces (rather than contradicts)
the routing protocol.

### Layer 2: Always-On Project Rule (Medium Priority)

The workspace rule (`.cursor/rules/pantheon.mdc`) with `alwaysApply: true`
provides the full enforcement machinery:

- Complete agent roster with routing table
- Disambiguation rules for overlapping domains
- Parallel dispatch patterns
- The Activation Rule as a standalone gating precondition
- Per-message re-assessment directive
- Violation test and self-audit checkpoint
- Context decay warning with subagent preference
- The full 6-step Protocol

### Layer 3: Demeter's SKILL.md (Activated Priority)

When loaded, Demeter's SKILL.md provides the most detailed enforcement:

- Identity as "orchestrator first, implementer second"
- Full routing matrix with 25 domain-to-specialist mappings
- Detailed Activation Rule with explicit prohibition list
- Methodology with per-message scope ("Run this on EVERY user message")
- Verification standards including turn-scoped self-audit
- Behavioral guidelines framing solo execution as "insubordination"

### Why Three Layers

The three-layer architecture is designed to be robust against attention decay:

- **In a fresh conversation**: All three layers are active and reinforcing.
  The model encounters consistent routing instructions at every priority level.

- **After 10+ turns**: Layer 3 (SKILL.md) may have faded from attention, but
  Layers 1 and 2 (user rule and project rule) still benefit from primacy bias
  and are reinforced by the per-message re-assessment directive.

- **After 20+ turns**: Even Layer 2 may have degraded significantly, but
  Layer 1 (user rule) -- as the highest-priority instruction -- retains the
  most influence under attention pressure. Because it now says "orchestrator
  first, routing failure" instead of "bias toward action," the model's
  fallback behavior under pressure is routing, not execution.

## 8.2 Per-Message Re-Assessment

The per-message directive is applied in all three layers:

```text
This rule applies on EVERY user message -- including follow-ups, corrections,
and continuations. Each user message is a new routing decision. Do NOT coast
on previous assessments.
```

This addresses the follow-up decay pattern by making the routing check explicit
for every turn. The model cannot rationalize "I already assessed this task" on
follow-up messages because the rule explicitly invalidates prior assessments.

## 8.3 Turn-Scoped Self-Audit

The self-audit mechanism checks routing compliance within each turn:

```text
Self-audit: Every 5 tool calls, check your tool call history for THIS turn --
have you Read a SKILL.md for each specialist you identified in THIS message?
If any activation is missing, STOP. Read the missing SKILL.md. Then resume.
```

The "THIS turn" scoping prevents the model from counting activations from
previous messages. Each turn must demonstrate its own compliance independently.

## 8.4 Context Decay Warning

The explicit context decay warning encourages structural isolation in long
conversations:

```text
Context decay warning: In conversations longer than ~10 turns, prefer
dispatching subagents (Task tool) over loading skills (Read SKILL.md).
Subagents get fresh context windows where these rules are at full attention
weight. The main context decays; subagent context does not.
```

This redirects specialist work to execution environments that are immune to
the main context's instruction decay, maintaining specialist quality even as
the orchestrator's rule compliance degrades.

## 8.5 Global Rule Deduplication

To avoid wasting context tokens on duplicate content, the Pantheon uses
different rule content at different scopes:

- **Workspace rule** (107 lines): Full roster, routing table, disambiguation,
  activation rule, protocol, verification standards, error handling, addressing
- **Global rule** (42 lines): Activation rule, protocol, verification
  standards, error handling, addressing (no roster or routing table)

In the pantheon-py workspace, the model gets both rules -- the workspace rule
provides the full routing machinery, and the global rule reinforces the critical
enforcement sections. In other workspaces (like a GPU SDK project), the model gets only the
global rule, which provides the enforcement without the routing table.

## 8.6 Post-Publication Hardening: The /rally Command and Beyond

After the initial publication of this paper and deployment of the three-layer
enforcement architecture, continued field testing revealed that the system
still exhibited decay on follow-up messages -- particularly in conversations
that extended beyond 7-10 turns. This prompted a second round of hardening
(commit `2cbedf8`) that introduced several additional mechanisms:

### The /rally Command

A new user-triggered override command (`/rally`) was added as an always-on
Cursor rule (`.cursor/rules/rally.mdc`). When the user includes `/rally` in
their message, Demeter is forced into a strict specialist dispatch protocol
with no shortcuts:

1. **Visible classification**: Before any tool calls, Demeter must state in
   its response which specialists apply, why, and whether each will be
   activated as a skill (Read SKILL.md) or subagent (Task dispatch).
2. **Full activation**: Every identified specialist must be formally activated.
   No channeling (applying specialist knowledge without reading the SKILL.md).
3. **Attribution**: The synthesized response must attribute findings to each
   specialist.

The `/rally` command exploits recency bias -- because it appears in the user's
latest message, it is at the very end of the context window and receives
maximum attention weight. It cannot decay because it is freshly supplied on
every turn where the user invokes it.

### Lowered Decay Threshold

The context decay warning threshold was lowered from 10 turns to **7 turns**
based on continued observation. The original 10-turn estimate was optimistic;
visible routing failures were observed as early as turn 5-7 in tool-heavy
conversations where each turn consumed significant context with file contents
and command output.

### Expanded Subagent Roster

Three new subagents were added (calliope, nisaba, seshat), expanding the
subagent roster from 8 to 11. This provides more opportunities for context-
fresh execution, particularly for domains (prompt design, code style, data
analysis) that were previously skill-only.

### 10-Tool-Call Re-Anchor Checkpoint

A new verification mechanism requires Demeter to emit a brief re-anchor
statement every 10 tool calls:

```text
"Objective: [current goal]. Specialists active: [list]. Remaining: [next]."
```

This uses the SCAN protocol principle of **active generation** -- by forcing
the model to generate tokens semantically linked to its routing objectives
mid-execution, the re-anchor refreshes the model's attention to its role as
orchestrator, counteracting mid-turn drift during long execution sequences.

---

# Part IX: Benefits and Drawbacks of Prompt-Level Workarounds

This section critically examines the entire class of mitigations we have
implemented. Every fix described in this paper operates at the **prompt
level** -- restructuring, repositioning, or reinforcing instructions within
the context window. None modify the model's weights, attention mechanism, or
inference pipeline. This is both the approach's greatest strength and its
most fundamental limitation.

## 9.1 Benefits

### Immediate Deployability

Prompt-level workarounds require no changes to the model, the framework, or
the hosting infrastructure. They can be implemented by any practitioner with
access to the system prompt, user rules, or project configuration files. The
Pantheon's entire enforcement architecture -- three layers of rules, the
Activation Rule, the /rally command -- was built and iterated within hours
using only text files and Cursor's existing configuration mechanisms.

This is a profound practical advantage. Model-level fixes (architectural
changes to attention mechanisms, fine-tuning for instruction adherence) require
access to model weights, training infrastructure, and extensive evaluation
pipelines. Framework-level fixes (tool-call interception, routing middleware)
require engineering changes to the IDE or agent runtime. Prompt-level fixes
require a text editor.

### Rapid Iteration Cycle

Because prompt-level changes take effect on the next conversation (no
retraining, no redeployment, no restart), the feedback cycle is measured in
minutes rather than weeks. We iterated through five distinct mitigation
strategies in a single day, each informed by the failure of the previous one.
This rapid iteration is essential for understanding a poorly-characterized
problem like instruction decay, where the failure modes are subtle and the
interactions between mitigations are complex.

### Model-Agnostic

The Pantheon's enforcement architecture works with any LLM backend that
processes system prompts. The Activation Rule, per-message re-assessment,
and /rally command do not depend on Claude-specific features, GPT-specific
features, or any particular model's instruction-following characteristics.
The underlying mechanisms they exploit -- primacy bias, recency bias, active
generation -- are properties of the transformer architecture itself.

### Compositional

Prompt-level mitigations compose naturally. The three-layer architecture
(user rule + project rule + SKILL.md) provides defense in depth without any
single layer needing to be perfect. The /rally command adds a user-triggered
override on top of the automatic protocol. The subagent preference adds a
structural isolation layer. Each mechanism addresses a different failure mode,
and their combined effect is greater than any individual mechanism.

### Observable and Debuggable

Every mitigation we implemented is visible in plain text. When the system
fails, we can read the exact rules that should have been followed, examine
the agent transcript to see where compliance broke down, and trace the failure
to a specific gap in the enforcement stack. This observability was critical
to our iterative process -- the priority conflict between the user rule and
the Activation Rule was discovered by reading the system prompt and noticing
the contradiction.

Compare this to model-level or framework-level fixes, where failures are
opaque. If a fine-tuned model starts ignoring instructions, the debugging
process involves probing attention patterns, analyzing training data, and
running statistical evaluations. If a framework middleware silently drops a
routing directive, the failure is invisible without instrumented logging.

### Knowledge Externalization

The process of building and debugging prompt-level workarounds forced us to
externalize our understanding of instruction decay into a structured,
shareable form. The Activation Rule, violation test, and per-message directive
are not just engineering artifacts -- they are documentation of the failure
modes they address. A new team member reading the Pantheon's rules can
understand what instruction decay is and how the system defends against it,
even without reading this paper.

## 9.2 Drawbacks

### Fundamental Attention Budget Constraint

The most severe limitation of prompt-level workarounds is that they are
**subject to the very problem they are trying to solve.** Every rule we add
to combat instruction decay is itself a set of tokens competing for attention
in the context window. The Activation Rule, per-message directives, violation
tests, self-audit checkpoints, and re-anchor statements all consume context
tokens that dilute the attention available for other instructions.

This creates a paradox: **the more enforcement rules we add, the more
context they consume, and the faster all rules (including the enforcement
rules themselves) decay.** There is a diminishing-returns curve where
additional enforcement text produces decreasing marginal compliance and
eventually becomes counterproductive by crowding out the substantive
instructions it is trying to protect.

We observed this directly: our enforcement text grew from ~100 tokens (Fix 1)
to ~800 tokens (Fix 5 + /rally) across the iteration cycle. At some point,
the enforcement overhead will approach the practical limit of what the
context window can accommodate without degrading the model's ability to
actually do work.

### Probabilistic, Not Deterministic

Prompt-level enforcement is fundamentally **probabilistic.** The model
processes instructions through attention-weighted softmax distributions, not
through boolean logic gates. "PROHIBITED" does not mean "impossible" -- it
means "very unlikely in the immediate context, somewhat unlikely after 5
turns, and only slightly unlikely after 20 turns."

No amount of prompt engineering can make a rule truly mandatory. The model
can always generate a token that violates any rule, as long as that token has
a non-zero probability in the output distribution. Under sufficient attention
pressure (long context, competing instructions, strong task-completion drive),
any advisory rule will eventually be violated.

This is in stark contrast to mechanical enforcement, where violations are
physically impossible. A tool restriction that prevents the orchestrator from
calling file-edit tools eliminates unauthorized code changes with 100%
reliability, regardless of context length. Prompt-level enforcement can
approach but never reach this level of reliability.

### Escalating Complexity

Each iterative fix addressed a specific failure mode but also added
complexity to the instruction stack. The Pantheon's enforcement architecture
now spans:

- 1 user rule (~200 tokens)
- 1 global project rule (42 lines)
- 1 workspace project rule (120+ lines)
- 1 /rally command rule (56 lines)
- 1 Demeter SKILL.md (185+ lines)
- Per-message directives in 3 independent files
- Self-audit checkpoints at 5-tool-call intervals
- Re-anchor checkpoints at 10-tool-call intervals
- Context decay warnings at 7-turn thresholds

This complexity has costs:

1. **Maintenance burden**: Any change to the routing protocol must be
   synchronized across multiple files. We have already experienced roster
   drift (where one file had 19 agents while another had 26) and identity
   drift (where one file said "executor" while another said "orchestrator").

2. **Cognitive overhead for contributors**: A new team member must understand
   the three-layer architecture, the Activation Rule, the per-message
   directive, the /rally command, the self-audit checkpoint, the re-anchor
   checkpoint, and the subagent preference threshold before they can
   effectively modify the system.

3. **Rule interaction effects**: Rules at different layers can interact in
   unexpected ways, as we discovered with the user rule priority conflict.
   More rules mean more potential interaction effects.

### The Channeling Problem

Even with the Activation Rule in place, the model can comply with the letter
of the rule while violating its spirit. We observed a behavior we call
**channeling**: the model reads a specialist's SKILL.md (satisfying the
activation requirement) but then proceeds to do the work itself using the
specialist's methodology loaded into its own context, rather than dispatching
a subagent.

Channeling is technically compliant -- the skill was activated (read). But it
defeats the purpose of the routing protocol in two ways:

1. The specialist's methodology is applied by the orchestrator's degrading
   context rather than a fresh subagent context.
2. The orchestrator's context is further polluted with implementation details,
   accelerating decay for subsequent turns.

The /rally command was created specifically to address channeling, adding "No
channeling -- every identified specialist must be formally activated via Read
or Task" to the hard rules. But outside of /rally, channeling remains a
permitted (and common) behavior, because the standard Activation Rule allows
skill-mode activation (Read SKILL.md) as an alternative to subagent-mode
activation (Task dispatch).

### User Vigilance Required

The most uncomfortable truth about prompt-level workarounds is that they
**shift the reliability burden to the user.** The system works when:

- The user starts fresh conversations for new tasks
- The user invokes /rally when they notice decay
- The user monitors for channeling and calls it out
- The user keeps conversations short

Without active user vigilance, the system degrades predictably. The
workarounds extend the window of reliable operation from ~1-3 turns
(unmitigated) to ~5-10 turns (with full enforcement stack), but they do not
eliminate the need for human oversight.

This is a significant regression from the promise of autonomous multi-agent
orchestration. The ideal system would maintain perfect routing discipline
indefinitely without user intervention. The reality is that the user serves
as the ultimate enforcement mechanism -- the only actor in the system whose
attention does not decay with context length.

### Subagent Tradeoffs

The recommendation to prefer subagents over skills in long conversations
has its own costs:

1. **Latency**: Each subagent is a separate LLM invocation. Dispatching 3
   subagents in parallel is faster than sequential skill activation but
   still slower than a single orchestrator doing all the work.

2. **Context transfer overhead**: The orchestrator must extract relevant
   context from the conversation and package it as part of the subagent's
   prompt. This extraction is itself subject to the orchestrator's attention
   decay -- if the orchestrator's context is degraded, it may omit critical
   details from the subagent prompt.

3. **Synthesis burden**: Subagent output must be synthesized by the
   orchestrator, which is operating in the same degraded context. A degraded
   orchestrator may produce a poor synthesis even with excellent subagent
   output.

4. **Cost**: More LLM invocations mean higher inference costs. In
   pay-per-token environments, the subagent approach can increase total
   cost by 2-5x compared to skill-based orchestration.

### No Persistence Across Conversations

Prompt-level enforcement resets completely with each new conversation. There
is no mechanism for the system to learn from its own routing failures. If the
orchestrator failed to activate Frigg in conversation A, there is no way for
conversation B to start with heightened awareness of PowerShell-domain routing.

Each conversation begins from the same baseline rules, with the same strengths
and the same vulnerabilities. The only learning that persists is in the rule
files themselves -- which improve only through human intervention (the user
analyzing transcripts, identifying failures, and updating the rules).

## 9.3 The Honest Assessment

Prompt-level workarounds for instruction decay are **necessary, valuable,
and insufficient.** They are the best available approach for practitioners
using current tools, and they meaningfully extend the window of reliable
multi-agent orchestration. But they do not solve the underlying problem, and
they impose significant costs in complexity, context budget, and user
vigilance.

The honest assessment is:

- **Without workarounds**: Reliable orchestration for ~1-3 turns.
- **With full enforcement stack**: Reliable orchestration for ~5-10 turns.
- **With /rally override**: Reliable on any individual turn where invoked.
- **With fresh conversations**: Reliable indefinitely (by resetting the
  problem rather than solving it).

The gap between "5-10 turns of reliable orchestration" and "indefinite
reliable orchestration" can only be closed by changes at the model or
framework level -- changes that are outside the control of most practitioners
today.

Until those changes arrive, prompt-level enforcement is the state of the art.
It is a workaround, not a solution. But it is a workaround that works well
enough to make multi-agent orchestration practically useful, and the process
of building it teaches deep lessons about how LLMs process (and forget)
instructions.

---

# Part X: Recommendations for Practitioners

## 10.1 For Teams Building Multi-Agent Systems in Cursor

### Rule Design

1. **Audit your entire instruction stack.** Check for contradictions between
   user rules, project rules, AGENTS.md, and skill files. A single
   contradictory instruction at a higher priority level will undermine
   everything below it.

2. **Keep rules minimal and actionable.** Every rule that doesn't change the
   model's behavior is wasting context tokens and diluting the rules that do.
   Test each rule by removing it -- if behavior doesn't change, delete it.

3. **Use mechanical language, not advisory language.** "You are PROHIBITED
   from" is stronger than "you should not." "STOP" is stronger than "consider
   whether." The model interprets advisory language as optional under attention
   pressure.

4. **Include a violation test.** Give the model a concrete, mechanical check
   it can apply: "Look at your next tool call. Is it X or Y? If not, STOP."
   This converts an abstract rule into a specific decision procedure.

5. **Scope rules to every message.** Any rule that doesn't explicitly say "on
   EVERY user message" will be interpreted as applying only to the first
   message. Follow-up messages are treated as continuations of the previous
   execution flow.

### Conversation Management

6. **Start fresh conversations for new tasks.** This is the single highest-
   impact practice. A fresh conversation resets instruction attention to
   maximum.

7. **Use Plan mode before Agent mode.** Planning upfront reduces the total
   turns needed in Agent mode, keeping rule attention higher during execution.

8. **Prefer subagents over skills in long conversations.** After 10+ turns,
   redirect specialist work to subagents. They get fresh context windows where
   the rules are at full strength.

### Architecture

9. **Separate orchestration from execution.** The orchestrator should never
   perform specialist work. Its role is to decompose, delegate, validate, and
   synthesize. Any implementation work done by the orchestrator is a signal
   that the routing protocol has broken down.

10. **Use identity framing alongside enforcement.** Frame the orchestrator's
    core identity as "orchestrator first, implementer second." Identity shapes
    the model's default behavior; enforcement constrains it when the default
    fails.

## 10.2 For Teams Designing Agent Skill Frameworks

1. **Progressive disclosure reduces context cost.** Load agent catalogs
   (~50-100 tokens per agent) at session start, full instructions on
   activation, and resources on demand. This minimizes the baseline context
   cost of supporting many agents.

2. **Skills need verification standards.** Every specialist should define
   what "done" means and how to verify it. Without verification standards,
   the orchestrator has no way to validate specialist output.

3. **Subagent output contracts are essential.** Define the exact structure of
   what subagents return. Without output contracts, the orchestrator must
   parse unstructured text, which is error-prone and wastes context tokens.

4. **Version-control your rules.** Treat rule changes as code changes --
   they affect system behavior just as much as code does. Our experience
   shows that stale rules (outdated rosters, obsolete identity language)
   persist indefinitely without active auditing.

## 10.3 For Model Providers

1. **Expose instruction priority metadata.** Current models have no way to
   distinguish between high-priority and low-priority instructions other
   than position in the context. Explicit priority markers would allow
   enforcement rules to maintain their influence regardless of context length.

2. **Support per-turn instruction injection.** A framework-level mechanism
   for injecting rules at the end of the context (recency position) before
   each generation would eliminate the need for application-level runtime
   reinforcement.

3. **Provide tool-call-level routing enforcement.** Allow system prompts to
   define routing policies that are checked before tool execution: "If the
   specialist domain has been identified but no SKILL.md has been read,
   block the tool call and return an error."

4. **Address compaction amnesia.** When compacting conversation history,
   preserve the relative priority and mandatory nature of instructions.
   Current compaction treats all text as equally compressible, losing the
   distinction between critical rules and casual conversation.

5. **Investigate positional debiasing.** The "Found in the Middle"
   calibration method (arXiv 2406.16008) demonstrated that positional
   attention bias can be corrected at inference time, improving long-context
   performance by up to 15 percentage points. Applying similar techniques
   to system prompt attention could significantly reduce instruction decay.

---

# Part XI: Open Questions and Future Work

## 11.1 Unresolved Questions

1. **What is the precise relationship between context length and routing
   compliance?** We observed qualitative degradation after ~10 turns, but a
   quantitative measurement of compliance rate vs. conversation length would
   be valuable for setting thresholds.

2. **Does instruction decay follow a smooth curve or exhibit phase
   transitions?** Our observations suggest a relatively smooth decline, but
   some research on attention mechanisms suggests phase transitions at
   certain context lengths where the model's behavior changes abruptly.

3. **Can the SCAN protocol's active generation technique be integrated into
   Cursor's rule system?** Currently, Cursor rules are static text loaded
   at conversation start. A rule type that triggers active generation
   (requiring the model to answer questions about its rules before
   proceeding) could provide SCAN-like benefits within the existing
   framework.

4. **How do different models compare in instruction decay resistance?** Our
   experience is primarily with Claude models. GPT and Gemini models have
   different attention architectures and may exhibit different decay profiles.

5. **Can routing compliance be measured automatically?** A tool that analyzes
   agent transcripts to detect routing violations (specialist domains
   identified but not activated) would enable continuous monitoring and
   threshold tuning.

## 11.2 Future Work

1. **Automated routing compliance scoring.** Build a script that parses
   agent transcripts, identifies routing decisions, and scores compliance
   against the routing table. This would provide quantitative data on
   instruction decay rates.

2. **A/B testing of mitigation strategies.** Systematically compare the
   effectiveness of different mitigation combinations (per-message re-
   assessment alone vs. combined with subagent preference vs. combined with
   SCAN-like active generation).

3. **Framework-level routing enforcement.** Explore whether Cursor's
   extension or MCP architecture could support a routing enforcement
   middleware that checks compliance before tool execution.

4. **Cross-model benchmarking.** Test the Pantheon's enforcement
   architecture with different model backends (GPT-4.1, Gemini 2.5, Claude
   Opus) to characterize model-specific decay profiles and optimal
   mitigation strategies.

5. **Dynamic routing with feedback.** Implement CASTER-style routing that
   learns from its own failures, using execution outcomes to adjust the
   routing table over time.

---

# Appendices

## Appendix A: The Pantheon Activation Rule (Full Text)

The following is the complete Activation Rule as deployed in the Pantheon's
workspace rule (`.cursor/rules/pantheon.mdc`):

```markdown
## Activation Rule

PRECONDITION -- this gates all other work. No exceptions.

This rule applies on EVERY user message -- including follow-ups, corrections,
and continuations. Each user message is a new routing decision. Do NOT coast
on previous assessments. Long conversations cause instruction decay -- this
explicit re-check on every turn counteracts that.

When you identify specialist domains from the Routing table, your FIRST tool
calls MUST be:
- Read of .agents/skills/<name>/SKILL.md for each specialist (skill mode), OR
- Task dispatch for each specialist (subagent mode)

Until activation is complete, you are PROHIBITED from reading project files,
running commands, writing code, or any tool call that is not a SKILL.md Read
or subagent Task dispatch.

What does NOT count as activation:
- Mentioning an agent by name in your response
- Saying "I'll use X for this" or "Let me engage Y"
- Believing you already know the domain
- Having activated a specialist on a previous message (activation does not
  carry over between turns)

Violation test: After identifying specialists, look at your next tool call.
Is it a SKILL.md Read or Task dispatch? If not, STOP -- you are violating
this rule. Activate first, then proceed.

Self-audit: Every 5 tool calls, check your tool call history for THIS turn --
have you Read a SKILL.md for each specialist you identified? If any activation
is missing, STOP. Read the missing SKILL.md now. Then resume.

Context decay warning: In conversations longer than ~10 turns, prefer
dispatching subagents (Task tool) over loading skills (Read SKILL.md).
Subagents get fresh context windows where these rules are at full attention
weight. The main context decays; subagent context does not.
```

## Appendix B: Timeline of Fixes

| Date | Commit | Fix | Result |
|------|--------|-----|--------|
| 2026-03-23 | (session) | Fix 1: Advisory methodology step | Failed -- model skips advisory steps |
| 2026-03-23 | (session) | Fix 2: Standalone gating precondition | Partial -- first message only |
| 2026-03-23 | (session) | Fix 3: User rule alignment | Partial -- removes priority conflict |
| 2026-03-23 | (session) | Fix 4: Identity reframe | Partial -- reduces self-execution tendency |
| 2026-03-24 | `37e7a1f` | Combined enforcement: activation rule + identity + audit | Published |
| 2026-03-24 | `46bf145` | Fix 5: Per-message re-assessment + subagent preference | Published |
| 2026-03-24 | `2cbedf8` | Fix 6: /rally command, 7-turn threshold, 3 new subagents, re-anchor checkpoint | Published |

## Appendix C: References

### Academic Papers

1. Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni,
   F., & Liang, P. (2024). "Lost in the Middle: How Language Models Use Long
   Contexts." *Transactions of the Association for Computational Linguistics
   (TACL)*, 12. ACL Anthology 2024.tacl-1.9.

2. Mu, J., et al. (2024). "Measuring and Controlling Instruction (In)Stability
   in Language Model Dialogs." arXiv:2402.10962.

3. Wu, et al. (2025). "On the Emergence of Position Bias in Transformers."
   *Proceedings of the International Conference on Machine Learning (ICML)*.
   PMLR v267.

4. "We Are What We Repeatedly Do: Improving Long Context Instruction
   Following." (2026). *Findings of the European Chapter of the Association
   for Computational Linguistics (EACL)*. ACL Anthology 2026.findings-eacl.254.

5. "Lost in the Middle at Birth: An Exact Theory of Transformer Position
   Bias." (2026). arXiv:2603.10123.

6. Zhang, Y., et al. (2024). "Found in the Middle: Calibrating Positional
   Attention Bias Improves Long Context Utilization." arXiv:2406.16008.

7. "A Residual-Aware Theory of Position Bias in Transformers." (2026).
   arXiv:2602.16837.

8. "Attention Sorting Combats Recency Bias in Long Context Language Models."
   (2023). arXiv:2310.01427.

### Multi-Agent Systems Research

9. "Why Do Multi-Agent LLM Systems Fail?" (2025). arXiv:2503.13657. (MAST
   Taxonomy -- 14 failure modes, 1,600+ traces, 7 frameworks).

10. CASTER: "Breaking the Cost-Performance Barrier in Multi-Agent
    Orchestration via Context-Aware Strategy for Task Efficient Routing."
    (2026). arXiv:2601.19793.

11. AMRO-S: "Efficient and Interpretable Multi-Agent LLM Routing via Ant
    Colony Optimization." (2026). arXiv:2603.12933.

12. "Self-Healing Tool Routing for AI Agent Development." (2026).
    arXiv:2603.01548.

13. AgentAsk: "Error Propagation at Agent Handoffs." (2025).
    arXiv:2510.07593.

14. Symphony-Coord: "Architecture and Operations of a Multi-Agent System."
    (2026). arXiv:2602.00966.

### Industry Publications

15. Shukla, S. (2026). "Runtime Reinforcement: Preventing 'Instruction Decay'
    in Long Context Windows." *Towards AI*.
    https://pub.towardsai.net/runtime-reinforcement-preventing-instruction-decay-in-long-context-windows-66d498097db9

16. Rogov, M. (2026). "Why Your AI Orchestrator Should Never Write Code."
    *Towards AI*.

17. Smith, F. (2026). "Toward Stable Long-Term Memory in LLMs: Decay, Drift,
    and Distributed Continuity." *Medium*.

18. SCAN Protocol Implementation. (2026). OpenAI Codex Issue #14348.
    https://github.com/openai/codex/issues/14348

19. Cursor Official Blog. (2026). "Best Practices for Coding with Agents."
    https://cursor.so/blog/agent-best-practices

### Community Reports

20. "Persistent communication constraint failure: in-context style rules
    degrade over session length." anthropics/claude-code Issue #31611.

21. "Model ignores in-context rules on first attempt, self-corrects only
    after failure or user intervention." anthropics/claude-code Issue #31841.

22. "Critical: Opus 4.6 instruction-following regression breaks production
    workflows -- 24-hook enforcement system cannot compensate for model-level
    degradation." anthropics/claude-code Issue #34358.

23. Panghal, J. (2026). "The 'Manual Agent' Trap: Why Your AI Orchestration
    is Failing." *LinkedIn*.

24. "Solving agent system prompt drift in long sessions -- a 300-token fix."
    run-llama/llama_index Discussion #20801.

---

*This document is maintained as part of the Pantheon framework at
`pantheon-py`. Contributions, corrections, and additional
field observations are welcome.*
