# Proposal: Skip Unit Tests for MVP

## Context
We're 2 weeks from our MVP deadline. The feature is a new dashboard that aggregates metrics from 3 internal services.

## Proposal
Skip writing unit tests for the dashboard backend to ship on time. We'll add tests after launch during the "hardening sprint" in Q2.

## Rationale
- Dashboard is read-only (low risk)
- Data comes from existing tested services
- Manual QA will cover the critical paths
- Team is underwater on the deadline

## Impact
- Saves ~3 days of engineering time
- Increases risk of regressions during Q2 changes
- Sets a precedent for test-optional features
