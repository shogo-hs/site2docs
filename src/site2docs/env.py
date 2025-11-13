"""環境変数および LLM 設定のローダー。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable, Mapping

DEFAULT_ENV_NAME = ".env"
LLM_API_KEY_ENV = "SITE2DOCS_API_KEY"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
LLM_MODEL_ENV = "SITE2DOCS_MODEL"
OPENAI_MODEL_ENV = "OPENAI_MODEL"


@dataclass(slots=True)
class LLMSettings:
    """LLM 呼び出しに必要な最低限の設定値。"""

    api_key: str | None
    model: str | None


def load_env_file(path: str | Path | None = None) -> dict[str, str]:
    """`.env` ファイルを読み込み、未設定の環境変数を補完します。"""

    env_path = _locate_env_file(path)
    if env_path is None or not env_path.exists():
        return {}
    loaded: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _strip_quotes(value.strip())
        if key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


def current_llm_settings(source: Mapping[str, str] | None = None) -> LLMSettings:
    """現在の環境変数から LLM 設定を読み取ります。"""

    env = source or os.environ
    api_key = env.get(LLM_API_KEY_ENV) or env.get(OPENAI_API_KEY_ENV)
    model = env.get(LLM_MODEL_ENV) or env.get(OPENAI_MODEL_ENV)
    return LLMSettings(api_key=api_key, model=model)


def _locate_env_file(path: str | Path | None) -> Path | None:
    if path is not None:
        candidate = Path(path)
        if candidate.is_dir():
            candidate = candidate / DEFAULT_ENV_NAME
        return candidate
    candidates: Iterable[Path] = (
        Path.cwd() / DEFAULT_ENV_NAME,
        Path(__file__).resolve().parents[2] / DEFAULT_ENV_NAME,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _strip_quotes(value: str) -> str:
    if not value:
        return value
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value
