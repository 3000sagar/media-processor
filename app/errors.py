from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class ApiError(Exception):
    """Base exception every service/endpoint should raise instead of ad hoc HTTPException.

    Guarantees every error response in this API has the exact same shape (RFC 7807),
    instead of every route inventing its own JSON body.
    """

    def __init__(self, status: int, title: str, detail: str | None = None, type_: str = "about:blank"):
        self.status = status
        self.title = title
        self.detail = detail
        self.type = type_
        super().__init__(title)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        problem = ProblemDetail(
            type=exc.type,
            title=exc.title,
            status=exc.status,
            detail=exc.detail,
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=exc.status, content=problem.model_dump(exclude_none=True))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals (stack traces, exception text) to the client.
        problem = ProblemDetail(
            title="Internal server error",
            status=500,
            instance=str(request.url.path),
        )
        return JSONResponse(status_code=500, content=problem.model_dump(exclude_none=True))


# Convenience constructors for common cases, used across the codebase for consistency.
def unauthorized(detail: str = "Missing or invalid API key") -> ApiError:
    return ApiError(401, "Unauthorized", detail, type_="https://media-processor.internal/errors/unauthorized")


def forbidden(detail: str = "You do not own this resource") -> ApiError:
    return ApiError(403, "Forbidden", detail, type_="https://media-processor.internal/errors/forbidden")


def not_found(detail: str = "Resource not found") -> ApiError:
    return ApiError(404, "Not Found", detail, type_="https://media-processor.internal/errors/not-found")


def conflict(detail: str) -> ApiError:
    return ApiError(409, "Conflict", detail, type_="https://media-processor.internal/errors/conflict")


def unprocessable(detail: str) -> ApiError:
    return ApiError(422, "Unprocessable Entity", detail, type_="https://media-processor.internal/errors/validation")


def too_many_requests(detail: str = "Rate limit exceeded") -> ApiError:
    return ApiError(429, "Too Many Requests", detail, type_="https://media-processor.internal/errors/rate-limit")


def service_unavailable(detail: str) -> ApiError:
    return ApiError(503, "Service Unavailable", detail, type_="https://media-processor.internal/errors/unavailable")
