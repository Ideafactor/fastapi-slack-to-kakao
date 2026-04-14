import time
import uuid
from contextvars import ContextVar

from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 요청 수명주기 동안 trace_id를 전파하는 컨텍스트 변수
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class TraceMiddleware(BaseHTTPMiddleware):
    """모든 요청에 trace_id를 부여하고 요청/응답 로그를 기록.

    카카오 웹훅의 경우 X-Kakao-Resource-ID를 trace_id로 사용.
    없으면 UUID를 생성하여 부여.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # X-Kakao-Resource-ID 우선, 없으면 UUID 생성
        trace_id = (
            request.headers.get("x-kakao-resource-id")
            or request.headers.get("x-slack-request-timestamp", "")
            or str(uuid.uuid4())[:8]
        )
        trace_id_var.set(trace_id)

        start = time.perf_counter()
        logger.info(
            f"[{trace_id}] --> {request.method} {request.url.path}"
        )

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            f"[{trace_id}] <-- {request.method} {request.url.path} "
            f"status={response.status_code} elapsed={elapsed_ms:.1f}ms"
        )
        # 응답 헤더에도 trace_id 주입 (디버깅 편의)
        response.headers["X-Trace-Id"] = trace_id
        return response


def get_trace_id() -> str:
    return trace_id_var.get()
