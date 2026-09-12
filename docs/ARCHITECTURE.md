# NEXUS R&D Factory — Architecture

## System Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    INFERENCE LAYER                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Tier 1    │  │   Tier 2    │  │   Tier 3    │         │
│  │  Primary    │──│  Fallback   │──│  Emergency  │         │
│  │  Pool       │  │  Pool       │  │  Pool       │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│       nginx reverse proxy :8000/v1                          │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  ORCHESTRATION LAYER                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │    Dify     │  │   CrewAI    │  │  LangGraph  │         │
│  │   Visual    │  │   Swarm     │  │  Stateful   │         │
│  │  Pipelines  │  │    DAG      │  │   Loops     │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                 EXECUTION LAYER                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  OpenHands + E2B/Daytona Sandboxes                  │   │
│  │  • Isolated code execution                          │   │
│  │  • Resource limits (CPU, memory, network)           │   │
│  │  • Circuit breaker (3-strike rule)                  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  CONTEXT LAYER                              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │  GitHub │ │ Notion  │ │Airtable │ │ Obsidian│          │
│  │   MCP   │ │   MCP   │ │   MCP   │ │   MCP   │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Operational Modes

### SCALPEL MODE
- Direct pool access
- Single-shot execution
- Latency: <100ms
- Use: syntax fixes, API lookups, code snippets

### SLEDGEHAMMER MODE
- Multi-agent DAG
- MapReduce distribution
- Parallel execution
- Use: large refactors, research tasks, system design

## Circuit Breaker Protocol

```
Attempt 1 ──► Failure ──► Analyze ──► Retry with fix
Attempt 2 ──► Failure ──► Analyze ──► Adjust parameters
Attempt 3 ──► Failure ──► Root cause analysis ──► Escalate
```

## Security Model

- All code execution in air-gapped sandboxes
- No host filesystem access
- Network isolation (egress-only via proxy)
- Secrets via environment variables only
