# NEXUS Open-Source R&D Factory v4.0

Self-hosted, zero-cost, resilient AI R&D infrastructure.

## Architecture

| Layer | Component | Purpose |
|-------|-----------|---------|
| Inference | 3-Tier Keyless Proxy Pool | LLM routing via `localhost:8000/v1`, TLS/JA3 rotation |
| Orchestration | Dify, CrewAI, LangGraph | Visual pipelines, multi-agent swarms, stateful graphs |
| Engineering | OpenHands + E2B/Daytona | Autonomous code execution in sandboxes |
| Context | MCP Servers | GitHub, Notion, Airtable, Obsidian integration |

## Quick Start

```bash
# 1. Start inference proxy pool
cd inference-proxy && docker-compose up -d

# 2. Launch orchestration stack
cd orchestration/dify && docker-compose up -d

# 3. Initialize MCP servers
cd mcp-servers && npm install && npm run start
```

## Operational Modes

- **SCALPEL**: Single-shot code fixes, API lookups
- **SLEDGEHAMMER**: Multi-agent DAG workflows, MapReduce operations

## Circuit Breaker

3-strike rule: analyze → rewrite → retry → escalate with root cause.
