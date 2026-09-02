"""A single, predictable error shape for every API response.

Android should branch on ``code``, never on ``message`` (which is prose meant
for a human, and free to change wording). ``details`` carries whatever
structured extras a given error needs — a paywall decision's ad/upsell flags,
a rate limit's retry-after seconds, and so on.

Every ``HTTPException`` in the app is normalized into this shape by the
exception handler registered in ``app_factory.create_app`` (see
``install_error_handlers``), so a route that still raises
``HTTPException(status_code=404, detail="Listing not found")`` needs no
changes — it comes out the other side as
``{"code": "not_found", "message": "Listing not found", "details": {}}``.
Routes that need a specific, documented code should raise via ``api_error``
instead so ``code`` is exact rather than derived from the status code alone.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.monetization.gate import AccessDecision

_STATUS_FALLBACK_CODES = {
    400: "bad_request",
    401: "unauthorized",
    402: "payment_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    503: "service_unavailable",
}


def api_error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": details or {}})


def raise_access_blocked(decision: AccessDecision) -> None:
    raise api_error(
        status.HTTP_402_PAYMENT_REQUIRED,
        code=decision.reason,
        message="This feature isn't available right now.",
        details={"should_offer_ad": decision.should_offer_ad, "should_show_paywall": decision.should_show_paywall},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _normalize_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            body = {"code": detail["code"], "message": detail["message"], "details": detail.get("details", {})}
        elif isinstance(detail, dict):
            # Pre-existing shapes (e.g. the legacy access-blocked payload) that
            # were never migrated to api_error(): keep every original key
            # available under `details` rather than silently dropping data a
            # client may already depend on.
            code = str(detail.get("reason") or detail.get("code") or _STATUS_FALLBACK_CODES.get(exc.status_code, "error"))
            body = {"code": code, "message": _STATUS_FALLBACK_CODES.get(exc.status_code, "error").replace("_", " "), "details": detail}
        else:
            code = _STATUS_FALLBACK_CODES.get(exc.status_code, "error")
            body = {"code": code, "message": str(detail) if detail else code.replace("_", " "), "details": {}}
        return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None) or {})

    @app.exception_handler(RequestValidationError)
    async def _normalize_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "validation_error",
                "message": "One or more fields are invalid.",
                "details": {"errors": jsonable_encoder(exc.errors())},
            },
        )
