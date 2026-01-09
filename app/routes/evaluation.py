"""Evaluation routes for message satisfaction feedback (thumb up/down)."""

from fastapi import APIRouter, HTTPException

from ..dependencies import HistoryManagerDep
from ..schemas import EvaluationResponse, EvaluationUpdate

router = APIRouter()


@router.patch(
    "/conversations/{conversation_id}/messages/{sequence_number}/evaluation",
    response_model=EvaluationResponse,
)
async def set_evaluation(
    conversation_id: str,
    sequence_number: int,
    body: EvaluationUpdate,
    history: HistoryManagerDep,
):
    """Set message satisfaction evaluation.

    - is_satisfy=true: Thumb up
    - is_satisfy=false: Thumb down, with optional comment
    """
    result = await history.backend.set_message_evaluation(
        conversation_id=conversation_id,
        sequence_number=sequence_number,
        is_satisfy=body.is_satisfy,
        comment=body.comment,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")

    return EvaluationResponse(**result)


@router.patch(
    "/conversations/{conversation_id}/messages/{sequence_number}/evaluation/clear",
    response_model=EvaluationResponse,
)
async def clear_evaluation(
    conversation_id: str,
    sequence_number: int,
    history: HistoryManagerDep,
):
    """Clear message satisfaction evaluation.

    Sets is_satisfy and comment to NULL (toggle off).
    """
    result = await history.backend.clear_message_evaluation(
        conversation_id=conversation_id,
        sequence_number=sequence_number,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Message not found")

    return EvaluationResponse(**result)
