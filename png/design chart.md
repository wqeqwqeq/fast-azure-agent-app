## triage_workflow

```mermaid
graph LR
    Start([User Query]) --> Triage[Triage Plan Agent<br/>Query Router]
    Triage --> Decision{Route Query}

    Decision -->|Reject| Reject([Rejection Response])
    Decision -->|Has Tasks| Dispatcher[Dispatcher<br/>Filter by triage.tasks]

    subgraph "Concurrent execution"
        SNAgent[ServiceNow Agent<br/>ITSM Operations]
        LAAgent[Log Analytics Agent<br/>ADF Monitoring]
        SHAgent[Service Health Agent<br/>Health Checks]
    end

    Dispatcher -->|"fan-out<br/>(when relevant)"| SNAgent
    Dispatcher -->|"fan-out<br/>(when relevant)"| LAAgent
    Dispatcher -->|"fan-out<br/>(when relevant)"| SHAgent

    SNAgent -->|fan-in| Summary[Aggregator<br/>Summary Agent]
    LAAgent -->|fan-in| Summary
    SHAgent -->|fan-in| Summary

    Summary --> End([Response to User])

    classDef triageClass fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef agentClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef decisionClass fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    classDef workflowClass fill:#fff3e0,stroke:#e65100,stroke-width:2px

    class Triage triageClass
    class SNAgent,LAAgent,SHAgent agentClass
    class Decision,Reject decisionClass
    class Dispatcher,Summary workflowClass
```

---

## dynamic_workflow

```mermaid
graph LR
    Start([User Query]) --> Plan

    subgraph Triage["Triage Executor"]
        Plan[Plan Agent]
        Replan[Replan Agent]
    end

    Plan --> Replan
    Plan --> Decision{Route}
    Replan --> Decision

    linkStyle 1 stroke-width:0px

    Decision -->|Reject| Reject([Rejection])
    Decision -->|Clarify| Clarify([Clarification])
    Decision -->|Execute| Orchestrator[Step-based Orchestrator<br/>See patterns below]

    Orchestrator --> Review[Review Agent]
    Review -->|Complete| Summary[Summary Agent]
    Review -->|Incomplete| Replan
    Replan -->|"Reject Review"| Summary

    Summary --> End([Response])

    classDef triageClass fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef decisionClass fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    classDef workflowClass fill:#fff3e0,stroke:#e65100,stroke-width:2px

    class Plan,Replan triageClass
    class Decision,Reject,Clarify decisionClass
    class Orchestrator,Review,Summary workflowClass
```

### Examples of Step-based Execution Patterns (determined by Plan/Replan Agent)

**Pattern A: All Parallel**
```mermaid
graph LR
    Start([Start]) --> A1[Step1: ServiceNow]
    Start --> A2[Step1: Log Analytics]
    Start --> A3[Step1: Service Health]
    A1 --> End([End])
    A2 --> End
    A3 --> End

    classDef agentClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    class A1,A2,A3 agentClass
```

**Pattern B: Sequential then Parallel**
```mermaid
graph LR
    Start([Start]) --> B1[Step1: ServiceNow]
    B1 --> B2[Step2: Log Analytics]
    B1 --> B3[Step2: Service Health]
    B2 --> End([End])
    B3 --> End

    classDef agentClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    class B1,B2,B3 agentClass
```

**Pattern C: All Sequential**
```mermaid
graph LR
    Start([Start]) --> C1[Step1: ServiceNow]
    C1 --> C2[Step2: Log Analytics]
    C2 --> C3[Step3: Service Health]
    C3 --> End([End])

    classDef agentClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    class C1,C2,C3 agentClass
```

**Pattern D: Sequential → Parallel → Sequential**
```mermaid
graph LR
    Start([Start]) --> D1[Step1: ServiceNow]
    D1 --> D2[Step2: Log Analytics]
    D1 --> D3[Step2: Service Health]
    D2 --> D4[Step3: ServiceNow]
    D3 --> D4
    D4 --> End([End])

    classDef agentClass fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    class D1,D2,D3,D4 agentClass
```
And more...

**Key Differences from triage_workflow:**
1. **Triage Executor** handles both Plan (initial) and Replan (after review) modes
2. **Orchestrator** executes steps sequentially, tasks within same step run in parallel
3. **Review Agent** checks if results fully answer the query
4. **Review Loop** - if incomplete, sends back to Triage for replan decision
5. **Triage can reject review** - if review feedback is invalid, skip retry and go to Summary
6. **max_iterations=10** prevents infinite loops

---

## write_through_cache

### Write Flow

```mermaid
graph LR
    User([User Login]) --> CreateChat[Create Chat<br/>POST /conversations]
    CreateChat --> CreateMsg[Create Message<br/>POST /conversations/id/messages]
    CreateMsg --> PG[(PostgreSQL<br/>Source of Truth)]

    PG --> CT["conversation table<br/>• conv_id (uuid[:8])<br/>• user_id<br/>• title ('New chat')<br/>• model<br/>• created_at<br/>• last_modified"]
    PG --> MT["message table<br/>• conv_id<br/>• msg_id<br/>• role<br/>• content<br/>• time"]

    PG -->|Write Success| Redis[(Redis Cache<br/>TTL: 30min)]
    Redis --> Done([Done])

    classDef dbClass fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    classDef cacheClass fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef tableClass fill:#e3f2fd,stroke:#1565c0,stroke-width:1px

    class PG dbClass
    class Redis cacheClass
    class CT,MT tableClass
```

### Read Flow

```mermaid
graph LR
    User([GET /conversations/id]) --> Redis[(Redis Cache)]
    Redis -->|Hit| Return([Return Data])
    Redis -->|Miss| PG[(PostgreSQL)]
    PG --> Backfill[Backfill Cache]
    Backfill --> Redis

    classDef dbClass fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    classDef cacheClass fill:#fff3e0,stroke:#e65100,stroke-width:2px

    class PG dbClass
    class Redis cacheClass
```

**Return Fields:**
| Field | Description |
|-------|-------------|
| `id` | conversation_id |
| `title` | chat title |
| `model` | LLM model |
| `created_at` | creation timestamp |
| `last_modified` | last update timestamp |
| `agent_level_llm_overwrite` | optional LLM override |
| `messages[]` | array of `{role, content, time}` |

**Write-Through Pattern:**
1. **Write Path**: All writes go to PostgreSQL first (source of truth), then update Redis cache
2. **Read Path**: Check Redis first → on cache miss, read from PostgreSQL and populate cache
3. **TTL**: Redis cache expires after 30 minutes to prevent stale data

| Table | Fields |
|-------|--------|
| **conversation** | `conversation_id`, `user_id`, `title`, `model`, `created_at`, `last_modified` |
| **message** | `conversation_id`, `message_id`, `role`, `content`, `time` |


