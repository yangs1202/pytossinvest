"""pytossinvest 커맨드라인 인터페이스.

사용 예::

    export TOSSINVEST_CLIENT_ID=c_...
    export TOSSINVEST_CLIENT_SECRET=s_...
    tossinvest price 005930 000660
    tossinvest accounts
    tossinvest -a 1 holdings

인증 정보는 환경변수 또는 전역 옵션으로 전달합니다:
    --client-id / TOSSINVEST_CLIENT_ID
    --client-secret / TOSSINVEST_CLIENT_SECRET
    --account / TOSSINVEST_ACCOUNT (계좌 API 의 accountSeq)

자격증명은 설정 파일 ``~/.tossinvest/token.json`` 에서도 읽습니다(우선순위는
플래그 > 환경변수 > 설정 파일). 파일 형식::

    {
      "client_id": "tsck_live_...",
      "client_secret": "tssk_live_...",
      "account": 1
    }

설정 파일 경로는 환경변수 ``TOSSINVEST_CONFIG`` 로 변경할 수 있습니다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, List, Optional

from . import __version__
from .client import DEFAULT_BASE_URL, TossInvestClient
from .exceptions import TossInvestError, TossInvestAPIError

DEFAULT_CONFIG_PATH = "~/.tossinvest/token.json"


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tossinvest",
        description="토스증권 Open API 커맨드라인 도구 (비공식)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--client-id", default=os.environ.get("TOSSINVEST_CLIENT_ID"))
    p.add_argument(
        "--client-secret", default=os.environ.get("TOSSINVEST_CLIENT_SECRET")
    )
    p.add_argument(
        "-a",
        "--account",
        type=int,
        default=_env_int("TOSSINVEST_ACCOUNT"),
        help="계좌 accountSeq (계좌·자산·주문 API 에 필요)",
    )
    p.add_argument("--base-url", default=None, help="API 베이스 URL override")
    p.add_argument(
        "-c", "--compact", action="store_true", help="JSON 을 한 줄로 출력"
    )

    sub = p.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # --- 시세·종목 정보 ---
    sp = sub.add_parser("token", help="액세스 토큰 발급 (디버그용)")
    sp.set_defaults(func=lambda c, a: c.fetch_token())

    sp = sub.add_parser("orderbook", help="호가 조회")
    sp.add_argument("symbol")
    sp.set_defaults(func=lambda c, a: c.get_orderbook(a.symbol))

    sp = sub.add_parser("price", help="현재가 조회 (다건 가능)")
    sp.add_argument("symbols", nargs="+", help="종목 심볼 (공백 또는 콤마 구분)")
    sp.set_defaults(func=lambda c, a: c.get_prices(_symbols(a.symbols)))

    sp = sub.add_parser("trades", help="최근 체결 내역 조회")
    sp.add_argument("symbol")
    sp.add_argument("--count", type=int, help="조회 건수 (1~50)")
    sp.set_defaults(func=lambda c, a: c.get_trades(a.symbol, count=a.count))

    sp = sub.add_parser("price-limits", help="상/하한가 조회")
    sp.add_argument("symbol")
    sp.set_defaults(func=lambda c, a: c.get_price_limits(a.symbol))

    sp = sub.add_parser("candles", help="캔들(OHLCV) 차트 조회")
    sp.add_argument("symbol")
    sp.add_argument(
        "--interval", required=True, choices=["1m", "1d"], help="봉 간격"
    )
    sp.add_argument("--count", type=int, help="조회 봉 개수 (최대 200)")
    sp.add_argument("--before", help="이 시각 이전 봉 조회 (date-time)")
    sp.add_argument("--adjusted", action="store_true", help="수정주가 적용")
    sp.set_defaults(
        func=lambda c, a: c.get_candles(
            a.symbol,
            interval=a.interval,
            count=a.count,
            before=a.before,
            adjusted=a.adjusted or None,
        )
    )

    sp = sub.add_parser("stock", help="종목 기본 정보 조회 (다건 가능)")
    sp.add_argument("symbols", nargs="+")
    sp.set_defaults(func=lambda c, a: c.get_stocks(_symbols(a.symbols)))

    sp = sub.add_parser("warnings", help="매수 유의사항 조회")
    sp.add_argument("symbol")
    sp.set_defaults(func=lambda c, a: c.get_stock_warnings(a.symbol))

    # --- 환율·장 운영 시간 ---
    sp = sub.add_parser("exchange-rate", help="환율 조회")
    sp.add_argument("--base", required=True, choices=["KRW", "USD"])
    sp.add_argument("--quote", required=True, choices=["KRW", "USD"])
    sp.add_argument("--datetime", dest="dt", help="조회 시각 (date-time)")
    sp.set_defaults(
        func=lambda c, a: c.get_exchange_rate(a.base, a.quote, date_time=a.dt)
    )

    sp = sub.add_parser("calendar-kr", help="국내 장 운영 정보 조회")
    sp.add_argument("--date", help="조회 기준일 (YYYY-MM-DD)")
    sp.set_defaults(func=lambda c, a: c.get_market_calendar_kr(date=a.date))

    sp = sub.add_parser("calendar-us", help="해외(미국) 장 운영 정보 조회")
    sp.add_argument("--date", help="조회 기준일 (YYYY-MM-DD)")
    sp.set_defaults(func=lambda c, a: c.get_market_calendar_us(date=a.date))

    # --- 계좌·자산 ---
    sp = sub.add_parser("accounts", help="계좌 목록 조회")
    sp.set_defaults(func=lambda c, a: c.get_accounts())

    sp = sub.add_parser("holdings", help="보유 주식 조회")
    sp.add_argument("symbol", nargs="?", help="특정 종목 필터 (선택)")
    sp.set_defaults(func=lambda c, a: c.get_holdings(symbol=a.symbol))

    # --- 거래 가능 정보 ---
    sp = sub.add_parser("buying-power", help="매수 가능 금액 조회")
    sp.add_argument("currency", choices=["KRW", "USD"])
    sp.set_defaults(func=lambda c, a: c.get_buying_power(a.currency))

    sp = sub.add_parser("sellable", help="판매 가능 수량 조회")
    sp.add_argument("symbol")
    sp.set_defaults(func=lambda c, a: c.get_sellable_quantity(a.symbol))

    sp = sub.add_parser("commissions", help="매매 수수료 조회")
    sp.set_defaults(func=lambda c, a: c.get_commissions())

    # --- 주문 조회 ---
    sp = sub.add_parser("orders", help="주문 목록 조회")
    sp.add_argument("--status", required=True, choices=["OPEN", "CLOSED"])
    sp.add_argument("--symbol")
    sp.add_argument("--from", dest="from_date", help="조회 시작일 (YYYY-MM-DD)")
    sp.add_argument("--to", dest="to_date", help="조회 종료일 (YYYY-MM-DD)")
    sp.add_argument("--cursor")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(
        func=lambda c, a: c.list_orders(
            a.status,
            symbol=a.symbol,
            from_date=a.from_date,
            to_date=a.to_date,
            cursor=a.cursor,
            limit=a.limit,
        )
    )

    sp = sub.add_parser("order", help="주문 상세 조회")
    sp.add_argument("order_id")
    sp.set_defaults(func=lambda c, a: c.get_order(a.order_id))

    # --- 주문 생성·정정·취소 (거래성: --yes 필요) ---
    sp = sub.add_parser("order-create", help="주문 생성 (실거래! --yes 필요)")
    sp.add_argument("--symbol", required=True)
    sp.add_argument("--side", required=True, choices=["BUY", "SELL"])
    sp.add_argument("--type", dest="order_type", required=True, choices=["LIMIT", "MARKET"])
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--quantity", help="주문 수량 (주)")
    g.add_argument("--amount", help="주문 금액 (달러, US 전용)")
    sp.add_argument("--price", help="지정가 (LIMIT 일 때)")
    sp.add_argument("--tif", choices=["DAY", "CLS"], help="주문 유효 조건")
    sp.add_argument("--client-order-id", help="멱등성 키")
    sp.add_argument("--high-value", action="store_true", help="1억원 이상 주문 확인")
    sp.add_argument("--yes", action="store_true", help="실거래 실행 확인")
    sp.set_defaults(func=_cmd_order_create, _trade=True)

    sp = sub.add_parser("order-modify", help="주문 정정 (실거래! --yes 필요)")
    sp.add_argument("order_id")
    sp.add_argument("--type", dest="order_type", required=True, choices=["LIMIT", "MARKET"])
    sp.add_argument("--quantity", help="변경할 수량 (KR 필수)")
    sp.add_argument("--price", help="변경할 가격 (LIMIT 일 때)")
    sp.add_argument("--high-value", action="store_true")
    sp.add_argument("--yes", action="store_true", help="실거래 실행 확인")
    sp.set_defaults(func=_cmd_order_modify, _trade=True)

    sp = sub.add_parser("order-cancel", help="주문 취소 (실거래! --yes 필요)")
    sp.add_argument("order_id")
    sp.add_argument("--yes", action="store_true", help="실거래 실행 확인")
    sp.set_defaults(func=lambda c, a: c.cancel_order(a.order_id), _trade=True)

    return p


def _cmd_order_create(c: TossInvestClient, a: argparse.Namespace) -> Any:
    return c.create_order(
        symbol=a.symbol,
        side=a.side,
        order_type=a.order_type,
        quantity=a.quantity,
        order_amount=a.amount,
        price=a.price,
        time_in_force=a.tif,
        client_order_id=a.client_order_id,
        confirm_high_value_order=a.high_value or None,
    )


def _cmd_order_modify(c: TossInvestClient, a: argparse.Namespace) -> Any:
    return c.modify_order(
        a.order_id,
        order_type=a.order_type,
        quantity=a.quantity,
        price=a.price,
        confirm_high_value_order=a.high_value or None,
    )


def _env_int(name: str) -> Optional[int]:
    val = os.environ.get(name)
    return int(val) if val else None


def _load_config() -> dict:
    """``~/.tossinvest/token.json`` (또는 TOSSINVEST_CONFIG) 에서 자격증명을 읽는다.

    파일이 없으면 빈 dict 를 반환하고, 손상된 경우 경고만 출력한다.
    """
    path = os.path.expanduser(
        os.environ.get("TOSSINVEST_CONFIG", DEFAULT_CONFIG_PATH)
    )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (ValueError, OSError) as e:
        print(f"경고: 설정 파일을 읽을 수 없습니다 ({path}): {e}", file=sys.stderr)
        return {}


def _symbols(values: List[str]) -> str:
    """공백 분리 인자와 콤마 분리 인자를 모두 콤마 문자열로 정규화."""
    out: List[str] = []
    for v in values:
        out.extend(s for s in v.split(",") if s)
    return ",".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    # 우선순위: 플래그/환경변수(args) > 설정 파일(~/.tossinvest/token.json)
    cfg = _load_config()
    client_id = args.client_id or cfg.get("client_id")
    client_secret = args.client_secret or cfg.get("client_secret")
    account = args.account
    if account is None and cfg.get("account") is not None:
        account = int(cfg["account"])
    base_url = args.base_url or cfg.get("base_url") or DEFAULT_BASE_URL

    if not client_id or not client_secret:
        print(
            "오류: client_id/client_secret 이 필요합니다. "
            "--client-id/--client-secret, 환경변수 "
            "TOSSINVEST_CLIENT_ID/TOSSINVEST_CLIENT_SECRET, 또는 설정 파일 "
            f"{DEFAULT_CONFIG_PATH} 를 설정하세요.",
            file=sys.stderr,
        )
        return 2

    # 거래성 명령은 --yes 없이는 실행하지 않습니다.
    if getattr(args, "_trade", False) and not getattr(args, "yes", False):
        print(
            "거부: 이 명령은 실거래입니다. 실행하려면 --yes 를 추가하세요.",
            file=sys.stderr,
        )
        return 3

    client = TossInvestClient(
        client_id=client_id,
        client_secret=client_secret,
        account_seq=account,
        base_url=base_url,
    )
    try:
        with client:
            result = args.func(client, args)
    except TossInvestAPIError as e:
        payload = {
            "error": {
                "status": e.status_code,
                "code": e.code,
                "message": e.message,
                "requestId": e.request_id,
                "data": e.data,
            }
        }
        print(json.dumps(payload, ensure_ascii=False, indent=None if args.compact else 2),
              file=sys.stderr)
        return 1
    except TossInvestError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1

    indent = None if args.compact else 2
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
