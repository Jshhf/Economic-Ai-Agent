# ADR: Skill-Centric Runtime

## Status

Accepted

## Context

The original project ran a mostly fixed economic analysis flow. That worked for a single demo path, but it limited reuse and made the runtime look less like a platform.

## Decision

Introduce a `Skill` layer above tools and below the overall runtime entrypoint.

Each skill defines:

- execution scenario
- available tools
- whether RAG is enabled
- which MCP sources can be used
- expected output style

## Consequences

- the runtime can support multiple analysis modes without duplicating the whole agent graph
- the UI and API can expose skill selection directly
- the project is easier to explain as an extensible Agent platform
