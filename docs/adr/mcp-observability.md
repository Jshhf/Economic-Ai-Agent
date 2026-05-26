# ADR: MCP Adapters and Observability Stack

## Status

Accepted

## Context

External capabilities and trace visibility are both important to the platform story. Ad hoc integrations would make the runtime harder to extend, and plain SQLite logs would undersell the engineering maturity of the project.

## Decision

Use an internal MCP adapter registry for external capabilities and treat observability as a first-class runtime concern.

The runtime:

- normalizes external sources through MCP adapters
- classifies runtime calls into `tool`, `rag`, and `mcp`
- persists references and metrics locally
- leaves clear seams for `OpenTelemetry`, `Langfuse`, and `Prometheus/Grafana`

## Consequences

- external integrations are easier to grow without rewriting the runtime
- traces are easier to explain in interviews
- the project has a credible path from local demo observability to fuller production instrumentation
