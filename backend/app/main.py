from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import admin, auth, avatars, jobs, me, meta, projects, script, video, voices
from app.api import worker as worker_api
from app.core.config import get_settings
from app.core.errors import AppError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.limiter import limiter
from app.db.connection import run_migrations
from app.engines.script_llm import QuotaExhaustedError, ScriptGenerationError
from app.jobs.queue import sweep_interrupted_jobs
from app.jobs.worker import Worker
from app.services.script_service import ScriptValidationError


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    run_migrations(settings.db_path)
    sweep_interrupted_jobs(settings.db_path)  # no orphaned `running` rows after a crash+restart

    worker = Worker(settings.db_path)
    app.state.worker = worker
    await worker.start()
    yield
    await worker.stop()


def _error_response(status_code: int, code: str, message: str, hint: str | None = None):
    body = {"error": {"code": code, "message": message}}
    if hint:
        body["error"]["hint"] = hint
    return JSONResponse(status_code=status_code, content=body)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Video Maker", lifespan=lifespan)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return _error_response(404, exc.code, exc.message, exc.hint)

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError):
        return _error_response(403, exc.code, exc.message, exc.hint)

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError):
        return _error_response(401, exc.code, exc.message, exc.hint)

    @app.exception_handler(QuotaExhaustedError)
    async def quota_exhausted_handler(request: Request, exc: QuotaExhaustedError):
        message = str(exc)
        return _error_response(429, "quota_exhausted", message, hint=message)

    @app.exception_handler(ScriptValidationError)
    async def script_validation_handler(request: Request, exc: ScriptValidationError):
        return _error_response(422, "script_validation_failed", "; ".join(exc.errors))

    @app.exception_handler(ScriptGenerationError)
    async def script_generation_handler(request: Request, exc: ScriptGenerationError):
        return _error_response(502, "script_generation_failed", str(exc))

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return _error_response(400, exc.code, exc.message, exc.hint)

    app.include_router(meta.router, prefix="/api/meta", tags=["meta"])
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(me.router, prefix="/api/me", tags=["me"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(script.router, prefix="/api/projects", tags=["script"])
    app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
    app.include_router(video.router, prefix="/api/projects", tags=["video"])
    app.include_router(avatars.router, prefix="/api/avatars", tags=["avatars"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(voices.router, prefix="/api/voices", tags=["voices"])
    app.include_router(worker_api.router, prefix="/api/worker", tags=["worker"])
    return app


app = create_app()
