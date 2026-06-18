"""CLI(tossinvest) 단위 테스트."""

import json

import responses

from pytossinvest import cli

BASE = "https://openapi.tossinvest.com"
TOKEN_URL = f"{BASE}/oauth2/token"
CREDS = ["--client-id", "c_test", "--client-secret", "s_test"]


def _register_token():
    responses.add(
        responses.POST,
        TOKEN_URL,
        json={"access_token": "tok", "token_type": "Bearer", "expires_in": 86400},
        status=200,
    )


def test_symbols_normalizes_space_and_comma():
    assert cli._symbols(["005930", "AAPL"]) == "005930,AAPL"
    assert cli._symbols(["005930,000660"]) == "005930,000660"
    assert cli._symbols(["005930,AAPL", "MSFT"]) == "005930,AAPL,MSFT"


def test_missing_credentials_returns_2(capsys):
    code = cli.main(["accounts"])
    assert code == 2
    assert "client_id" in capsys.readouterr().err


def test_trade_command_blocked_without_yes(capsys):
    code = cli.main(CREDS + ["order-cancel", "abc"])
    assert code == 3
    assert "--yes" in capsys.readouterr().err


@responses.activate
def test_price_command_outputs_json(capsys):
    _register_token()
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/prices",
        json={"result": [{"symbol": "005930", "lastPrice": "72000"}]},
        status=200,
    )
    code = cli.main(CREDS + ["-c", "price", "005930"])
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out == [{"symbol": "005930", "lastPrice": "72000"}]
    assert responses.calls[-1].request.params["symbols"] == "005930"


@responses.activate
def test_api_error_returns_1_and_prints_to_stderr(capsys):
    _register_token()
    responses.add(
        responses.GET,
        f"{BASE}/api/v1/orderbook",
        json={"error": {"code": "stock-not-found", "message": "없음"}},
        status=404,
    )
    code = cli.main(CREDS + ["orderbook", "999999"])
    assert code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["error"]["code"] == "stock-not-found"
    assert err["error"]["status"] == 404


@responses.activate
def test_order_cancel_with_yes_executes(capsys):
    _register_token()
    responses.add(
        responses.POST,
        f"{BASE}/api/v1/orders/o1/cancel",
        json={"result": {"orderId": "o1"}},
        status=200,
    )
    code = cli.main(CREDS + ["-a", "1", "order-cancel", "o1", "--yes"])
    assert code == 0
    assert responses.calls[-1].request.headers["X-Tossinvest-Account"] == "1"
