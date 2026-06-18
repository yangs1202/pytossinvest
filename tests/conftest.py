"""테스트 격리 설정.

실제 ``~/.tossinvest/token.json`` 설정 파일이나 사용자 환경변수가 CLI 테스트에
새지 않도록, 모든 테스트에서 자격증명 소스를 비운다. 개별 테스트는 필요 시
``monkeypatch.setenv`` 로 자체 설정 파일을 다시 지정한다.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("TOSSINVEST_CONFIG", str(tmp_path / "no-such-config.json"))
    monkeypatch.delenv("TOSSINVEST_CLIENT_ID", raising=False)
    monkeypatch.delenv("TOSSINVEST_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TOSSINVEST_ACCOUNT", raising=False)
