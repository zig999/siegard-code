---
name: u-spec-globals-error-codes
description: Centralized project error code catalog. Every error.code must be registered here before being used in any spec.
user-invocable: false
---

# Error Code Catalog — FRAMEWORK BASE

> **Do not add project codes to this file (R14b).** It ships with Siegard, is listed in
> `siegard-manifest.json` with its SHA-256, and is **overwritten on every upgrade** — a manual
> copy into `.claude/` takes no merge step, so anything added here is silently lost and
> `verify_install.py` reports the file as `modified` until then.
>
> **Project codes live in `{SPECS_DIR}/_global/error-codes.md`.** That file belongs to the project,
> is never touched by an upgrade, and is the one the deterministic gate reads
> (`check_error_codes_synced.py`). Spec agents read **both** and treat the union as the catalog:
> this file for the base codes every project shares, the project file for its own.
>
> A downstream project did add its codes here — reasonably, since every agent was told this was
> "the global error catalog" while the developer agents were pointed at the project file under the
> same description. That ambiguity is what this header removes.

| | This file | `{SPECS_DIR}/_global/error-codes.md` |
|---|---|---|
| Owner | Siegard | the project |
| Contains | base codes shared by every project | codes for this project's domains |
| On upgrade | overwritten | untouched |
| Under manifest integrity | yes | no |
| Read by the `error_codes_synced` gate | no | **yes** |

## Rules
1. Every `error.code` is a SCREAMING_SNAKE_CASE string
2. Prefix indicates the category: `AUTH_`, `VALIDATION_`, `RESOURCE_`, `BUSINESS_`, `SYSTEM_`
3. Never reuse a removed code — mark as `deprecated`
4. Every new code must be registered BEFORE being used in any spec — a project code in
   `{SPECS_DIR}/_global/error-codes.md`, a framework base code here
5. The Spec Reviewer validates that no code is used without being in this catalog

## Base Codes (present in every project)

### Authentication (AUTH_)
| error.code | HTTP | Description | When it occurs |
|------------|------|-------------|----------------|
| `AUTH_TOKEN_EXPIRED` | 401 | Authentication token expired | JWT expired |
| `AUTH_TOKEN_INVALID` | 401 | Invalid or malformed token | JWT not decodable |
| `AUTH_UNAUTHORIZED` | 401 | Not authenticated | Request without token |
| `AUTH_FORBIDDEN` | 403 | No permission for this resource | RBAC denied access |

### Validation (VALIDATION_)
| error.code | HTTP | Description | When it occurs |
|------------|------|-------------|----------------|
| `VALIDATION_REQUIRED_FIELD` | 422 | Required field missing | Incomplete body |
| `VALIDATION_INVALID_FORMAT` | 422 | Invalid format | Email, date, etc. |
| `VALIDATION_OUT_OF_RANGE` | 422 | Value outside allowed range | Min/max violated |

### Resource (RESOURCE_)
| error.code | HTTP | Description | When it occurs |
|------------|------|-------------|----------------|
| `RESOURCE_NOT_FOUND` | 404 | Resource not found | Nonexistent ID |
| `RESOURCE_ALREADY_EXISTS` | 409 | Resource already exists | Unique constraint |
| `RESOURCE_CONFLICT` | 409 | State conflict | Concurrent operation |

### Business (BUSINESS_)
| error.code | HTTP | Description | When it occurs |
|------------|------|-------------|----------------|
| (defined per domain — each domain adds its own below) | | | |

### System (SYSTEM_)
| error.code | HTTP | Description | When it occurs |
|------------|------|-------------|----------------|
| `SYSTEM_INTERNAL_ERROR` | 500 | Unexpected internal error | Unhandled exception |
| `SYSTEM_SERVICE_UNAVAILABLE` | 503 | External service unavailable | Integration timeout |

## Codes by Domain
<!-- Each domain adds its BUSINESS_ codes here when specified -->
<!-- Format: ### {Domain} followed by table with the 4 fields above -->

## Deprecated Codes

Removed codes that CANNOT be reused. Keep here to avoid collision.

| error.code | Deprecated on | Reason | Replaced by |
|------------|---------------|--------|-------------|
<!-- Example: -->
<!-- | `BUSINESS_OLD_CODE` | 2026-03-21 | Domain restructured | `BUSINESS_NEW_CODE` | -->

### Deprecation rules
1. When removing an active error.code, move it to this section (do not delete)
2. Fill in all fields: date, reason, replacement code (or "none")
3. The Spec Reviewer validates that no deprecated code is being used in active specs
