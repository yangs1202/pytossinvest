"""TossInvestClient 단위 테스트 (HTTP 는 responses 로 모킹)."""

import json

import pytest
import responses

from pytossinvest import (
    TossInvestAPIError,
    TossInvestAuthError,
    TossInvestClient,
    TossInvestError,
    TossInvestRateLimitError,
)

BASE = "https://openapi.tossinvest.com"
TOKEN_URL = f"{BASE}/oauth2/token"


def _register_token(expires_in=86400, token="tok-123"):
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": token, "token_type": "Bearer", "expires_in": expires_in},
        status=200,
    )


def _client():
    return TossInvestClient(client_id="c_test", client_secret="s_test", max_retries=2)


def test_init_requires_credentials():
    with pytest.raises(ValueError):
        TossInvestClient(client_id="", client_secret="x")


@responses.activate
def test_token_issued_and_bearer_attached():
    _register_token(token="abc")
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/prices",
        json={"result": [{"symbol": "005930", "lastPrice": "72000"}]},
        status=200,
    )
    client = _client()
    result = client.get_prices("005930")

    assert result == [{"symbol": "005930", "lastPrice": "72000"}]
    # 토큰 발급 1회 + prices 1회
    assert len(responses.calls) == 2
    token_req = responses.calls[0].request
    assert "grant_type=client_credentials" in token_req.body
    prices_req = responses.calls[1].request
    assert prices_req.headers["Authorization"] == "Bearer abc"
    assert prices_req.params["symbols"] == "005930"


@responses.activate
def test_token_is_cached_across_calls():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/prices", json={"result": []}, status=200
    )
    client = _client()
    client.get_prices("005930")
    client.get_prices("000660")
    # 토큰은 한 번만 발급되어야 함
    token_calls = [c for c in responses.calls if c.request.url.startswith(TOKEN_URL)]
    assert len(token_calls) == 1


@responses.activate
def test_symbols_list_joined_with_comma():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/stocks", json={"result": []}, status=200
    )
    client = _client()
    client.get_stocks(["005930", "AAPL"])
    req = responses.calls[-1].request
    assert req.params["symbols"] == "005930,AAPL"


@responses.activate
def test_candles_params_serialized():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/candles", json={"result": {}}, status=200
    )
    client = _client()
    client.get_candles("005930", interval="1d", count=10, adjusted=True)
    req = responses.calls[-1].request
    assert req.params["interval"] == "1d"
    assert req.params["count"] == "10"
    assert req.params["adjusted"] == "True"
    assert "before" not in req.params  # None 값은 제외


@responses.activate
def test_account_header_required_without_seq():
    _register_token()
    client = _client()
    with pytest.raises(TossInvestError):
        client.get_holdings()  # account_seq 미설정


@responses.activate
def test_account_header_sent():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/holdings", json={"result": {}}, status=200
    )
    client = _client()
    client.account_seq = 7
    client.get_holdings()
    req = responses.calls[-1].request
    assert req.headers["X-Tossinvest-Account"] == "7"


@responses.activate
def test_account_seq_override_per_call():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/holdings", json={"result": {}}, status=200
    )
    client = _client()
    client.account_seq = 1
    client.get_holdings(account_seq=99)
    req = responses.calls[-1].request
    assert req.headers["X-Tossinvest-Account"] == "99"


@responses.activate
def test_create_order_quantity_based_body():
    _register_token()
    responses.add(
        responses.POST,
        f"{BASE}/api/v1/orders",
        json={"result": {"orderId": "o1", "clientOrderId": "my-1"}},
        status=200,
    )
    client = _client()
    client.account_seq = 1
    result = client.create_order(
        symbol="005930",
        side="BUY",
        order_type="LIMIT",
        quantity=10,
        price=70000,
        client_order_id="my-1",
    )
    assert result["orderId"] == "o1"
    body = json.loads(responses.calls[-1].request.body)
    assert body == {
        "symbol": "005930",
        "side": "BUY",
        "orderType": "LIMIT",
        "quantity": "10",
        "price": "70000",
        "clientOrderId": "my-1",
    }


def test_create_order_requires_exactly_one_quantity_mode():
    client = _client()
    client.account_seq = 1
    with pytest.raises(ValueError):
        client.create_order("AAPL", "BUY", "LIMIT")  # 둘 다 없음
    with pytest.raises(ValueError):
        client.create_order(
            "AAPL", "BUY", "MARKET", quantity=1, order_amount=100
        )  # 둘 다 있음


@responses.activate
def test_error_envelope_parsed():
    _register_token()
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/orderbook",
        json={
            "error": {
                "requestId": "req-1",
                "code": "stock-not-found",
                "message": "종목을 찾을 수 없습니다.",
                "data": {"symbol": "999999"},
            }
        },
        status=404,
    )
    client = _client()
    with pytest.raises(TossInvestAPIError) as exc:
        client.get_orderbook("999999")
    err = exc.value
    assert err.status_code == 404
    assert err.code == "stock-not-found"
    assert err.request_id == "req-1"
    assert err.data == {"symbol": "999999"}


@responses.activate
def test_rate_limit_retries_then_succeeds():
    _register_token()
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/prices",
        json={"error": {"code": "rate-limit-exceeded"}},
        status=429,
        headers={"Retry-After": "0"},
    )
    responses.add(
        responses.GET, f"{BASE}/api/v1/prices", json={"result": []}, status=200
    )
    client = _client()
    result = client.get_prices("005930")
    assert result == []
    price_calls = [c for c in responses.calls if "/prices" in c.request.url]
    assert len(price_calls) == 2  # 429 1회 + 성공 1회


@responses.activate
def test_rate_limit_exhausts_retries_raises():
    _register_token()
    for _ in range(5):
        responses.add(
            responses.GET,
            f"{BASE}/api/v1/prices",
            json={"error": {"code": "rate-limit-exceeded"}},
            status=429,
            headers={"Retry-After": "0"},
        )
    client = TossInvestClient("c", "s", max_retries=1)
    with pytest.raises(TossInvestRateLimitError) as exc:
        client.get_prices("005930")
    assert exc.value.retry_after == 0.0


@responses.activate
def test_401_triggers_token_refresh_and_retry():
    # 첫 토큰 발급
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "t1", "token_type": "Bearer", "expires_in": 86400},
        status=200,
    )
    # 첫 호출은 401 (토큰 무효화 시뮬레이션)
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/prices",
        json={"error": {"code": "invalid-token"}},
        status=401,
    )
    # 재발급 토큰
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "t2", "token_type": "Bearer", "expires_in": 86400},
        status=200,
    )
    # 재시도 성공
    responses.add(
        responses.GET, f"{BASE}/api/v1/prices", json={"result": []}, status=200
    )
    client = _client()
    result = client.get_prices("005930")
    assert result == []
    last = responses.calls[-1].request
    assert last.headers["Authorization"] == "Bearer t2"


@responses.activate
def test_token_endpoint_401_raises_auth_error():
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"error": "invalid_client", "error_description": "bad secret"},
        status=401,
    )
    client = _client()
    with pytest.raises(TossInvestAuthError) as exc:
        client.fetch_token()
    assert exc.value.code == "invalid_client"
    assert exc.value.message == "bad secret"


@responses.activate
def test_context_manager_closes_session():
    _register_token()
    responses.add(
        responses.GET, f"{BASE}/api/v1/accounts", json={"result": []}, status=200
    )
    with _client() as client:
        assert client.get_accounts() == []
