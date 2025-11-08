from __future__ import annotations

from pathlib import Path

import pytest

from site2docs import cli


@pytest.mark.parametrize(
    "options",
    [
        {
            "min_content_characters": "200",
            "semantic_min_length": "800",
            "semantic_length_ratio": "1.5",
            "semantic_min_delta": "150",
        }
    ],
)
def test_cli_collects_extraction_overrides(tmp_path: Path, options: dict[str, str]) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    args_list = [
        "--input",
        str(input_dir),
        "--out",
        str(output_dir),
        "--min-content-chars",
        options["min_content_characters"],
        "--semantic-min-length",
        options["semantic_min_length"],
        "--semantic-length-ratio",
        options["semantic_length_ratio"],
        "--semantic-min-delta",
        options["semantic_min_delta"],
        "--no-readability",
        "--no-semantic-fallback",
    ]
    args = cli.parse_args(args_list)
    overrides = cli._collect_extraction_overrides(args)

    assert overrides["min_content_characters"] == int(options["min_content_characters"])
    assert overrides["semantic_min_length"] == int(options["semantic_min_length"])
    assert overrides["semantic_length_ratio"] == float(options["semantic_length_ratio"])
    assert overrides["semantic_min_delta"] == int(options["semantic_min_delta"])
    assert overrides["readability"] is False
    assert overrides["semantic_body_fallback"] is False


def test_cli_collects_graph_overrides(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_dir = tmp_path / "output"
    args = cli.parse_args(
        [
            "--input",
            str(input_dir),
            "--out",
            str(output_dir),
            "--min-cluster-size",
            "1",
            "--allow-singleton-clusters",
            "--max-network-cluster-size",
            "10",
            "--directory-cluster-depth",
            "3",
            "--url-pattern-depth",
            "2",
            "--label-tfidf-terms",
            "8",
        ]
    )
    overrides = cli._collect_graph_overrides(args)

    assert overrides["min_cluster_size"] == 1
    assert overrides["allow_singleton_clusters"] is True
    assert overrides["max_network_cluster_size"] == 10
    assert overrides["directory_cluster_depth"] == 3
    assert overrides["url_pattern_depth"] == 2
    assert overrides["label_tfidf_terms"] == 8
