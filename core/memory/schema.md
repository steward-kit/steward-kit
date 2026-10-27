# Memory schema

A memory is one markdown file with this frontmatter:

    ---
    name: kebab-case-id
    description: one line saying when this memory applies
    scope: global | profile | machine
    type: feedback | project | reference | user
    ---

The body is the lesson or fact in plain words.

## Scope

- global: how to work. Shared by every profile and machine, so it is part of core.
- profile: facts about one context, plus the evidence behind them.
- machine: facts about one host.

## Rules for global files

- Carry the lesson with a short reason in plain words.
- Never put a quote in quote marks. Paraphrase it.
- Never include a job identifier: no employer, requisition, application or ticket reference.
- Evidence and verbatim rulings stay in profile scope. If a lesson only makes sense with them attached, it is not global yet.

## Types

- feedback: a correction or a confirmed way of working.
- project: work in flight and its state.
- reference: where something lives.
- user: who the principal is and how they like to work.

Global files are part of core, so the lint covers them: a global memory that leaks a profile identifier fails it.
