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
async def get_agents() -> AgentsResponse:
    """List agent keys that can have custom models.

    Returns:
        AgentsResponse with list of agent keys for per-agent model override
    """
    return AgentsResponse(
        agents=[
            "triage",
            "servicenow",
            "log_analytics",
            "service_health",
            "review",
            "clarify",
            "plan",
            "replan",
            "summary",
        ]
    )
