---
name: onboard
description: Interactive agent factory onboarding. Use when the user runs /onboard or wants to create multi-agent applications, set up new specialized agents for a domain, or generate sub-agent configurations and tool stubs.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Task, AskUserQuestion
argument-hint: Optional domain name (e.g., "HR Assistant")
---

# Agent Factory Onboarding Skill

When the user runs `/onboard`, follow this process to create a new agent application.

## Overview

This skill helps create a multi-agent application by:
1. Collecting configuration (domain + sub-agents)
2. Generating sub-agent files using templates in `./templates/`
3. **Modifying 6 orchestration agent prompts in parallel** using Task subagents

See `./examples/hr_assistant.md` for a complete example.

---

## Phase 1: Collect Configuration

### Step 1: Domain Configuration
Ask: "What domain does this assistant serve? Please provide:
1. **Domain name** (e.g., 'HR Assistant', 'IT Support')
2. **Description** (one sentence explaining what the assistant helps with)"

### Step 2: Sub-Agents
For each sub-agent, collect:
- **key**: snake_case identifier (e.g., `leave`, `payroll`)
- **name**: display name (e.g., 'leave-agent')
- **description**: one-line description
- **capabilities**: list of things this agent can do
- **tools**: list of tool functions with name and description
- **use_cases**: 2-3 use cases with example queries
- **when_to_use**: scenarios where triage should route here
- **when_not_to_use**: scenarios where another agent is better

Ask: "Now let's define your specialized agents. For each agent, provide key, name, description, capabilities, tools, use cases, when to route here, and when NOT to route here."

Continue: "Do you have another agent to add? (yes/no)"

### Step 3: Confirm Configuration
Present a summary and ask: "Does this look correct? (yes/no)"

---

## Phase 2: Generate Sub-Agent Files

After confirmation, generate using templates from `./templates/`:

1. **`app/agent_factory/subagent_config.py`** - Use template: `./templates/subagent_config.py.md`
2. **`app/agent_factory/agents/sub_agents/{key}_agent.py`** - Use template: `./templates/sub_agent.py.md`
3. **`app/agent_factory/agents/sub_agents/tools/{key}_tools.py`** - Use template: `./templates/tools.py.md`

---

## Phase 3: Modify Orchestration Agent Prompts (PARALLEL)

After generating sub-agent files, modify the 6 orchestration agent prompts **in parallel** using the Task tool.

### Critical: Use Parallel Task Subagents

Launch **6 Task tool calls in a single message**. Each subagent modifies one orchestration agent file independently.

### Orchestration Agents and Placeholders

| Agent | File | Key Placeholders |
|-------|------|------------------|
| Triage | `triage_agent.py` | `{domain_purpose}`, `{agent_summaries}`, `{routing_examples}`, `{decision_guidelines}` |
| Plan | `plan_agent.py` | `{domain_purpose}`, `{agent_tools_summary}`, `{planning_examples}`, `{parallel_vs_sequential_guidance}` |
| Replan | `replan_agent.py` | `{agent_tools_summary}`, `{retry_examples}`, `{when_to_retry_vs_complete}` |
| Review | `review_agent.py` | `{completeness_criteria}`, `{domain_specific_quality_checks}`, `{review_examples}` |
| Clarify | `clarify_agent.py` | `{domain_purpose}`, `{capabilities_summary}`, `{clarification_examples}` |
| Summary | `summary_agent.py` | `{domain_purpose}`, `{formatting_guidelines}`, `{response_examples}` |

### How to Execute

Use a single message with 6 Task tool calls. Example:

```
Task 1 (parallel):
  description: "Modify triage agent prompt"
  subagent_type: "general-purpose"
  prompt: |
    Modify the triage agent for {domain_name}.

    Configuration:
    - Domain: {domain_name} - {domain_description}
    - Sub-agents: {sub_agent_summaries with tools and routing info}

    File: app/agent_factory/agents/orchestration/triage_agent.py

    Instructions:
    1. Read the file
    2. Fill {domain_purpose} with domain description
    3. Fill {agent_summaries} with detailed agent descriptions including tools, use cases, routing guidance
    4. Fill {routing_examples} with 5-8 specific examples
    5. Fill {decision_guidelines} with decision-making rules
    6. Write the updated file

    DO NOT modify output format. Write in English.

Task 2 (parallel):
  description: "Modify plan agent prompt"
  subagent_type: "general-purpose"
  prompt: |
    Modify the plan agent for {domain_name}.
    ... (similar structure)

... Tasks 3-6 for replan, review, clarify, summary
```

### Subagent Instructions Template

Each subagent should:
1. **Read** the orchestration agent file
2. **Fill `{placeholders}`** using LLM reasoning based on collected config
3. **Modify surrounding text** if it improves the prompt
4. **DO NOT modify** output format sections (captured by schema)
5. **Write** the updated file
6. **ALWAYS write in English** regardless of user's language

---

## Phase 4: Post-Generation Summary

After all tasks complete, summarize:

```
## Files Generated/Modified

### Generated:
1. `app/agent_factory/subagent_config.py`
2. `app/agent_factory/agents/sub_agents/{key}_agent.py` (per agent)
3. `app/agent_factory/agents/sub_agents/tools/{key}_tools.py` (per agent)

### Modified (prompts customized for your domain):
4-9. All 6 orchestration agents in `app/agent_factory/agents/orchestration/`

## Next Steps

1. **Implement Tools**: Replace stubs in `tools/{key}_tools.py`
2. **Test**:
   ```bash
   USE_DEMO_OPSAGENT=false uv run uvicorn app.main:app --reload
   ```

Would you like help implementing any tools?
```

---

## Phase 5: Tool Implementation (Optional)

If the user wants help implementing tools:

1. **Gather requirements** (APIs, data sources, SDKs)
2. **Add dependencies**: `uv add <package-name>`
3. **Implement tools**: Replace `NotImplementedError` stubs with actual logic
4. **Test each tool**:
   ```python
   # test_tools.py
   from app.agent_factory.agents.sub_agents.tools.{key}_tools import tool_func
   result = tool_func(param="value")
   print(result)
   ```
   Run: `uv run python test_tools.py`
5. **Iterate** until all tools pass

---

## Important Notes

- Use snake_case for keys and function names
- Use PascalCase for class names
- Tool functions must return JSON strings
- Use `Annotated` type hints for parameters
- **Orchestration prompts are filled by Claude (LLM), not string parsing**
- **DO NOT modify output format sections** (captured by schema)
- **ALWAYS write prompts in English**

---

## Example Session

```
User: /onboard

Claude: What domain does this assistant serve?

User: HR Assistant - Helps employees manage leave, payroll, benefits

Claude: Now define your first agent...

User: leave agent - handles vacation/leave, tools: get_leave_balance, submit_leave_request
       Route here for: PTO, vacation, sick leave
       Don't route here for: pay during leave (that's payroll)

Claude: Do you have another agent?

User: yes, payroll agent - salary/compensation, tools: get_pay_stub, get_bonus_info
       Route here for: salary, pay, bonus
       Don't route here for: leave balance

User: no more agents

Claude: [Shows configuration summary]

User: yes, looks correct

Claude: [Generates sub-agent files]
Claude: [Launches 6 parallel Task subagents to modify orchestration prompts]
Claude: [Shows completion summary with next steps]
```

See `./examples/hr_assistant.md` for the complete generated output.
