Execute the full specialist dispatch protocol for this request.

1. **Classify** (visible to user) — State every applicable specialist from the Routing table in AGENTS.md, why each applies, and mode (skill via Read SKILL.md, or subagent via Task dispatch).

2. **Activate ALL** — Your first tool calls MUST be Read or Task for EVERY identified specialist. No other tool calls until all activations are complete.
   - Implementation work → skill (Read `.agents/skills/<name>/SKILL.md`)
   - Analysis/review work → subagent (Task dispatch using `.agents/subagents/<name>.md`)
   - When uncertain → subagent (fresh context beats decayed context)

3. **Execute** — Work through each activated specialist's methodology. Follow their verification standards.

4. **Synthesize** — Combine all specialist outputs into a unified response with clear attribution.

Hard rules: No channeling (every specialist formally activated). No skipping. No early implementation. No collapsing specialists into generic output.

$ARGUMENTS
