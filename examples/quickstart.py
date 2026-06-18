"""pytossinvest 빠른 시작 예제.

실행 전 환경변수를 설정하세요::

    export TOSSINVEST_CLIENT_ID="c_..."
    export TOSSINVEST_CLIENT_SECRET="s_..."

토스증권 WTS > 설정 > Open API 에서 client_id / client_secret 을 발급받습니다.
"""

import os

from pytossinvest import TossInvestClient, TossInvestAPIError


def main() -> None:
    client = TossInvestClient(
        client_id=os.environ["TOSSINVEST_CLIENT_ID"],
        client_secret=os.environ["TOSSINVEST_CLIENT_SECRET"],
    )

    # --- 시세·종목 정보 (토큰만 필요) ---
    print("현재가:", client.get_prices("005930"))
    print("종목정보:", client.get_stocks(["005930", "AAPL"]))
    print("일봉:", client.get_candles("005930", interval="1d", count=5))
    print("환율:", client.get_exchange_rate("USD", "KRW"))

    # --- 계좌·자산 (X-Tossinvest-Account 헤더 필요) ---
    accounts = client.get_accounts()
    if not accounts:
        print("계좌가 없습니다.")
        return
    client.account_seq = accounts[0]["accountSeq"]
    print("보유주식:", client.get_holdings())
    print("매수가능금액:", client.get_buying_power("KRW"))

    # --- 주문 (실거래 주의) ---
    try:
        order = client.create_order(
            symbol="005930",
            side="BUY",
            order_type="LIMIT",
            quantity=1,
            price=70000,
            client_order_id="example-001",
        )
        print("주문 생성:", order)
        print("주문 상세:", client.get_order(order["orderId"]))
    except TossInvestAPIError as e:
        print(f"주문 실패: code={e.code} message={e.message}")


if __name__ == "__main__":
    main()
