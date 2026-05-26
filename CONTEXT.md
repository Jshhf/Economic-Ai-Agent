# Context Glossary

## Agent

A role-oriented runtime component that makes decisions and coordinates execution. In this repo, agents delegate work rather than directly owning every implementation detail.

## Tool

A narrow, structured capability used by an agent or skill to inspect the dataset or produce analysis artifacts.

## Skill

A task-level orchestration unit that combines agent behavior, tools, RAG retrieval, MCP sources, and output expectations for a specific scenario.

## RAG Source

A retrievable knowledge source used to enrich analysis with locally indexed documents or curated reference text.

## MCP Source

A standardized external capability provider accessed through an internal adapter and normalized into platform-owned schemas.

## Job

A single runtime execution unit created from an uploaded or local CSV file plus a selected skill.

## Artifact

A persisted output generated during a job, such as an evidence pack, chart payloads, a final report, or source references.

## Trace

The recorded execution trail of a job, including agent runs, runtime calls, metrics, sources, and failure classification.
