from __future__ import annotations

import os
from pathlib import Path

from site2docs import env


def test_load_env_file_populates_missing_variables(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
        # comment
        SITE2DOCS_API_KEY=sk-test
        SITE2DOCS_MODEL="gpt-example"
        OPENAI_MODEL=gpt-ignored
        """,
        encoding="utf-8",
    )
    monkeypatch.delenv("SITE2DOCS_API_KEY", raising=False)
    monkeypatch.delenv("SITE2DOCS_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "preserve")

    loaded = env.load_env_file(env_path)

    assert loaded["SITE2DOCS_API_KEY"] == "sk-test"
    assert loaded["SITE2DOCS_MODEL"] == "gpt-example"
    assert os.environ["SITE2DOCS_API_KEY"] == "sk-test"
    # 既存の環境変数は上書きしない
    assert os.environ["OPENAI_MODEL"] == "preserve"


def test_current_llm_settings_prefers_site2docs_vars(monkeypatch) -> None:
    monkeypatch.setenv("SITE2DOCS_API_KEY", "sk-site")
    monkeypatch.setenv("SITE2DOCS_MODEL", "gpt-site")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-openai")

    settings = env.current_llm_settings()

    assert settings.api_key == "sk-site"
    assert settings.model == "gpt-site"
