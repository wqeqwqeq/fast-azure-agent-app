"""Model and agent configuration API routes."""

from fastapi import APIRouter, Request

from ..schemas import AgentsResponse, ModelsResponse

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
async def get_models(request: Request) -> ModelsResponse:
    """List available LLM models.

    Returns:
        ModelsResponse with list of available model identifiers
    """
    registry = request.app.state.model_registry
    return ModelsResponse(models=[m.name for m in registry.list_models()])


@router.get("/agents", response_model=AgentsResponse)
async def get_agents(react_mode: bool = False) -> AgentsResponse:
    """List agent keys based on workflow type.

    Args:
        react_mode: If True, return dynamic workflow agents; otherwise triage agents.

    Returns:
        AgentsResponse with list of agent keys for per-agent model override
    """
    from ..opsagent.model_registry import DYNAMIC_AGENTS, TRIAGE_AGENTS

    agents = DYNAMIC_AGENTS if react_mode else TRIAGE_AGENTS
    return AgentsResponse(agents=agents)
