---
description: 토스증권 종목 현재가 조회 (다건 가능)
argument-hint: "<종목심볼...> (예: 005930 AAPL)"
allowed-tools: Bash(tossinvest:*)
---

다음은 요청한 종목의 현재가입니다 (`tossinvest price $ARGUMENTS`):

!`tossinvest price $ARGUMENTS`

위 결과를 사람이 읽기 좋게 종목별 현재가·통화·시각으로 요약해줘. 에러가 있으면 원인과 해결 방법을 알려줘. (CLI 가 없으면 SKILL 의 uv 설치 안내를, 인증 오류면 키 설정 안내를 제시.)
