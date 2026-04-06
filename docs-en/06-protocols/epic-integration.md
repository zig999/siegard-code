# Epic Integration Protocol

Cross-Story validation executed when all Stories in an Epic are complete.

## When triggered

All Stories in an Epic reach `Done` status.

## What it validates

### Backend
- API contract consistency across Stories
- Database migration compatibility
- Data consistency and integrity
- Cross-domain integration points

### Frontend
- Navigation flow consistency across screens
- Shared state management correctness
- Layout consistency
- Cross-Story UI integration

## Process

1. QA executes regression tests across all Stories in the Epic
2. Cross-Story validation checks are performed
3. If issues found: specific Stories are flagged for rework
4. If passed: Epic is marked as integration-complete

## Separate protocols

Backend and frontend have distinct epic integration protocols:
- `u-be-epic-integration.md`
- `u-fe-epic-integration.md`
