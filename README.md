# fast-azure-agent-app

**Production-ready multi-agent infrastructure on Azure**

## Why This Project

Building an LLM agent with tool-calling is easy. Building a complete production stack—chat UI, conversation history, memory management, observability, authentication, multi-agent workflows, async API backend, and SSE streaming—takes significant engineering effort.

This project provides all that infrastructure out-of-the-box. You focus only on:
- **Prompt engineering** - Define your agent's behavior
- **Tool implementation** - Write the functions your agents call

**Think of it as cookiecutter for AI agents**—but instead of filling out a config file, you have a conversation. Run `/onboard` in Claude Code, describe your domain and agents in natural language, and get working code generated automatically.

## Features

- **Chat UI** - Conversation history, model selection, thinking panel
- **Multi-agent Workflows** - Triage (classification routing) and Dynamic (flexible orchestration) modes
- **Chat History** - PostgreSQL + Redis write-through caching
- **Memory** - Rolling window + LLM summarization for long conversations
- **Observability** - Azure Application Insights / local Aspire dashboard
- **Authentication** - Azure App Service Easy Auth
- **SSE Streaming** - Real-time agent execution feedback
- **Claude Code Skills** - Rapid agent scaffolding via `/onboard`

## Architecture

<!-- TODO: Add architecture diagrams -->

- [ ] Azure Architecture Diagram
- [ ] Triage/Dynamic Workflow Diagram
- [ ] Storage Strategy Diagram
- [ ] Memory Design Diagram

**Tech Stack:** FastAPI | Azure PostgreSQL | Azure Redis | Microsoft Agent Framework | Azure OpenAI

## Quick Start

### 1. Deploy Azure Infrastructure

```bash
# Create resource group
./deployment/deploy_infra.sh rg

# Deploy full infrastructure
./deployment/deploy_infra.sh app --postgres-password <your-password>

# Initialize database
./deployment/deploy_script.sh db <your-password>
```

### 2. Configure Key Vault

- Add access policy for your identity
- Set `AZURE-OPENAI-API-KEY` secret

### 3. Local Development

```bash
# Install dependencies
uv sync

# Copy environment config
cp env.example .env

# Enable demo mode for testing
# Set USE_DEMO_OPSAGENT=true in .env

# Run development server
uv run uvicorn app.main:app --reload
```

### 4. Create Your Agent

```bash
# In Claude Code, run:
/onboard

# Follow prompts to describe your domain and agents
# Set USE_DEMO_OPSAGENT=false in .env
```

### 5. Build & Deploy

```bash
./deployment/build_docker.sh
# Push to ACR and deploy
```

## Create Your Agent with `/onboard`

The `/onboard` skill guides you through agent creation:

1. Run `/onboard` in Claude Code
2. Answer questions about your domain and required agents
3. Get generated files:
   - Sub-agent configurations
   - Tool stubs
   - 6 orchestration prompts
4. Implement your tool logic
5. Run and iterate

## Project Structure

```
app/
├── core/           # Internal building blocks (SSE utilities)
├── infrastructure/ # External services (PostgreSQL, Redis, Key Vault)
├── routes/         # FastAPI endpoints
├── schemas/        # Pydantic models
├── agent_factory/  # Agent framework (/onboard generates code here)
│   ├── agents/     # Agent implementations
│   ├── workflows/  # Triage & dynamic workflows
│   ├── prompts/    # System prompts
│   ├── factory.py  # Creates agents from config
│   └── subagent_registry.py  # Agent registration
├── opsagent/       # Demo agent (reference implementation)
├── memory_agent/   # Conversation memory management
├── dependencies.py # Dependency injection
└── config.py       # Environment configuration
```

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `RESOURCE_PREFIX` | Azure service name prefix | - |
| `CHAT_HISTORY_MODE` | Storage: `local`, `postgres`, `redis` | `local` |
| `DYNAMIC_PLAN` | Enable dynamic workflow | `false` |
| `USE_DEMO_OPSAGENT` | Use demo agent for testing | `false` |
| `MEMORY_ROLLING_WINDOW` | Recent messages to keep | `14` |
| `MEMORY_SUMMARIZE_THRESHOLD` | Start summarizing after N rounds | `4` |
| `SHOW_FUNC_RESULT` | Show function args/results in UI | `false` |

## Development Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn app.main:app --reload

# Add package
uv add <package-name>

# Run production
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Deployment

```bash
# Deploy infrastructure
./deployment/deploy_infra.sh rg              # Resource group only
./deployment/deploy_infra.sh app --postgres-password <password>

# Build container
./deployment/build_container.sh

# Deploy application
./deployment/deploy_script.sh
```
