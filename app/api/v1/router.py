from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.llm_test import router as llm_router
from app.api.v1.workflows import router as workflows_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.executions import router as executions_router
from app.api.v1.tools import router as tools_router
from app.api.v1.planning import router as planning_router
from app.api.v1.artifacts import router as artifacts_router
from app.api.v1.security import router as security_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.templates import router as templates_router

api_v1_router = APIRouter()

api_v1_router.include_router(health_router)
api_v1_router.include_router(llm_router)
api_v1_router.include_router(workflows_router)
api_v1_router.include_router(approvals_router)
api_v1_router.include_router(executions_router)
api_v1_router.include_router(tools_router)
api_v1_router.include_router(planning_router)
api_v1_router.include_router(artifacts_router)
api_v1_router.include_router(security_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(templates_router)


