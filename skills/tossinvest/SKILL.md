---
name: tossinvest
description: 토스증권 Open API로 국내(KRX)·미국 주식의 시세/호가/체결/캔들, 종목 정보, 환율, 장 운영 시간을 조회하고, 본인 계좌의 보유 주식·매수가능금액·주문을 조회/생성/정정/취소한다. "토스증권", "토스 주식", "내 주식 잔고", "삼성전자 현재가", "매수/매도 주문", "보유 종목", "tossinvest" 등 토스증권 계좌·시세·주문 작업이 필요할 때 사용.
---

# Toss Invest (토스증권 Open API)

`pytossinvest` 패키지의 `tossinvest` CLI 로 토스증권 Open API 를 다룬다.
20개 REST 엔드포인트(시세·종목·환율·장운영·계좌·자산·주문)를 커버한다.

## 사전 준비

1. 설치 (한 번만):
   ```bash
   pip install git+https://github.com/yangs1202/pytossinvest.git
   ```
2. 인증 — 토스증권 WTS > 설정 > Open API 에서 발급한 키를 설정 파일 또는 환경변수로 설정.
   설정 파일 `~/.tossinvest/token.json` (권한 600) 에 두면 어디서나 바로 동작한다:
   ```json
   { "client_id": "tsck_live_...", "client_secret": "tssk_live_...", "account": 1 }
   ```
   또는 환경변수(설정 파일보다 우선):
   ```bash
   export TOSSINVEST_CLIENT_ID=tsck_live_...
   export TOSSINVEST_CLIENT_SECRET=tssk_live_...
   export TOSSINVEST_ACCOUNT=1   # 계좌·주문 API 용 accountSeq (accounts 로 확인)
   ```
   우선순위는 플래그 > 환경변수 > 설정 파일. 키가 없으면 사용자에게 발급/설정을 요청한다.
   **키는 절대 로그·터미널 출력·커밋에 그대로 노출하지 않는다.**

## 안전 수칙 (중요)

- 시세·조회 명령은 자유롭게 사용해도 된다.
- **주문 생성·정정·취소(`order-create` / `order-modify` / `order-cancel`)는 실제 체결되는 실거래다.**
  - 이 명령들은 `--yes` 플래그가 없으면 실행되지 않는다(가드).
  - 실행 전 반드시 사용자에게 **종목·방향·수량·가격을 요약해 확인받는다.**
  - 테스트 목적이면 현재가에서 크게 벗어난 지정가(체결 안 될 가격)로 주문 후 즉시 취소한다.
  - 미국장 휴장 여부는 `calendar-us` 로, 매수가능금액은 `buying-power` 로, 매도가능수량은 `sellable` 로 먼저 확인한다.

## CLI 사용법

출력은 JSON. `-c` 는 한 줄 출력, `-a/--account` 로 accountSeq override.

### 시세·종목 정보 (토큰만 필요)
```bash
tossinvest orderbook 005930                 # 호가
tossinvest price 005930 AAPL                 # 현재가 (다건: 공백/콤마)
tossinvest trades 005930 --count 10          # 최근 체결
tossinvest price-limits 005930               # 상/하한가
tossinvest candles 005930 --interval 1d --count 20   # 캔들 (1m|1d)
tossinvest stock 005930 AAPL                 # 종목 기본 정보
tossinvest warnings 005930                   # 매수 유의사항(VI 등)
```

### 환율·장 운영 시간
```bash
tossinvest exchange-rate --base USD --quote KRW
tossinvest calendar-kr                       # 국내 장 운영
tossinvest calendar-us --date 2026-03-25     # 미국 장 운영
```

### 계좌·자산 (accountSeq 필요)
```bash
tossinvest accounts                          # 계좌 목록 → accountSeq 확인
tossinvest holdings                          # 보유 주식 (특정 종목: holdings 005930)
tossinvest buying-power KRW                   # 매수 가능 금액
tossinvest sellable 005930                   # 판매 가능 수량
tossinvest commissions                       # 매매 수수료
```

### 주문 조회
```bash
tossinvest orders --status OPEN              # 진행 중 주문
tossinvest orders --status CLOSED --limit 20 # 종료 주문
tossinvest order <ORDER_ID>                  # 주문 상세
```

### 주문 (실거래 — --yes 필수, 사전 확인 필수)
```bash
# 지정가 매수 (수량 기반)
tossinvest order-create --symbol 005930 --side BUY --type LIMIT \
  --quantity 10 --price 70000 --client-order-id my-001 --yes

# 금액 기반 매수 (US 정규장 전용)
tossinvest order-create --symbol AAPL --side BUY --type MARKET --amount 100 --yes

# 정정 (KR 은 --quantity 필수, US 는 가격만)
tossinvest order-modify <ORDER_ID> --type LIMIT --quantity 15 --price 71000 --yes

# 취소
tossinvest order-cancel <ORDER_ID> --yes
```

주문 참고:
- `--quantity`(수량) 와 `--amount`(금액) 중 정확히 하나만 사용. `--amount` 는 US 전용.
- `LIMIT` 은 `--price` 필수, `MARKET` 은 `--price` 전달 불가.
- 1억원 이상 주문은 `--high-value` 필요.
- `--client-order-id` 는 멱등성 키(10분 유효).

## Python 라이브러리로 직접 쓰기

스크립트/자동화가 필요하면 라이브러리를 직접 사용한다:
```python
from pytossinvest import TossInvestClient, TossInvestAPIError

client = TossInvestClient(client_id="...", client_secret="...", account_seq=1)
print(client.get_prices(["005930", "AAPL"]))
print(client.get_holdings())
```
조회 메서드는 응답 envelope 의 `result` 를 그대로 반환한다(dict/list).

## 종료 코드 (스크립트에서 분기 시)
- `0` 성공 · `1` API 에러(stderr 에 에러 JSON) · `2` 인증 정보 누락 · `3` 거래 명령에 `--yes` 누락

## 에러 처리
에러는 `{"error": {"status","code","message","requestId","data"}}` 형태로 stderr 에 출력된다.
대표 코드: `invalid-token`(토큰 무효, 재발급 필요), `order-hours-closed`(주문 시간 아님),
`insufficient-buying-power`(잔고 부족), `stock-not-found`, `rate-limit-exceeded`(429, 자동 재시도됨).

## 참고
- 공식 문서: https://developers.tossinvest.com/docs
- OpenAPI 스펙: 저장소의 `docs/openapi.json`
