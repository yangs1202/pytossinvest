"""토스증권 Open API 예외 정의.

모든 에러 응답은 공통 envelope 으로 내려옵니다::

    {
      "error": {
        "requestId": "01HXYZ...",
        "code": "invalid-request",
        "message": "주문 방향이 올바르지 않습니다.",
        "data": { ... }
      }
    }

OAuth2 토큰 엔드포인트(/oauth2/token)는 envelope 이 아닌 OAuth2 표준 에러 형식을
따르므로, 해당 경우에도 사용할 수 있도록 필드를 모두 optional 로 둡니다.
"""

from __future__ import annotations

from typing import Any, Optional


class TossInvestError(Exception):
    """라이브러리 전체의 베이스 예외."""


class TossInvestAPIError(TossInvestError):
    """API 가 에러 응답(4xx/5xx)을 반환했을 때 발생합니다.

    Attributes:
        status_code: HTTP 상태 코드.
        code: 토스 에러 코드 (예: ``invalid-request``, ``order-not-found``).
        message: 사람이 읽을 수 있는 에러 메시지.
        request_id: 응답의 ``requestId`` (헤더 ``X-Request-Id`` 와 동일).
            누락된 경우 응답 헤더의 ``cf-ray`` 값으로 대체됩니다.
        data: 에러 해결 힌트. 코드별로 포함 여부와 키 구조가 다릅니다.
        response_headers: 원본 응답 헤더 (rate limit 헤더 등 포함).
    """

    def __init__(
        self,
        status_code: int,
        code: Optional[str] = None,
        message: Optional[str] = None,
        request_id: Optional[str] = None,
        data: Any = None,
        response_headers: Optional[dict] = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id
        self.data = data
        self.response_headers = response_headers or {}

        parts = [f"HTTP {status_code}"]
        if code:
            parts.append(code)
        if message:
            parts.append(message)
        if request_id:
            parts.append(f"(requestId={request_id})")
        super().__init__(" ".join(parts))


class TossInvestAuthError(TossInvestAPIError):
    """토큰 발급/인증 실패(401) 시 발생합니다."""


class TossInvestRateLimitError(TossInvestAPIError):
    """Rate limit(429) 초과 시 발생합니다.

    Attributes:
        retry_after: 재시도 권장 대기 시간(초). ``Retry-After`` 헤더 값.
    """

    def __init__(self, *args: Any, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        self.retry_after = retry_after
        super().__init__(*args, **kwargs)
