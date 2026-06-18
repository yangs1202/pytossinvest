"""토스증권 Open API Python 클라이언트.

토스증권 Open API (https://developers.tossinvest.com/docs) 의 얇은 wrapper 입니다.
OAuth 2.0 토큰 발급/갱신, 계좌 헤더 처리, 에러 envelope 파싱, 429 재시도를
처리하며, 20개 엔드포인트 전부를 메서드로 노출합니다.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Union

import requests

from .exceptions import (
    TossInvestAPIError,
    TossInvestAuthError,
    TossInvestError,
    TossInvestRateLimitError,
)

__all__ = ["TossInvestClient"]

DEFAULT_BASE_URL = "https://openapi.tossinvest.com"
DEFAULT_TIMEOUT = 10.0
# 만료 임박 토큰을 미리 갱신하기 위한 여유 시간(초).
_TOKEN_EXPIRY_SKEW = 60

SymbolsArg = Union[str, Iterable[str]]


def _join_symbols(symbols: SymbolsArg) -> str:
    """``"005930"`` 또는 ``["005930", "AAPL"]`` 을 콤마 구분 문자열로 변환."""
    if isinstance(symbols, str):
        return symbols
    return ",".join(str(s) for s in symbols)


class TossInvestClient:
    """토스증권 Open API 클라이언트.

    Example:
        >>> client = TossInvestClient(client_id="c_...", client_secret="s_...")
        >>> client.get_prices("005930")
        [{'symbol': '005930', 'lastPrice': '72000', ...}]
        >>> accounts = client.get_accounts()
        >>> client.account_seq = accounts[0]["accountSeq"]
        >>> client.get_holdings()

    Args:
        client_id: 발급받은 클라이언트 ID.
        client_secret: 발급받은 클라이언트 시크릿.
        account_seq: 계좌 컨텍스트 API 에서 기본으로 사용할 ``accountSeq``.
            메서드 호출 시 ``account_seq`` 인자로 매번 override 할 수 있습니다.
        base_url: API 베이스 URL. 기본값은 운영 서버.
        timeout: 개별 요청 타임아웃(초).
        max_retries: 429 응답에 대한 최대 재시도 횟수.
        session: 재사용할 ``requests.Session``. 미지정 시 내부에서 생성.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        account_seq: Optional[int] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("client_id 와 client_secret 은 필수입니다.")
        self._client_id = client_id
        self._client_secret = client_secret
        self.account_seq = account_seq
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = session or requests.Session()

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # 인증 (Auth)
    # ------------------------------------------------------------------ #
    def fetch_token(self) -> Dict[str, Any]:
        """OAuth 2.0 Client Credentials Grant 로 access token 을 발급합니다.

        토큰은 내부에 캐시되며 만료 임박 시 자동 갱신됩니다. 보통 직접 호출할
        필요는 없지만, 토큰 메타데이터(``expires_in`` 등)가 필요하면 사용합니다.

        Returns:
            ``{"access_token": ..., "token_type": "Bearer", "expires_in": ...}``
        """
        url = f"{self.base_url}/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        resp = self._session.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            self._raise_for_error(resp, is_token=True)

        payload = resp.json()
        self._access_token = payload["access_token"]
        expires_in = payload.get("expires_in", 0)
        self._token_expires_at = time.time() + max(0, expires_in - _TOKEN_EXPIRY_SKEW)
        return payload

    def _ensure_token(self) -> str:
        """유효한 access token 을 반환하고, 없거나 만료 임박이면 갱신합니다."""
        with self._token_lock:
            if self._access_token is None or time.time() >= self._token_expires_at:
                self.fetch_token()
            assert self._access_token is not None
            return self._access_token

    # ------------------------------------------------------------------ #
    # 내부 요청 처리
    # ------------------------------------------------------------------ #
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
        account_seq: Optional[int] = None,
        require_account: bool = False,
    ) -> Any:
        """인증 헤더를 붙여 요청하고, envelope 의 ``result`` 를 반환합니다.

        429 응답은 ``Retry-After`` (없으면 지수 백오프 + jitter) 만큼 대기 후
        ``max_retries`` 까지 재시도합니다.
        """
        url = f"{self.base_url}{path}"
        clean_params = None
        if params is not None:
            clean_params = {k: v for k, v in params.items() if v is not None}

        headers = {}
        if require_account:
            seq = account_seq if account_seq is not None else self.account_seq
            if seq is None:
                raise TossInvestError(
                    "이 API 는 계좌가 필요합니다. account_seq 를 전달하거나 "
                    "client.account_seq 를 설정하세요."
                )
            headers["X-Tossinvest-Account"] = str(seq)

        attempt = 0
        while True:
            headers["Authorization"] = f"Bearer {self._ensure_token()}"
            resp = self._session.request(
                method,
                url,
                params=clean_params,
                json=json_body,
                headers=headers,
                timeout=self.timeout,
            )

            if resp.status_code == 429 and attempt < self.max_retries:
                wait = self._retry_wait(resp, attempt)
                time.sleep(wait)
                attempt += 1
                continue

            if resp.status_code == 401 and attempt == 0:
                # 토큰이 무효화된 경우 한 번 강제 갱신 후 재시도.
                self._access_token = None
                attempt += 1
                continue

            if not resp.ok:
                self._raise_for_error(resp)

            return self._unwrap(resp)

    @staticmethod
    def _retry_wait(resp: requests.Response, attempt: int) -> float:
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        # 지수 백오프 (1s, 2s, 4s, ...) + jitter
        return (2 ** attempt) + random.uniform(0, 0.5)

    @staticmethod
    def _unwrap(resp: requests.Response) -> Any:
        if resp.status_code == 204 or not resp.content:
            return None
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    @staticmethod
    def _raise_for_error(resp: requests.Response, is_token: bool = False) -> None:
        status = resp.status_code
        code = message = request_id = None
        data = None
        try:
            payload = resp.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                code = err.get("code")
                message = err.get("message")
                request_id = err.get("requestId")
                data = err.get("data")
            else:
                # OAuth2 표준 에러 형식: {"error": "...", "error_description": "..."}
                code = payload.get("error")
                message = payload.get("error_description")

        if request_id is None:
            request_id = resp.headers.get("X-Request-Id") or resp.headers.get("cf-ray")

        kwargs = dict(
            status_code=status,
            code=code,
            message=message,
            request_id=request_id,
            data=data,
            response_headers=dict(resp.headers),
        )

        if status == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                retry_after = float(retry_after) if retry_after is not None else None
            except ValueError:
                retry_after = None
            raise TossInvestRateLimitError(retry_after=retry_after, **kwargs)
        if status == 401 or is_token:
            raise TossInvestAuthError(**kwargs)
        raise TossInvestAPIError(**kwargs)

    # ================================================================== #
    # 시세 (Market Data)
    # ================================================================== #
    def get_orderbook(self, symbol: str) -> Dict[str, Any]:
        """호가 조회. 매수/매도 호가 및 잔량을 반환합니다.

        Args:
            symbol: 종목 심볼. KRX 6자리 숫자(예: ``005930``) 또는 US 티커(예: ``AAPL``).
        """
        return self._request("GET", "/api/v1/orderbook", params={"symbol": symbol})

    def get_prices(self, symbols: SymbolsArg) -> List[Dict[str, Any]]:
        """현재가 조회. 최대 200건 다건 조회를 지원합니다.

        Args:
            symbols: 종목 심볼 문자열(콤마 구분) 또는 심볼 리스트.
        """
        return self._request(
            "GET", "/api/v1/prices", params={"symbols": _join_symbols(symbols)}
        )

    def get_trades(self, symbol: str, count: Optional[int] = None) -> List[Dict[str, Any]]:
        """최근 체결 내역 조회 (당일).

        Args:
            symbol: 종목 심볼.
            count: 조회 건수 (1~50).
        """
        return self._request(
            "GET", "/api/v1/trades", params={"symbol": symbol, "count": count}
        )

    def get_price_limits(self, symbol: str) -> Dict[str, Any]:
        """상/하한가 조회 (당일).

        Args:
            symbol: 종목 심볼.
        """
        return self._request("GET", "/api/v1/price-limits", params={"symbol": symbol})

    def get_candles(
        self,
        symbol: str,
        interval: str,
        count: Optional[int] = None,
        before: Optional[str] = None,
        adjusted: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """캔들(OHLCV) 차트 조회. 최대 200개 봉을 반환합니다.

        Args:
            symbol: 종목 심볼.
            interval: 봉 간격. ``"1m"`` (1분봉) 또는 ``"1d"`` (일봉).
            count: 조회 봉 개수 (최대 200).
            before: 이 시각 이전의 봉을 조회 (date-time, 페이지네이션).
            adjusted: 수정주가 적용 여부.
        """
        return self._request(
            "GET",
            "/api/v1/candles",
            params={
                "symbol": symbol,
                "interval": interval,
                "count": count,
                "before": before,
                "adjusted": adjusted,
            },
        )

    # ================================================================== #
    # 종목 정보 (Stock Info)
    # ================================================================== #
    def get_stocks(self, symbols: SymbolsArg) -> List[Dict[str, Any]]:
        """종목 기본 정보 조회. 콤마 구분 최대 200건 다건 조회.

        Args:
            symbols: 종목 심볼 문자열(콤마 구분) 또는 심볼 리스트.
        """
        return self._request(
            "GET", "/api/v1/stocks", params={"symbols": _join_symbols(symbols)}
        )

    def get_stock_warnings(self, symbol: str) -> List[Dict[str, Any]]:
        """매수 유의사항(정리매매·과열·투자경고/위험·VI 등) 조회.

        Args:
            symbol: 종목 심볼.
        """
        return self._request("GET", f"/api/v1/stocks/{symbol}/warnings")

    # ================================================================== #
    # 환율·장 운영 시간 (Market Info)
    # ================================================================== #
    def get_exchange_rate(
        self,
        base_currency: str,
        quote_currency: str,
        date_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """KRW↔USD 환율 조회.

        Args:
            base_currency: 기준 통화. ``"KRW"`` 또는 ``"USD"``.
            quote_currency: 표시 통화. ``"KRW"`` 또는 ``"USD"``.
            date_time: 조회 시각 (date-time). 미지정 시 현재 유효 환율.
        """
        return self._request(
            "GET",
            "/api/v1/exchange-rate",
            params={
                "baseCurrency": base_currency,
                "quoteCurrency": quote_currency,
                "dateTime": date_time,
            },
        )

    def get_market_calendar_kr(self, date: Optional[str] = None) -> Dict[str, Any]:
        """국내(KRX+NXT) 장 운영 정보 조회. 전일/당일/익일 3영업일 반환.

        Args:
            date: 조회 기준일 (``YYYY-MM-DD``).
        """
        return self._request(
            "GET", "/api/v1/market-calendar/KR", params={"date": date}
        )

    def get_market_calendar_us(self, date: Optional[str] = None) -> Dict[str, Any]:
        """해외(미국) 장 운영 정보 조회. 전일/당일/익일 3영업일 반환.

        Args:
            date: 조회 기준일 (``YYYY-MM-DD``, 미국 현지 날짜).
        """
        return self._request(
            "GET", "/api/v1/market-calendar/US", params={"date": date}
        )

    # ================================================================== #
    # 계좌·자산 (Account · Asset)
    # ================================================================== #
    def get_accounts(self) -> List[Dict[str, Any]]:
        """계좌 목록 조회.

        응답의 ``accountSeq`` 를 ``client.account_seq`` 또는 계좌 API 의
        ``account_seq`` 인자로 사용합니다.
        """
        return self._request("GET", "/api/v1/accounts")

    def get_holdings(
        self,
        symbol: Optional[str] = None,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """보유 주식 조회 (종목별 상세 + 합산 요약).

        Args:
            symbol: 특정 종목으로 필터링 (미지정 시 전체).
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            "/api/v1/holdings",
            params={"symbol": symbol},
            account_seq=account_seq,
            require_account=True,
        )

    # ================================================================== #
    # 주문 (Order)
    # ================================================================== #
    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[Union[str, int]] = None,
        order_amount: Optional[Union[str, float]] = None,
        price: Optional[Union[str, float]] = None,
        time_in_force: Optional[str] = None,
        client_order_id: Optional[str] = None,
        confirm_high_value_order: Optional[bool] = None,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """주문 생성 (매수/매도).

        ``quantity`` (수량 기반) 와 ``order_amount`` (금액 기반) 중 **정확히 하나**를
        지정해야 합니다. ``order_amount`` 는 US 시장 정규장 전용입니다.

        Args:
            symbol: 종목 심볼.
            side: 주문 방향. ``"BUY"`` 또는 ``"SELL"``.
            order_type: 호가 유형. ``"LIMIT"`` (지정가) 또는 ``"MARKET"`` (시장가).
            quantity: 주문 수량(주). 정수 문자열. 금액 기반 주문 시 미지정.
            order_amount: 주문 금액(달러). US 전용. 수량 기반 주문 시 미지정.
            price: 주문 가격. ``order_type`` 이 ``LIMIT`` 일 때만 사용.
                KR 은 정수(원), US 는 소수점(달러).
            time_in_force: 주문 유효 조건. ``"DAY"`` (기본) 또는 ``"CLS"`` (장 마감).
            client_order_id: 멱등성 키 (최대 36자, 영숫자/``-``/``_``). 10분간 유효.
            confirm_high_value_order: 1억원 이상 주문 시 ``True`` 필요.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).

        Raises:
            ValueError: ``quantity`` 와 ``order_amount`` 를 둘 다 지정했거나 둘 다
                지정하지 않은 경우.
        """
        if (quantity is None) == (order_amount is None):
            raise ValueError(
                "quantity 와 order_amount 중 정확히 하나만 지정해야 합니다."
            )

        body: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
        }
        if quantity is not None:
            body["quantity"] = str(quantity)
        if order_amount is not None:
            body["orderAmount"] = str(order_amount)
        if price is not None:
            body["price"] = str(price)
        if time_in_force is not None:
            body["timeInForce"] = time_in_force
        if client_order_id is not None:
            body["clientOrderId"] = client_order_id
        if confirm_high_value_order is not None:
            body["confirmHighValueOrder"] = confirm_high_value_order

        return self._request(
            "POST",
            "/api/v1/orders",
            json_body=body,
            account_seq=account_seq,
            require_account=True,
        )

    def modify_order(
        self,
        order_id: str,
        order_type: str,
        quantity: Optional[Union[str, int]] = None,
        price: Optional[Union[str, float]] = None,
        confirm_high_value_order: Optional[bool] = None,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """주문 정정 (가격/수량).

        KR 주식은 ``quantity`` 필수, US 주식은 ``quantity`` 전달 불가(가격만 정정).

        Args:
            order_id: 정정할 주문 식별자.
            order_type: 변경할 호가 유형. ``"LIMIT"`` 또는 ``"MARKET"``.
            quantity: 변경할 수량 (KR 필수, US 불가).
            price: 변경할 가격 (``LIMIT`` 일 때만).
            confirm_high_value_order: 1억원 이상 주문 시 ``True`` 필요.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        body: Dict[str, Any] = {"orderType": order_type}
        if quantity is not None:
            body["quantity"] = str(quantity)
        if price is not None:
            body["price"] = str(price)
        if confirm_high_value_order is not None:
            body["confirmHighValueOrder"] = confirm_high_value_order

        return self._request(
            "POST",
            f"/api/v1/orders/{order_id}/modify",
            json_body=body,
            account_seq=account_seq,
            require_account=True,
        )

    def cancel_order(
        self,
        order_id: str,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """주문 취소. 이미 체결된 주문은 취소할 수 없습니다.

        Args:
            order_id: 취소할 주문 식별자.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "POST",
            f"/api/v1/orders/{order_id}/cancel",
            account_seq=account_seq,
            require_account=True,
        )

    # ================================================================== #
    # 주문 조회 (Order History)
    # ================================================================== #
    def list_orders(
        self,
        status: str,
        symbol: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        cursor: Optional[str] = None,
        limit: Optional[int] = None,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """주문 목록 조회.

        Args:
            status: 라이프사이클 그룹. ``"OPEN"`` (진행 중) 또는 ``"CLOSED"`` (종료).
            symbol: 특정 종목 필터.
            from_date: 조회 시작일 (``YYYY-MM-DD``, KST, inclusive).
            to_date: 조회 종료일 (``YYYY-MM-DD``, KST, inclusive).
            cursor: 페이지네이션 커서 (``CLOSED`` 에서만 유효).
            limit: 페이지 크기 (``CLOSED`` 기본 20, 최대 100). ``OPEN`` 은 전량 반환.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            "/api/v1/orders",
            params={
                "status": status,
                "symbol": symbol,
                "from": from_date,
                "to": to_date,
                "cursor": cursor,
                "limit": limit,
            },
            account_seq=account_seq,
            require_account=True,
        )

    def get_order(
        self,
        order_id: str,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """주문 상세 조회 (모든 상태).

        Args:
            order_id: 주문 식별자.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            f"/api/v1/orders/{order_id}",
            account_seq=account_seq,
            require_account=True,
        )

    # ================================================================== #
    # 거래 가능 정보 (Order Info)
    # ================================================================== #
    def get_buying_power(
        self,
        currency: str,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """매수 가능 금액 조회 (현금 기반).

        Args:
            currency: 통화. ``"KRW"`` 또는 ``"USD"``.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            "/api/v1/buying-power",
            params={"currency": currency},
            account_seq=account_seq,
            require_account=True,
        )

    def get_sellable_quantity(
        self,
        symbol: str,
        account_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """판매 가능 수량 조회.

        Args:
            symbol: 종목 심볼.
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            "/api/v1/sellable-quantity",
            params={"symbol": symbol},
            account_seq=account_seq,
            require_account=True,
        )

    def get_commissions(
        self,
        account_seq: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """매매 수수료 조회 (KR·US 시장별).

        Args:
            account_seq: 계좌 ``accountSeq`` (미지정 시 ``client.account_seq``).
        """
        return self._request(
            "GET",
            "/api/v1/commissions",
            account_seq=account_seq,
            require_account=True,
        )

    # ------------------------------------------------------------------ #
    # 컨텍스트 매니저 지원
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        """내부 ``requests.Session`` 을 닫습니다."""
        self._session.close()

    def __enter__(self) -> "TossInvestClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
