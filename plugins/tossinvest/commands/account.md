---
description: 토스증권 계좌 요약 (계좌 목록·보유주식·매수가능금액)
allowed-tools: Bash(tossinvest:*)
---

토스증권 계좌 현황을 모아봅니다.

계좌 목록:
!`tossinvest -c accounts`

보유 주식:
!`tossinvest -c holdings`

원화 매수 가능 금액:
!`tossinvest -c buying-power KRW`

위 세 결과를 묶어 계좌 한눈 요약을 만들어줘: 계좌(accountSeq), 총 평가금액과 손익, 주요 보유 종목, 매수 가능 금액. 인증/계좌 오류가 있으면 원인과 해결 방법을 알려줘.
