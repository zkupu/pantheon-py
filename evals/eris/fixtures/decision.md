# Decision: Adopt Microservices Architecture

## Context
Our monolithic Django app handles 50k requests/day. The team (8 engineers) wants to move to microservices to "improve developer velocity" and "enable independent deployments."

## Plan
- Split the monolith into 6 microservices (users, orders, payments, inventory, notifications, analytics)
- Use Kubernetes for orchestration
- Implement an API gateway
- Migrate over 6 months

## Expected Benefits
- Teams can deploy independently
- Better scalability per service
- Technology diversity (use the best tool for each job)
- Easier onboarding (smaller codebases)
