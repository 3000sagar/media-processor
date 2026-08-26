from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import health, jobs, metrics
from app.errors import register_error_handlers, too_many_requests
from app.logging_config import configure_logging
from app.rate_limit import limiter


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(title="Distributed Media Processing Microservice", version="1.0.0")

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        err = too_many_requests()
        return JSONResponse(
            status_code=err.status,
            content={"title": err.title, "status": err.status, "detail": err.detail},
        )

    register_error_handlers(app)

    app.include_router(jobs.router)
    app.include_router(health.router)
    app.include_router(metrics.router)

    return app


app = create_app()
