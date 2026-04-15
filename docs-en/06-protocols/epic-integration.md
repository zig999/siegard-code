# Epic Integration Protocol

Cross-Task Contract validation executed when all Task Contracts in an Epic are complete.

## When triggered

All Task Contracts in an Epic reach `Done` status.

## What it validates

### Backend
- API contract consistency across Task Contracts
- Database migration compatibility
- Data consistency and integrity
- Cross-domain integration points

### Frontend
- Navigation flow consistency across screens
- Shared state management correctness
- Layout consistency
- Cross-Task Contract UI integration

## Process

1. QA executes regression tests across all Task Contracts in the Epic
2. Cross-Task Contract validation checks are performed
3. If issues found: specific Task Contracts are flagged for rework
4. If passed: Epic is marked as integration-complete

## Separate protocols

Backend and frontend have distinct epic integration protocols:
- `u-be-epic-integration.md`
- `u-fe-epic-integration.md`
