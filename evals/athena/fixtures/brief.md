# Project Brief: Real-Time Notification Service

## Context
Our e-commerce platform (50k DAU) needs a notification service. Currently, notifications are sent synchronously during checkout, causing 2-3s latency spikes.

## Requirements
- Send email, SMS, and push notifications
- Must not block the checkout flow
- 99.9% delivery guarantee
- Support for notification preferences per user
- Rate limiting (max 10 notifications/user/hour)
- Template support for notification content

## Constraints
- Team: 3 backend engineers, 1 DevOps
- Timeline: 8 weeks to MVP
- Infra: AWS, currently using RDS PostgreSQL and ECS
- Budget: No new managed services over $500/month
