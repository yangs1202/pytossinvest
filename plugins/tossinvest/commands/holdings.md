---
description: 토스증권 보유 주식 조회 (계좌 전체 또는 특정 종목)
argument-hint: "[종목심볼] (생략 시 전체)"
allowed-tools: Bash(tossinvest:*)
---

다음은 보유 주식 현황입니다 (`tossinvest holdings $ARGUMENTS`):

!`tossinvest holdings $ARGUMENTS`

위 결과를 종목별 수량·평가금액·손익과 계좌 합산 평가금액/손익으로 정리해줘. 금액은 통화 단위를 명확히 표기하고, 손익은 +/− 와 수익률(%)을 함께 보여줘. 보유 종목이 없으면 그 사실을 알려줘.
