# Event Schema — Especificação Formal

> Spec de referência: schemas JSON formais de cada tipo de evento do orquestrador.
> Uso: validação em runtime, testes, e contrato para implementadores.
> Formato: JSON Schema draft 2020-12.

---

## Como usar este documento

Todos os schemas abaixo podem ser usados com `jsonschema` (Python stdlib compatível via `pip install jsonschema`) ou com validação manual em stdlib.

**Propósito primário**: validar eventos antes de escrever no log. Um evento que falha validação aqui **nunca deve chegar ao log**.

**Propósito secundário**: referência para implementação do `emit.py`, `append.py`, e reducer.

---

## Sumário

1. [Schema base (comum a todos os eventos)](#1-schema-base)
2. [Eventos de ciclo de task](#2-eventos-de-ciclo-de-task)
3. [Eventos de ciclo de fase](#3-eventos-de-ciclo-de-fase)
4. [Eventos de gestão e operação](#4-eventos-de-gestão-e-operação)
5. [Tipos comuns reutilizados](#5-tipos-comuns-reutilizados)
6. [Enumerações](#6-enumerações)
7. [Validação em Python](#7-validação-em-python)

---

## 1. Schema base

Todos os eventos seguem este envelope. Os schemas específicos por tipo refinam o campo `data`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/orch/event-base.json",
  "title": "Event (base envelope)",
  "type": "object",
  "required": ["seq", "event_id", "ts", "agent", "event_type", "attempt", "data", "prev_hash", "hash"],
  "additionalProperties": false,
  "properties": {
    "seq": {
      "type": "integer",
      "minimum": 1,
      "description": "Monotonically increasing global sequence number, assigned at write time"
    },
    "event_id": {
      "type": "string",
      "pattern": "^evt_[0-9A-HJKMNP-TV-Z]{26}$",
      "description": "ULID-like unique identifier with evt_ prefix"
    },
    "ts": {
      "type": "string",
      "format": "date-time",
      "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\\.[0-9]{3}Z$",
      "description": "ISO 8601 UTC with millisecond precision"
    },
    "agent": {
      "type": "string",
      "pattern": "^(orchestrator|worker-[a-z0-9-]+|hook-[a-z_-]+|operator|system)(\\s*<[^>]+>)?$",
      "description": "Emitter identity"
    },
    "event_type": {
      "type": "string",
      "enum": [
        "task_created", "task_claimed", "task_progress",
        "task_completed", "task_failed",
        "task_scheduled_retry", "task_retried", "task_dlq",
        "phase_declared", "phase_entered",
        "phase_exit_criterion_met", "phase_exit_approved",
        "phase_transitioned", "phase_paused", "phase_resumed",
        "circuit_breaker_tripped",
        "escalation", "human_response",
        "snapshot", "log_recovered", "preflight_failed"
      ],
      "description": "One of 21 canonical event types"
    },
    "task_id": {
      "oneOf": [
        {"type": "null"},
        {"type": "string", "pattern": "^t_[0-9]+$"}
      ],
      "description": "Task identifier (t_NNNN) or null for global events"
    },
    "attempt": {
      "type": "integer",
      "minimum": 1,
      "description": "Current attempt number, starts at 1"
    },
    "data": {
      "type": "object",
      "description": "Type-specific payload (see per-type schemas)"
    },
    "prev_hash": {
      "type": "string",
      "oneOf": [
        {"const": "GENESIS"},
        {"pattern": "^[0-9a-f]{64}$"}
      ],
      "description": "SHA-256 of previous event, or GENESIS for first event"
    },
    "hash": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$",
      "description": "SHA-256 of this event (excluding hash field itself)"
    }
  }
}
```

**Notas sobre o envelope:**

- `event_id` usa padrão ULID-like: prefixo `evt_` + 26 chars base32 (exclui I, L, O, U).
- `ts` tem precisão de milissegundos e sempre UTC (Z).
- `agent` permite 5 formas: `orchestrator`, `worker-<type>-<id>`, `hook-<name>`, `operator`, `system`. Opcional: sufixo `<email>` para auditoria.
- `task_id` é `null` para eventos globais (phase_*, escalation, snapshot, etc.).
- `attempt` é sempre >= 1. Para eventos globais sem noção de tentativa, usar 1.
- Hash chain: `prev_hash` do primeiro evento é `"GENESIS"`. Dos demais, é o `hash` do anterior.
- `hash` é calculado sobre o evento **excluindo** o próprio campo `hash`, com chaves ordenadas.

---

## 2. Eventos de ciclo de task

### 2.1 `task_created`

Declara uma nova task no workflow.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/orch/events/task_created.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_created"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "attempt": {"const": 1},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "tier", "type", "spec", "deps"],
          "additionalProperties": false,
          "properties": {
            "phase": {
              "type": "string",
              "pattern": "^[a-z][a-z0-9_-]*$",
              "description": "Phase name this task belongs to"
            },
            "tier": {
              "type": "string",
              "enum": ["critical", "standard", "bulk"]
            },
            "type": {
              "type": "string",
              "pattern": "^[a-z][a-z0-9_-]*$",
              "description": "Task type (maps to worker via phase rules)"
            },
            "spec": {
              "type": "string",
              "minLength": 1,
              "maxLength": 5000,
              "description": "Human/LLM-readable task specification"
            },
            "deps": {
              "type": "array",
              "items": {"type": "string", "pattern": "^t_[0-9]+$"},
              "uniqueItems": true,
              "description": "Task IDs this task depends on"
            },
            "priority": {
              "type": "integer",
              "minimum": 0,
              "maximum": 100,
              "default": 50,
              "description": "Higher = earlier scheduling among ready tasks"
            },
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1},
              "description": "Seq numbers justifying task creation"
            }
          }
        }
      }
    }
  ]
}
```

**Exemplo válido:**

```json
{
  "seq": 10,
  "event_id": "evt_01HK7XZY8K9M3P4Q5R6S7T8U9V",
  "ts": "2026-04-20T10:00:42.123Z",
  "agent": "orchestrator",
  "event_type": "task_created",
  "task_id": "t_0042",
  "attempt": 1,
  "data": {
    "phase": "dev",
    "tier": "standard",
    "type": "implementation",
    "spec": "Implement JWT signing function in src/auth/jwt.py using RS256",
    "deps": ["t_0040", "t_0041"],
    "priority": 50,
    "evidence": [5, 8]
  },
  "prev_hash": "a3f2c8b9...",
  "hash": "7b91d4e2..."
}
```

### 2.2 `task_claimed`

Orchestrator atribui uma task `ready` a um worker.

```json
{
  "$id": "https://example.com/orch/events/task_claimed.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_claimed"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "worker_type", "worker_id"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "worker_type": {"type": "string", "pattern": "^[a-z][a-z0-9-]*$"},
            "worker_id": {"type": "string", "pattern": "^worker-[a-z0-9-]+-[0-9]+$"},
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  ]
}
```

### 2.3 `task_progress`

Worker reporta progresso. Serve como heartbeat E marcos.

```json
{
  "$id": "https://example.com/orch/events/task_progress.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_progress"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"type": "string", "pattern": "^worker-"},
        "data": {
          "type": "object",
          "required": ["phase", "note"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "note": {
              "type": "string",
              "minLength": 1,
              "maxLength": 500,
              "description": "Human-readable milestone description"
            },
            "pct": {
              "type": "number",
              "minimum": 0,
              "maximum": 100,
              "description": "Optional completion percentage"
            }
          }
        }
      }
    }
  ]
}
```

### 2.4 `task_completed`

Worker conclui task com sucesso.

```json
{
  "$id": "https://example.com/orch/events/task_completed.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_completed"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"type": "string", "pattern": "^worker-"},
        "data": {
          "type": "object",
          "required": ["phase", "artifacts", "summary"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "artifacts": {
              "type": "array",
              "items": {"type": "string"},
              "description": "File paths created or modified (NOT inline content)"
            },
            "summary": {
              "type": "string",
              "minLength": 1,
              "maxLength": 500,
              "description": "Short description of what was done"
            },
            "metrics": {
              "type": "object",
              "description": "Optional execution metrics",
              "properties": {
                "duration_seconds": {"type": "number", "minimum": 0},
                "tokens_in": {"type": "integer", "minimum": 0},
                "tokens_out": {"type": "integer", "minimum": 0}
              }
            }
          }
        }
      }
    }
  ]
}
```

**Convenção crítica**: `artifacts` são **paths**, não conteúdo inline. Se worker precisa incluir conteúdo grande, usa o mecanismo de blob externalizado (ver schema base do evento).

### 2.5 `task_failed`

Worker ou hook reporta falha.

```json
{
  "$id": "https://example.com/orch/events/task_failed.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_failed"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"type": "string", "pattern": "^(worker-|hook-)"},
        "data": {
          "type": "object",
          "required": ["phase", "reason", "retryable"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "reason": {
              "type": "string",
              "minLength": 1,
              "maxLength": 1000
            },
            "retryable": {
              "type": "boolean",
              "description": "true = transient (will retry); false = deterministic (DLQ immediately)"
            },
            "synthesized_by": {
              "type": "string",
              "description": "Set by hook when synthesizing failure (e.g., 'stale_detection')"
            },
            "original_worker": {
              "type": "string",
              "description": "When synthesized, which worker was running"
            }
          }
        }
      }
    }
  ]
}
```

### 2.6 `task_scheduled_retry`

Orchestrator agenda retry com backoff.

```json
{
  "$id": "https://example.com/orch/events/task_scheduled_retry.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_scheduled_retry"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "next_retry_at", "backoff_seconds", "previous_failure_seq"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "next_retry_at": {
              "type": "string",
              "format": "date-time"
            },
            "backoff_seconds": {
              "type": "number",
              "minimum": 0
            },
            "reason": {"type": "string"},
            "previous_failure_seq": {
              "type": "integer",
              "minimum": 1
            },
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  ]
}
```

### 2.7 `task_retried`

Orchestrator re-enfileira task. O `attempt` do evento é o novo (= previous + 1).

```json
{
  "$id": "https://example.com/orch/events/task_retried.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_retried"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "attempt": {"type": "integer", "minimum": 2},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "previous_attempt", "scheduled_retry_seq"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "previous_attempt": {"type": "integer", "minimum": 1},
            "scheduled_retry_seq": {"type": "integer", "minimum": 1},
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  ]
}
```

### 2.8 `task_dlq`

Task vai para Dead Letter Queue (terminal).

```json
{
  "$id": "https://example.com/orch/events/task_dlq.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "task_dlq"},
        "task_id": {"type": "string", "pattern": "^t_[0-9]+$"},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "reason", "last_error"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "reason": {
              "type": "string",
              "enum": ["non_retryable", "max_attempts_exceeded", "cascade_from_dep", "manual_dlq"]
            },
            "last_error": {
              "type": "string",
              "description": "Copy of last task_failed reason"
            },
            "dep_task_id": {
              "type": "string",
              "pattern": "^t_[0-9]+$",
              "description": "For cascade_from_dep: which dep failed"
            },
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  ]
}
```

---

## 3. Eventos de ciclo de fase

### 3.1 `phase_declared`

Orchestrator declara o workflow completo no início.

```json
{
  "$id": "https://example.com/orch/events/phase_declared.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_declared"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["workflow_id", "phases"],
          "additionalProperties": false,
          "properties": {
            "workflow_id": {
              "type": "string",
              "pattern": "^wf_[a-z0-9_-]+$"
            },
            "workflow_type": {
              "type": "string",
              "enum": ["dev-cycle", "bug-fix", "refactor", "spike", "custom"]
            },
            "phases": {
              "type": "array",
              "minItems": 1,
              "items": {
                "type": "object",
                "required": ["name", "order", "required"],
                "properties": {
                  "name": {"type": "string", "pattern": "^[a-z][a-z0-9_-]*$"},
                  "order": {"type": "integer", "minimum": 1},
                  "required": {"type": "boolean"}
                }
              }
            }
          }
        }
      }
    }
  ]
}
```

### 3.2 `phase_entered`

Fase se torna `active`.

```json
{
  "$id": "https://example.com/orch/events/phase_entered.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_entered"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "order"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "order": {"type": "integer", "minimum": 1},
            "previous_phase": {
              "oneOf": [{"type": "null"}, {"type": "string"}]
            },
            "entered_at": {"type": "string", "format": "date-time"}
          }
        }
      }
    }
  ]
}
```

### 3.3 `phase_exit_criterion_met`

Critério individual atingido (granularidade fina para auditoria).

```json
{
  "$id": "https://example.com/orch/events/phase_exit_criterion_met.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_exit_criterion_met"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "criterion"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "criterion": {
              "type": "string",
              "description": "Criterion ID from exit-criteria.json"
            },
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            },
            "details": {
              "type": "object",
              "description": "Output of checker script"
            }
          }
        }
      }
    }
  ]
}
```

### 3.4 `phase_exit_approved`

Todos os critérios required atingidos.

```json
{
  "$id": "https://example.com/orch/events/phase_exit_approved.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_exit_approved"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "criteria_met", "next_phase"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "criteria_met": {
              "type": "array",
              "items": {"type": "string"},
              "minItems": 1
            },
            "next_phase": {
              "oneOf": [{"type": "null"}, {"type": "string"}],
              "description": "null if this is the final phase"
            },
            "approved_by": {
              "type": "string",
              "enum": ["orchestrator", "human"]
            }
          }
        }
      }
    }
  ]
}
```

### 3.5 `phase_transitioned`

Fase anterior fecha, próxima abre (atomicamente logicamente, dois eventos no log).

```json
{
  "$id": "https://example.com/orch/events/phase_transitioned.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_transitioned"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["from_phase", "to_phase", "evidence_seq"],
          "additionalProperties": false,
          "properties": {
            "from_phase": {"type": "string"},
            "to_phase": {
              "oneOf": [
                {"type": "null", "description": "Workflow completed"},
                {"type": "string"}
              ]
            },
            "transitioned_at": {"type": "string", "format": "date-time"},
            "evidence_seq": {
              "type": "integer",
              "minimum": 1,
              "description": "Seq of the phase_exit_approved that justified this"
            }
          }
        }
      }
    }
  ]
}
```

### 3.6 `phase_paused`

```json
{
  "$id": "https://example.com/orch/events/phase_paused.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_paused"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "reason"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "reason": {
              "type": "string",
              "enum": ["escalation", "manual_pause", "circuit_breaker"]
            },
            "escalation_seq": {
              "type": "integer",
              "description": "For reason=escalation: seq of the escalation event"
            }
          }
        }
      }
    }
  ]
}
```

### 3.7 `phase_resumed`

```json
{
  "$id": "https://example.com/orch/events/phase_resumed.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "phase_resumed"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["phase", "paused_seq"],
          "additionalProperties": false,
          "properties": {
            "phase": {"type": "string"},
            "paused_seq": {
              "type": "integer",
              "minimum": 1
            },
            "resumed_by": {
              "type": "string",
              "enum": ["orchestrator", "human"]
            },
            "human_response_seq": {
              "type": "integer",
              "description": "If resumed by human response"
            }
          }
        }
      }
    }
  ]
}
```

---

## 4. Eventos de gestão e operação

### 4.1 `circuit_breaker_tripped`

```json
{
  "$id": "https://example.com/orch/events/circuit_breaker_tripped.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "circuit_breaker_tripped"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["window_start", "window_end", "failure_count", "threshold"],
          "additionalProperties": false,
          "properties": {
            "window_start": {"type": "string", "format": "date-time"},
            "window_end": {"type": "string", "format": "date-time"},
            "failure_count": {"type": "integer", "minimum": 0},
            "threshold": {"type": "integer", "minimum": 1},
            "window_minutes": {"type": "number", "minimum": 0},
            "scope": {
              "type": "string",
              "enum": ["workflow", "per_worker_type", "per_phase"]
            },
            "affected_workers": {
              "type": "array",
              "items": {"type": "string"}
            },
            "affected_phase": {"type": "string"},
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1}
            }
          }
        }
      }
    }
  ]
}
```

### 4.2 `escalation`

```json
{
  "$id": "https://example.com/orch/events/escalation.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "escalation"},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["code", "severity", "reason", "evidence"],
          "additionalProperties": false,
          "properties": {
            "code": {
              "type": "string",
              "enum": [
                "E01_unknown_event",
                "E02_illegal_transition",
                "E03_dependency_cycle",
                "E04_critical_task_dlq",
                "E05_duplicate_completion",
                "E06_deadlock",
                "E07_invariant_violation",
                "E08_budget_exceeded",
                "E09_corrupted_log",
                "E10_invalid_config",
                "E11_no_worker_for_type",
                "E12_unknown_phase"
              ]
            },
            "severity": {
              "type": "string",
              "enum": ["warning", "error", "critical"]
            },
            "reason": {
              "type": "string",
              "minLength": 1,
              "maxLength": 1000
            },
            "evidence": {
              "type": "array",
              "items": {"type": "integer", "minimum": 1},
              "minItems": 1
            },
            "suggested_actions": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        }
      }
    }
  ]
}
```

### 4.3 `human_response`

Humano resolve uma escalação.

```json
{
  "$id": "https://example.com/orch/events/human_response.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "human_response"},
        "agent": {"const": "operator"},
        "data": {
          "type": "object",
          "required": ["escalation_seq", "action", "operator"],
          "additionalProperties": false,
          "properties": {
            "escalation_seq": {"type": "integer", "minimum": 1},
            "action": {
              "type": "string",
              "enum": [
                "resume_phase",
                "cancel_task",
                "cancel_workflow",
                "force_retry",
                "mark_dlq",
                "reset_circuit_breaker",
                "acknowledge_only"
              ]
            },
            "operator": {
              "type": "string",
              "description": "Identity of the operator (email, handle, etc.)"
            },
            "notes": {
              "type": "string",
              "maxLength": 2000
            },
            "affected_task_ids": {
              "type": "array",
              "items": {"type": "string", "pattern": "^t_[0-9]+$"}
            }
          }
        }
      }
    }
  ]
}
```

### 4.4 `snapshot`

```json
{
  "$id": "https://example.com/orch/events/snapshot.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "snapshot"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["snapshot_path", "summary"],
          "additionalProperties": false,
          "properties": {
            "snapshot_path": {
              "type": "string",
              "pattern": "^\\.orch/state/snapshot-[0-9]{8}\\.json$"
            },
            "summary": {
              "type": "object",
              "properties": {
                "total_tasks": {"type": "integer", "minimum": 0},
                "current_phase": {
                  "oneOf": [{"type": "null"}, {"type": "string"}]
                },
                "by_status": {
                  "type": "object",
                  "patternProperties": {
                    "^(pending|ready|running|scheduled|completed|failed|dlq|cancelled)$": {
                      "type": "integer",
                      "minimum": 0
                    }
                  }
                }
              }
            },
            "state_hash": {
              "type": "string",
              "pattern": "^[0-9a-f]{64}$",
              "description": "SHA-256 of canonical state JSON (optional, for verification)"
            }
          }
        }
      }
    }
  ]
}
```

### 4.5 `log_recovered`

Emitido após recovery manual de corrupção.

```json
{
  "$id": "https://example.com/orch/events/log_recovered.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "log_recovered"},
        "task_id": {"const": null},
        "agent": {"const": "operator"},
        "data": {
          "type": "object",
          "required": ["seq_truncated_from", "events_removed", "operator", "corrupt_file_path"],
          "additionalProperties": false,
          "properties": {
            "seq_truncated_from": {"type": "integer", "minimum": 1},
            "seq_truncated_to": {"type": "integer", "minimum": 1},
            "events_removed": {"type": "integer", "minimum": 1},
            "operator": {"type": "string", "minLength": 1},
            "corrupt_file_path": {
              "type": "string",
              "pattern": "^\\.orch/log\\.jsonl\\.corrupt\\..+$"
            },
            "hash_before_truncation": {
              "type": "string",
              "pattern": "^[0-9a-f]{64}$"
            },
            "hash_after_truncation": {
              "type": "string",
              "pattern": "^[0-9a-f]{64}$"
            }
          }
        }
      }
    }
  ]
}
```

### 4.6 `preflight_failed`

```json
{
  "$id": "https://example.com/orch/events/preflight_failed.json",
  "allOf": [
    {"$ref": "event-base.json"},
    {
      "properties": {
        "event_type": {"const": "preflight_failed"},
        "task_id": {"const": null},
        "agent": {"const": "orchestrator"},
        "data": {
          "type": "object",
          "required": ["failed_checks", "total_count", "passed_count"],
          "additionalProperties": false,
          "properties": {
            "failed_checks": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["check", "reason"],
                "properties": {
                  "check": {"type": "string"},
                  "reason": {"type": "string"}
                }
              },
              "minItems": 1
            },
            "passed_count": {"type": "integer", "minimum": 0},
            "total_count": {"type": "integer", "minimum": 1},
            "claude_code_version": {"type": "string"},
            "python_version": {"type": "string"}
          }
        }
      }
    }
  ]
}
```

---

## 5. Tipos comuns reutilizados

### 5.1 Blob reference (payload externalizado)

Quando evento tem payload > 3500 bytes, `data` é substituído por esta estrutura:

```json
{
  "$id": "https://example.com/orch/common/blob_ref.json",
  "type": "object",
  "required": ["_blob_ref", "_size", "_blob_hash"],
  "additionalProperties": false,
  "properties": {
    "_blob_ref": {
      "type": "string",
      "pattern": "^\\.orch/blobs/evt_[0-9A-HJKMNP-TV-Z]{26}\\.json$"
    },
    "_size": {
      "type": "integer",
      "minimum": 3501
    },
    "_blob_hash": {
      "type": "string",
      "pattern": "^[0-9a-f]{64}$",
      "description": "SHA-256 of blob content for integrity verification"
    }
  }
}
```

**Importante**: ao carregar, sempre verificar que hash do blob bate com `_blob_hash`.

---

## 6. Enumerações

### 6.1 Task status

Derivados pelo reducer (não aparecem em eventos diretamente):

```
pending | ready | running | scheduled | completed | failed | dlq | cancelled
```

### 6.2 Phase status

```
pending | active | exit_approved | completed | paused
```

### 6.3 Tiers

```
critical | standard | bulk
```

### 6.4 Códigos de escalação

Ver `escalation.data.code` em §4.2 para lista completa (E01-E12).

---

## 7. Validação em Python

### 7.1 Abordagem com stdlib (recomendada)

Validação básica usando `json.JSONDecoder` + verificações manuais (mais rápida, zero deps):

```python
# .claude/lib/event_validator.py
from __future__ import annotations

import json
import re
from typing import Any

ULID_PATTERN = re.compile(r"^evt_[0-9A-HJKMNP-TV-Z]{26}$")
TASK_ID_PATTERN = re.compile(r"^t_[0-9]+$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TS_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$")

VALID_EVENT_TYPES = {
    "task_created", "task_claimed", "task_progress",
    "task_completed", "task_failed",
    "task_scheduled_retry", "task_retried", "task_dlq",
    "phase_declared", "phase_entered",
    "phase_exit_criterion_met", "phase_exit_approved",
    "phase_transitioned", "phase_paused", "phase_resumed",
    "circuit_breaker_tripped",
    "escalation", "human_response",
    "snapshot", "log_recovered", "preflight_failed",
}

VALID_TIERS = {"critical", "standard", "bulk"}


class EventValidationError(Exception):
    pass


def validate_event_envelope(event: dict[str, Any]) -> None:
    """Validates base event envelope. Raises EventValidationError."""
    required = {"seq", "event_id", "ts", "agent", "event_type",
                "attempt", "data", "prev_hash", "hash"}
    missing = required - set(event.keys())
    if missing:
        raise EventValidationError(f"Missing required fields: {missing}")

    if not isinstance(event["seq"], int) or event["seq"] < 1:
        raise EventValidationError(f"Invalid seq: {event['seq']}")

    if not ULID_PATTERN.match(event["event_id"]):
        raise EventValidationError(f"Invalid event_id: {event['event_id']}")

    if not TS_PATTERN.match(event["ts"]):
        raise EventValidationError(f"Invalid ts format: {event['ts']}")

    if event["event_type"] not in VALID_EVENT_TYPES:
        raise EventValidationError(f"Unknown event_type: {event['event_type']}")

    if event["task_id"] is not None and not TASK_ID_PATTERN.match(event["task_id"]):
        raise EventValidationError(f"Invalid task_id: {event['task_id']}")

    if not isinstance(event["attempt"], int) or event["attempt"] < 1:
        raise EventValidationError(f"Invalid attempt: {event['attempt']}")

    if not isinstance(event["data"], dict):
        raise EventValidationError("data must be object")

    if event["prev_hash"] != "GENESIS" and not HASH_PATTERN.match(event["prev_hash"]):
        raise EventValidationError(f"Invalid prev_hash: {event['prev_hash']}")

    if not HASH_PATTERN.match(event["hash"]):
        raise EventValidationError(f"Invalid hash: {event['hash']}")


def validate_task_created(event: dict[str, Any]) -> None:
    """Type-specific validation for task_created."""
    validate_event_envelope(event)
    data = event["data"]

    required = {"phase", "tier", "type", "spec", "deps"}
    missing = required - set(data.keys())
    if missing:
        raise EventValidationError(f"task_created missing: {missing}")

    if data["tier"] not in VALID_TIERS:
        raise EventValidationError(f"Invalid tier: {data['tier']}")

    if not isinstance(data["deps"], list):
        raise EventValidationError("deps must be array")

    for dep in data["deps"]:
        if not isinstance(dep, str) or not TASK_ID_PATTERN.match(dep):
            raise EventValidationError(f"Invalid dep: {dep}")


# ... uma função de validação por tipo de evento
```

### 7.2 Abordagem com jsonschema (opcional)

Se o projeto aceita adicionar dependência, `jsonschema` é mais expressivo:

```python
from jsonschema import validate, ValidationError
import json

with open(".claude/specs/schemas/task_created.json") as f:
    schema = json.load(f)

try:
    validate(instance=event, schema=schema)
except ValidationError as e:
    raise EventValidationError(str(e))
```

**Recomendação**: stdlib em runtime (hot path: append_event), `jsonschema` em testes (melhor mensagem de erro).

### 7.3 Dispatcher de validação

```python
def validate_event(event: dict[str, Any]) -> None:
    """Routes to type-specific validator based on event_type."""
    validate_event_envelope(event)

    validators = {
        "task_created": validate_task_created,
        "task_claimed": validate_task_claimed,
        "task_progress": validate_task_progress,
        "task_completed": validate_task_completed,
        "task_failed": validate_task_failed,
        "task_scheduled_retry": validate_task_scheduled_retry,
        "task_retried": validate_task_retried,
        "task_dlq": validate_task_dlq,
        "phase_declared": validate_phase_declared,
        "phase_entered": validate_phase_entered,
        "phase_exit_criterion_met": validate_phase_exit_criterion_met,
        "phase_exit_approved": validate_phase_exit_approved,
        "phase_transitioned": validate_phase_transitioned,
        "phase_paused": validate_phase_paused,
        "phase_resumed": validate_phase_resumed,
        "circuit_breaker_tripped": validate_circuit_breaker_tripped,
        "escalation": validate_escalation,
        "human_response": validate_human_response,
        "snapshot": validate_snapshot,
        "log_recovered": validate_log_recovered,
        "preflight_failed": validate_preflight_failed,
    }

    validator = validators[event["event_type"]]
    validator(event)
```

---

## 8. Pontos críticos de implementação

### 8.1 Validação em runtime vs. testes

- **Runtime (append_event)**: validação mínima para detectar bugs cedo, mas rápida. Use envelope + type dispatch.
- **Testes**: validação completa com jsonschema ou manual detalhada. Inclua fixture de evento inválido para cada regra.

### 8.2 Canonicalização para hashing

O campo `hash` é calculado sobre o evento **sem** o campo `hash`, com chaves **ordenadas**:

```python
def canonical_json(event: dict) -> str:
    """Canonical serialization for hashing. Excludes hash field."""
    event_for_hash = {k: v for k, v in event.items() if k != "hash"}
    return json.dumps(event_for_hash, sort_keys=True, separators=(",", ":"))
```

Separadores sem espaço reduzem tamanho e garantem determinismo.

### 8.3 Schema evolution

Se precisar adicionar campos:

- **Campos opcionais novos**: ok, não quebra eventos antigos
- **Campos required novos**: quebra; adicione como opcional inicialmente
- **Remoção de campos**: quebra; marque como deprecated, mantenha por N versões
- **Mudança de tipo**: quebra total; use novo event_type

### 8.4 Tamanho dos eventos

Envelope sem `data`: ~400 bytes. Deixe ~3000 bytes para `data` para caber no limite de 3500 inline. Se precisar mais, use blob externalizado (§5.1).

---

## 9. Checklist para implementador

Ao implementar append_event e validators, confirme:

- [ ] Envelope obrigatório: 9 campos, todos validados
- [ ] Padrões regex para event_id, task_id, hashes, timestamps
- [ ] Dispatch por event_type para validação específica
- [ ] Campo `phase` obrigatório em data de eventos de task
- [ ] Transições de attempt: monotônicas por (task_id, event_type)
- [ ] `task_id = null` apenas em eventos globais
- [ ] `prev_hash = GENESIS` apenas no primeiro evento
- [ ] Canonicalização para hash exclui campo `hash`, chaves ordenadas
- [ ] Mensagens de erro claras apontando o campo problemático
- [ ] Testes com fixtures válidos E inválidos para cada tipo
