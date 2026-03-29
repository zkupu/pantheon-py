# Task: Migrate Authentication from Session-Based to JWT

## Current State
- Flask app with session-based auth using Flask-Login
- Sessions stored in Redis
- 15 API endpoints, 8 require authentication
- 3 user roles: admin, editor, viewer
- Frontend is a React SPA that stores session cookies

## Goal
Migrate to JWT-based authentication while:
- Maintaining backward compatibility during rollout
- Supporting both session and JWT during transition
- Adding refresh token support
- Keeping role-based access control
- Updating the React frontend to use Bearer tokens
