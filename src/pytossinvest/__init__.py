"""pytossinvest — 토스증권 Open API Python 클라이언트.

비공식(unofficial) wrapper 입니다. 토스증권 Open API 의 OAuth 2.0 인증과
20개 REST 엔드포인트를 파이썬 메서드로 제공합니다.

기본 사용법::

    from pytossinvest import TossInvestClient

    client = TossInvestClient(client_id="c_...", client_secret="s_...")
    print(client.get_prices("005930"))
"""

from .client import TossInvestClient
from .exceptions import (
    TossInvestAPIError,
    TossInvestAuthError,
    TossInvestError,
    TossInvestRateLimitError,
)

__version__ = "0.1.0"

__all__ = [
    "TossInvestClient",
    "TossInvestError",
    "TossInvestAPIError",
    "TossInvestAuthError",
    "TossInvestRateLimitError",
    "__version__",
]
