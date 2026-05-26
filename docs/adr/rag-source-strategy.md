# ADR: RAG Source Strategy

## Status

Accepted

## Context

The project needs stronger knowledge grounding, but the main product story should remain an Agent runtime platform rather than a generic knowledge chatbot.

## Decision

Use RAG as an enhancement layer only.

The first release combines:

- local markdown knowledge in `knowledge/`
- external context returned through MCP-style adapters

RAG is used to support analysis quality, source attribution, and policy-style briefing. It is not exposed as a standalone chat product.

## Consequences

- the project gains explainability and richer references
- the runtime can distinguish between structured analysis and retrieved context
- the repo keeps its main focus on task-oriented analysis instead of Q&A
