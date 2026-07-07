#!/usr/bin/env python3
"""classify_stack.py — deterministic fe|be|fullstack classifier (fix P0-1).

The SDD front/back/both decision used to be a single boolean (`ui_task`) derived
by LLM-interpreted keyword prose with an UNCONDITIONAL backend-suppression rule:
*any* backend keyword forced `ui_task=false` even when UI signals were present,
silently collapsing fullstack requirements to back-only. This script replaces
that prose with a deterministic, co-presence-aware classifier, so the most
consequential branch of the pipeline is Python-owned (not LLM-owned) — the same
"move the decision into code" pattern the project already applies via sm_runner.

Decision rule (co-presence aware):
    ui  AND  backend  -> fullstack
    ui  AND  not be   -> fe
    not ui AND backend -> be
    not ui AND not be  -> fullstack   (conservative default: never silently
                                       drop the front leg; the asymmetric cost
                                       of a missing front spec dominates the
                                       cost of an unused one — recoverable at
                                       the E99 gate via force_backend_only)

`ui_task` is DERIVED: ui_task = stack in {"fe", "fullstack"}. The orchestrator
keeps reading `triage.ui_task` unchanged (back-compat); `stack` is the new
first-class field that orchestrator-sdd and the handoff guard consume.

Usage:
    classify_stack.py --requirement "<text>"

Output (exit 0; exit 1 only on internal error):
    {"stack": "fullstack", "ui_task": true,
     "ui_signals": ["page"], "backend_signals": ["api"],
     "rationale": "ui+backend signals present -> fullstack"}
"""
from __future__ import annotations

import argparse
import json
import re
import sys

# --------------------------------------------------------------------------- #
# Signal vocabularies (bilingual EN + PT-BR — the lab's runtime context is     #
# PT-BR). Kept deliberately inclusive on the UI side and conservative on the   #
# backend side: a false UI hit only ever upgrades be->fullstack (safe), while  #
# the dangerous direction (dropping the front leg) is guarded by the default.  #
# Genuinely ambiguous tokens (card/table = UI or DB; route/rota = FE or BE)    #
# are intentionally excluded to avoid mojibake classifications.                #
# --------------------------------------------------------------------------- #
UI_SIGNALS: tuple[str, ...] = (
    # EN
    "component", "components", "screen", "screens", "page", "pages", "layout",
    "modal", "dialog", "form", "forms", "button", "buttons", "sidebar",
    "navigation", "navbar", "menu", "header", "footer", "theme", "typography",
    "icon", "icons", "tooltip", "dropdown", "checkbox", "stepper", "drawer",
    "dashboard", "wizard", "frontend", "front-end", "ui", "ux", "view", "views",
    "widget", "spacing", "padding", "hover", "css", "responsive", "mobile",
    "design system", "design-system", "landing", "onboarding screen",
    # PT-BR
    "tela", "telas", "página", "pagina", "páginas", "paginas", "formulário",
    "formulario", "botão", "botao", "componente", "componentes", "navegação",
    "navegacao", "cabeçalho", "cabecalho", "rodapé", "rodape", "ícone", "icone",
    "painel", "responsivo", "tema",
)

BACKEND_SIGNALS: tuple[str, ...] = (
    # EN
    "api", "apis", "endpoint", "endpoints", "service", "services", "repository",
    "migration", "migrations", "cron", "background job", "webhook", "webhooks",
    "database", "queue", "microservice", "microservices", "backend", "back-end",
    "persistence", "sql", "orm", "rest api", "grpc", "message broker", "kafka",
    "rabbitmq", "scheduler", "integration",
    # PT-BR
    "serviço", "servico", "serviços", "servicos", "repositório", "repositorio",
    "migração", "migracao", "banco de dados", "fila", "filas", "webhook",
    "persistência", "persistencia", "integração", "integracao", "agendamento",
    "autenticação", "autenticacao",
)

# A "word char" for boundary purposes includes ASCII alphanumerics plus the
# Latin-1 accented range, so "api" does not match inside "rapid"/"apiário" and
# "tela" does not match inside "etiqueta".
_WORD = r"0-9A-Za-zÀ-ÿ"


def _compile(terms: tuple[str, ...]) -> list[tuple[str, re.Pattern[str]]]:
    out: list[tuple[str, re.Pattern[str]]] = []
    for term in terms:
        pattern = re.compile(
            rf"(?<![{_WORD}]){re.escape(term)}(?![{_WORD}])",
            re.IGNORECASE,
        )
        out.append((term, pattern))
    return out


_UI_PATTERNS = _compile(UI_SIGNALS)
_BACKEND_PATTERNS = _compile(BACKEND_SIGNALS)


def _matches(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    found: list[str] = []
    for term, pattern in patterns:
        if term not in found and pattern.search(text):
            found.append(term)
    return found


def _confidence(stack: str, ui: list[str], backend: list[str]) -> tuple[str, str]:
    """Confidence in the classification — advisory only, NEVER changes `stack`
    (fix F5). The decision stays deliberately conservative (P0-1: never silently
    drop the front leg); confidence exists so the E99 gate can steer a fast human
    override instead of treating every fullstack as an equal impasse.

    low when the fullstack decision rests on weak evidence:
      - no signals at all (pure conservative default), or
      - a lone minority signal on one side amid a dominant other side
        (e.g. one incidental UI word in a backend-heavy requirement — the exact
        false 'fullstack' the report hit). high otherwise.
    """
    if stack in ("fe", "be"):
        return "high", "single-sided signals -> clear classification"
    # stack == "fullstack"
    if not ui and not backend:
        return "low", "no signals -> defaulted to fullstack; confirm the real stack at the gate"
    if len(ui) == 1 and len(backend) >= 2:
        return "low", ("backend-dominant with a single UI signal "
                       f"({ui[0]!r}) -> likely backend-only; consider force_backend_only")
    if len(backend) == 1 and len(ui) >= 2:
        return "low", ("ui-dominant with a single backend signal "
                       f"({backend[0]!r}) -> confirm the backend leg is really needed")
    return "high", "ui+backend both clearly present -> fullstack"


def classify(requirement: str) -> dict:
    """Pure function: requirement text -> stack decision envelope."""
    text = requirement or ""
    ui = _matches(text, _UI_PATTERNS)
    backend = _matches(text, _BACKEND_PATTERNS)

    if ui and backend:
        stack, rationale = "fullstack", "ui+backend signals present -> fullstack"
    elif ui and not backend:
        stack, rationale = "fe", "ui signals only -> fe"
    elif backend and not ui:
        stack, rationale = "be", "backend signals only -> be"
    else:
        stack, rationale = "fullstack", "no signals -> fullstack (conservative default)"

    confidence, confidence_hint = _confidence(stack, ui, backend)

    return {
        "stack": stack,
        "ui_task": stack in ("fe", "fullstack"),
        "ui_signals": ui,
        "backend_signals": backend,
        "rationale": rationale,
        "confidence": confidence,
        "confidence_hint": confidence_hint,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Deterministically classify a requirement as fe|be|fullstack (stdlib only)."
    )
    ap.add_argument("--requirement", required=True, help="Requirement text to classify.")
    args = ap.parse_args()
    print(json.dumps(classify(args.requirement)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — surface a parseable error, never crash silently
        print(json.dumps({"error": "internal_error", "detail": str(exc)}), file=sys.stderr)
        sys.exit(1)
