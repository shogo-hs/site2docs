from __future__ import annotations

from pathlib import Path

from site2docs.config import BuildConfig


def test_from_args_merges_expand_texts_case_insensitively(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    config = BuildConfig.from_args(
        input_dir=tmp_path,
        output_dir=output_dir,
        expand_texts=["Read More", "追加"],
    )

    expand_texts = config.render.expand_texts

    read_more_variants = [text for text in expand_texts if text.lower() == "read more"]
    assert len(read_more_variants) == 1
    assert "追加" in expand_texts
