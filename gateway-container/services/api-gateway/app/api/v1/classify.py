from fastapi import APIRouter, Depends

from ...contracts.requests import BatchClassifyIn, ClassifyIn
from ...core.auth import current_user, require_api_key
from ...services import services

router = APIRouter(dependencies=[Depends(require_api_key), Depends(current_user)])


@router.post("/classify")
async def classify(body: ClassifyIn):
    return await services.classifier.classify_one(body.text, body.threshold)


@router.post("/batch-classify")
async def batch_classify(body: BatchClassifyIn):
    return await services.classifier.classify_batch(body.texts, body.threshold)
