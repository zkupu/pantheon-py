# Workflow Templates

These workflows are available as slash commands in Cursor (`.cursor/commands/`).
In Claude Code or other environments, copy-paste the prompt template below.

Each template invokes the same Pantheon specialists that the Cursor slash
command would. The prompts are written so the agent can identify the correct
specialist from the routing table without Cursor-specific syntax.

---

## Code Review

**Cursor**: `/review`
**Claude Code**: paste the prompt below

> Review the current changes for production readiness. Apply multiple specialist perspectives:
>
> 1. **Code quality** (Saraswati) — correctness, clarity, error handling, idiom compliance
> 2. **Security** (Kali) — injection, auth, secrets, trust boundaries
> 3. **Testing** (Themis) — are critical paths tested? coverage gaps?
> 4. **Ops readiness** (Pele) — logging, health checks, graceful shutdown, config management
> 5. **Documentation** (Aphrodite) — are changes documented? READMEs updated?
>
> For each area, report: what's good, what needs fixing, and concrete fixes.
>
> Use `git diff` to identify all changes. Read the affected files in full context.

---

## Test Execution

**Cursor**: `/test`
**Claude Code**: paste the prompt below

> Write tests for the specified code, following the Themis testing methodology.
>
> 1. Read the implementation files and understand the code under test
> 2. Identify critical paths and edge cases
> 3. Check existing test patterns in the project — match conventions
> 4. Write tests: table-driven where applicable, clear names, Arrange-Act-Assert
> 5. Run the tests — confirm they pass
> 6. Verify tests fail when the target behavior is removed (mental mutation test)
>
> Prioritize: critical paths first, edge cases second, happy paths last (they're usually already covered).

---

## Security Audit

**Cursor**: `/security-audit`
**Claude Code**: paste the prompt below

> Perform a security assessment of the specified code or the current project, following the Kali security methodology.
>
> 1. Map the attack surface — entry points, trust boundaries, data flows
> 2. Apply STRIDE to each component
> 3. Scan for: hardcoded secrets, injection vectors, missing auth, unsafe deserialization
> 4. Search for patterns: `password`, `secret`, `key`, `token`, `exec`, `eval`, `unsafe`
> 5. Check dependencies for known vulnerabilities
> 6. Classify findings by severity (Critical / High / Medium / Low / Info)
> 7. Provide a concrete remediation for every finding
>
> Output each finding as: Title | Severity | Location | Description | Remediation | Cost of deferral

---

## Planning

**Cursor**: `/plan`
**Claude Code**: paste the prompt below

> Analyze the request and produce a detailed implementation plan before writing any code, following the Athena strategic planning methodology.
>
> 1. Read relevant code, configs, and documentation
> 2. Identify constraints: existing patterns, dependencies, risks
> 3. Propose an approach with alternatives and tradeoffs
> 4. Break the plan into concrete steps with acceptance criteria
> 5. Identify what could go wrong
> 6. Present the plan for approval before proceeding
>
> Do NOT write implementation code. Plan only.

---

## Values Check

**Cursor**: `/values-check`
**Claude Code**: paste the prompt below

> Weigh the current decision or approach against engineering values, following the Maat values-alignment methodology.
>
> Evaluate against all four pillars:
>
> 1. **High-Velocity Development** — Does this accelerate or slow the development loop? Build times? Feedback loops? Time-to-value?
> 2. **Innovation** — Are we pushing boundaries or playing safe? Is "we've always done it this way" driving the choice?
> 3. **Thorough Testing** — Is test coverage adequate? Are we buying velocity at the cost of quality?
> 4. **Solid Documentation** — Is this documented? Will the person joining in 6 months understand it?
>
> For each value: state whether the decision aligns or compromises. Name any debt explicitly. End with a clear recommendation.
