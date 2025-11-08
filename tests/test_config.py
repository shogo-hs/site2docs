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


def test_from_args_accepts_extraction_and_graph_overrides(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    config = BuildConfig.from_args(
        input_dir=tmp_path,
        output_dir=output_dir,
        extraction_overrides={
            "min_content_characters": 100,
            "semantic_body_fallback": False,
        },
        graph_overrides={
            "min_cluster_size": 1,
            "allow_singleton_clusters": True,
        },
    )

    assert config.extract.min_content_characters == 100
    assert config.extract.semantic_body_fallback is False
    assert config.graph.min_cluster_size == 1
    assert config.graph.allow_singleton_clusters is True
