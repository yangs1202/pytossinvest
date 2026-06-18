# pytossinvest

토스증권 [Open API](https://developers.tossinvest.com/docs)의 **비공식(unofficial)** Python 클라이언트입니다.
OAuth 2.0 인증, 계좌 헤더 처리, 에러 파싱, 429 자동 재시도를 처리하며 20개 REST 엔드포인트 전부를 메서드로 제공합니다.

> ⚠️ 본 라이브러리는 토스증권이 제공하는 공식 SDK가 아닙니다. 실제 매매 주문은 신중히 사용하세요.

## 설치

```bash
pip install git+https://github.com/yangs1202/pytossinvest.git
```

또는 소스에서:

```bash
git clone https://github.com/yangs1202/pytossinvest.git
cd pytossinvest
pip install -e ".[dev]"
```

요구 사항: Python 3.8+, `requests`.

## 빠른 시작

`client_id` / `client_secret` 은 토스증권 WTS > **설정 > Open API** 메뉴에서 발급합니다.

```python
from pytossinvest import TossInvestClient

client = TossInvestClient(client_id="c_...", client_secret="s_...")

# 시세·종목 정보 (액세스 토큰만 필요)
client.get_prices("005930")              # 현재가 (다건: ["005930", "AAPL"])
client.get_orderbook("005930")           # 호가
client.get_candles("005930", "1d", count=20)  # 일봉
client.get_exchange_rate("USD", "KRW")   # 환율

# 계좌·자산 (X-Tossinvest-Account 헤더 필요)
accounts = client.get_accounts()
client.account_seq = accounts[0]["accountSeq"]  # 기본 계좌 설정
client.get_holdings()                    # 보유 주식
client.get_buying_power("KRW")           # 매수 가능 금액

# 주문
order = client.create_order(
    symbol="005930", side="BUY", order_type="LIMIT",
    quantity=10, price="70000", client_order_id="my-order-001",
)
client.get_order(order["orderId"])       # 주문 상세
client.cancel_order(order["orderId"])    # 주문 취소
```

`TossInvestClient` 는 컨텍스트 매니저로도 사용할 수 있습니다:

```python
with TossInvestClient(client_id="c_...", client_secret="s_...") as client:
    print(client.get_prices("005930"))
```

## CLI

설치하면 `tossinvest` 명령을 사용할 수 있습니다. 인증은 **설정 파일** 또는 환경변수로 전달합니다.

설정 파일(`~/.tossinvest/token.json`)에 한 번 저장해 두면 어디서나 바로 사용할 수 있습니다:

```bash
mkdir -p ~/.tossinvest && chmod 700 ~/.tossinvest
cat > ~/.tossinvest/token.json <<'JSON'
{
  "client_id": "tsck_live_...",
  "client_secret": "tssk_live_...",
  "account": 1
}
JSON
chmod 600 ~/.tossinvest/token.json
```

또는 환경변수로 전달할 수도 있습니다(설정 파일보다 우선):

```bash
export TOSSINVEST_CLIENT_ID=tsck_live_...
export TOSSINVEST_CLIENT_SECRET=tssk_live_...
export TOSSINVEST_ACCOUNT=1   # 계좌·주문 API 의 accountSeq
```

우선순위는 **명령행 플래그 > 환경변수 > 설정 파일**입니다. 설정 파일 경로는 `TOSSINVEST_CONFIG` 로 변경할 수 있습니다.

```bash
tossinvest price 005930 AAPL          # 현재가 (다건)
tossinvest candles 005930 --interval 1d --count 20
tossinvest accounts                   # 계좌 목록
tossinvest holdings                   # 보유 주식
tossinvest orders --status OPEN       # 진행 중 주문
```

출력은 JSON 이며 `-c/--compact` 로 한 줄 출력합니다. 계좌는 `-a/--account` 로 override 합니다.

**주문 생성·정정·취소는 실거래**이므로 `--yes` 플래그가 없으면 실행되지 않습니다:

```bash
tossinvest order-create --symbol 005930 --side BUY --type LIMIT \
  --quantity 10 --price 70000 --client-order-id my-001 --yes
tossinvest order-cancel <ORDER_ID> --yes
```

종료 코드: `0` 성공 · `1` API 에러 · `2` 인증 정보 누락 · `3` 거래 명령에 `--yes` 누락.
전체 명령은 `tossinvest --help` 또는 `tossinvest <command> --help` 참고.

## Claude Code Skill

`skills/tossinvest/SKILL.md` 에 [Claude Code](https://claude.com/claude-code) skill 이 포함되어 있습니다.
Claude 가 토스증권 시세·계좌·주문 작업을 이 CLI 로 수행하도록 안내합니다. 설치:

```bash
# 사용자 전역 스킬로 링크 (또는 복사)
ln -s "$(pwd)/skills/tossinvest" ~/.claude/skills/tossinvest
```

이후 Claude Code 에서 "삼성전자 현재가 알려줘", "내 토스 주식 잔고 보여줘" 같은 요청에 skill 이 활성화됩니다.

## 인증

토큰 발급은 자동으로 처리됩니다. 첫 API 호출 시 `client_credentials` grant 로 access token 을 발급하고
내부에 캐시하며, 만료 60초 전에 자동으로 재발급합니다. 401(토큰 무효화) 응답을 받으면 토큰을 강제
갱신한 뒤 한 번 재시도합니다. `refresh token` 은 발급되지 않으며, client 당 유효 토큰은 1개입니다.

## 계좌 헤더 (`X-Tossinvest-Account`)

계좌·자산 및 주문 카테고리 API 는 `accountSeq` 가 필요합니다. 두 가지 방법으로 전달합니다.

```python
# 1) 클라이언트 기본값으로 설정
client.account_seq = 1
client.get_holdings()

# 2) 메서드별로 override
client.get_holdings(account_seq=99)
```

설정 없이 계좌 API 를 호출하면 `TossInvestError` 가 발생합니다.

## 에러 처리

에러 응답은 예외로 변환됩니다. 공통 envelope(`error.code`, `error.message`, `error.requestId`,
`error.data`)이 그대로 매핑됩니다.

```python
from pytossinvest import (
    TossInvestAPIError, TossInvestAuthError, TossInvestRateLimitError,
)

try:
    client.create_order("005930", "BUY", "LIMIT", quantity=10, price="70000")
except TossInvestRateLimitError as e:
    print("rate limit, retry after", e.retry_after)
except TossInvestAuthError as e:
    print("인증 실패", e.code)
except TossInvestAPIError as e:
    print(e.status_code, e.code, e.message, e.request_id, e.data)
```

| 예외 | 발생 시점 |
| --- | --- |
| `TossInvestAuthError` | 401 인증 실패 / 토큰 발급 실패 |
| `TossInvestRateLimitError` | 429 rate limit 초과 (재시도 소진 후) |
| `TossInvestAPIError` | 그 외 4xx/5xx |
| `TossInvestError` | 라이브러리 베이스 예외 (예: 계좌 미설정) |

## Rate Limit 재시도

429 응답을 받으면 `Retry-After` 헤더(없으면 지수 백오프 `2^n` + jitter)만큼 대기 후 `max_retries`
(기본 3)까지 재시도합니다. 모두 소진되면 `TossInvestRateLimitError` 를 발생시킵니다.

```python
client = TossInvestClient(client_id="...", client_secret="...", max_retries=5)
```

## API 메서드 매핑

| 메서드 | HTTP | 엔드포인트 |
| --- | --- | --- |
| `fetch_token()` | POST | `/oauth2/token` |
| `get_orderbook(symbol)` | GET | `/api/v1/orderbook` |
| `get_prices(symbols)` | GET | `/api/v1/prices` |
| `get_trades(symbol, count=)` | GET | `/api/v1/trades` |
| `get_price_limits(symbol)` | GET | `/api/v1/price-limits` |
| `get_candles(symbol, interval, count=, before=, adjusted=)` | GET | `/api/v1/candles` |
| `get_stocks(symbols)` | GET | `/api/v1/stocks` |
| `get_stock_warnings(symbol)` | GET | `/api/v1/stocks/{symbol}/warnings` |
| `get_exchange_rate(base_currency, quote_currency, date_time=)` | GET | `/api/v1/exchange-rate` |
| `get_market_calendar_kr(date=)` | GET | `/api/v1/market-calendar/KR` |
| `get_market_calendar_us(date=)` | GET | `/api/v1/market-calendar/US` |
| `get_accounts()` | GET | `/api/v1/accounts` |
| `get_holdings(symbol=, account_seq=)` | GET | `/api/v1/holdings` |
| `create_order(...)` | POST | `/api/v1/orders` |
| `list_orders(status, ...)` | GET | `/api/v1/orders` |
| `get_order(order_id, ...)` | GET | `/api/v1/orders/{orderId}` |
| `modify_order(order_id, ...)` | POST | `/api/v1/orders/{orderId}/modify` |
| `cancel_order(order_id, ...)` | POST | `/api/v1/orders/{orderId}/cancel` |
| `get_buying_power(currency, ...)` | GET | `/api/v1/buying-power` |
| `get_sellable_quantity(symbol, ...)` | GET | `/api/v1/sellable-quantity` |
| `get_commissions(...)` | GET | `/api/v1/commissions` |

모든 조회 메서드는 응답 envelope 의 `result` 값을 그대로 반환합니다 (예: `get_prices` → 리스트,
`get_holdings` → dict). 응답 필드의 정확한 구조는 [공식 API 문서](https://developers.tossinvest.com/docs)와
`docs/openapi.json` (이 저장소에 포함된 OpenAPI 3.1 스펙)을 참조하세요.

## 주문 참고 사항

- `create_order` 는 `quantity`(수량 기반)와 `order_amount`(금액 기반) 중 **정확히 하나**를
  지정해야 합니다. `order_amount` 는 US 시장 정규장 전용입니다.
- 가격/수량/금액은 정밀도 손실을 막기 위해 내부에서 **문자열**로 전송됩니다 (`int`/`float` 도 허용하며
  자동으로 문자열화).
- 1억원 이상 주문은 `confirm_high_value_order=True` 가 필요합니다.
- `client_order_id` 는 멱등성 키로 동작하며 10분간 유효합니다.

## 개발

```bash
pip install -e ".[dev]"
pytest
```

## 라이선스

[MIT](LICENSE)
