import json
from pathlib import Path

import pytest

from app.modules.curriculum import CurriculumBaseline, CurriculumBaselineError


def test_curriculum_baseline_rejects_catalog_drift(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.csv"
    catalog.write_text("sealed", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "baseline_id": "v1",
        "catalog_sha256": "0" * 64,
        "official_sources": [{"authority": "中华人民共和国教育部", "title": "课程标准"}],
    }, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CurriculumBaselineError, match="偏离封存基线"):
        CurriculumBaseline.load(manifest, catalog)


def test_curriculum_baseline_hash_is_newline_stable(tmp_path: Path) -> None:
    content = "node_id,title\nnode1,函数的概念\n".encode("utf-8")
    catalog_lf = tmp_path / "catalog-lf.csv"
    catalog_crlf = tmp_path / "catalog-crlf.csv"
    catalog_lf.write_bytes(content)
    catalog_crlf.write_bytes(content.replace(b"\n", b"\r\n"))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({
            "baseline_id": "v1",
            "catalog_sha256": "77f6e613060749c6ce27e95891858c4fb5d93e9c9c8c2e4c8fffc20068753010",
            "official_sources": [{"authority": "中华人民共和国教育部", "title": "课程标准"}],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    lf_baseline = CurriculumBaseline.load(manifest, catalog_lf)
    crlf_baseline = CurriculumBaseline.load(manifest, catalog_crlf)

    assert lf_baseline.baseline_id == "v1"
    assert crlf_baseline.baseline_id == "v1"
