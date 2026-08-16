"""Production Fixture Isolation（Prompt 3.5 §8-9）。

Gate：
- 生产 Search Agent 不得读取 data/test-fixtures（静态架构守卫 + 行为测试）。
- 生产默认 bank 位于 data/runtime（商业数据 DENY BY DEFAULT）。
- data/commercial-approved/ 初始只允许 README / policy，不包含任何题目内容。
- 即使 Tool 证据中出现 synthetic 题目 ID，只要生产 bank 为空（commercial-approved 为空），
  搜索结果必须真实返回 0 results / 诚实空状态，而不是 synthetic fixture。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.modules.curriculum import CsvCurriculumCatalog
from app.modules.question_bank import QuestionBank
from app.modules.search_agent.pipeline import SearchAgentPipeline

from tests.test_search_agent_pipeline import (
    FakeRuntime,
    _pipeline,
    _result,
    _run,
    _search_call,
    _search_item,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SEARCH_AGENT_MODULES = [
    REPO_ROOT / "apps" / "api" / "app" / "modules" / "search_agent",
    REPO_ROOT / "apps" / "api" / "app" / "routes" / "search_agent.py",
    REPO_ROOT / "apps" / "api" / "app" / "routes" / "internal_agent_tools.py",
]
_CURRICULUM_CSV = (
    REPO_ROOT
    / "docs"
    / "high-school-math-ai"
    / "curriculum"
    / "pep-a-full-knowledge-tree-v1.csv"
)


def test_production_modules_never_reference_test_fixtures() -> None:
    """静态守卫：生产 Search Agent 代码不得出现 test-fixtures 路径。"""
    offenders: list[str] = []
    for target in SEARCH_AGENT_MODULES:
        if target.is_dir():
            files = sorted(target.glob("*.py"))
        else:
            files = [target] if target.exists() else []
        for file in files:
            for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
                if "test-fixtures" in line:
                    offenders.append(f"{file}:{line_no}")
    assert not offenders, f"生产代码引用了 test-fixtures: {offenders}"


def test_default_bank_path_is_runtime_not_test_fixtures() -> None:
    settings = get_settings()
    db_path = str(settings.question_bank_db)
    assert "test-fixtures" not in db_path
    assert "runtime" in db_path


def test_empty_production_like_bank_returns_honest_zero_results(tmp_path: Path) -> None:
    """commercial-approved 为空（生产 bank 无内容）时，即使证据出现 synthetic ID，
    搜索结果必须为 0 + 诚实空状态；synthetic fixture 不得进入生产路径。"""
    bank = QuestionBank(tmp_path / "production-like.sqlite3")  # 空 bank
    catalog = CsvCurriculumCatalog(_CURRICULUM_CSV)
    runtime = FakeRuntime(_result([
        _search_call([
            _search_item("q_sa_focus_01"),
            _search_item("q_sa_focus_02"),
        ]),
    ]))
    response = _run(_pipeline(bank, catalog, runtime).run("给我找椭圆题"))
    assert response.results == []
    assert response.returned_count == 0
    assert "没有找到完全满足条件" in response.answer_summary
    assert response.exact_match is False
    assert all("q_sa_" not in item.question_id for item in response.results)


def test_commercial_approved_contains_no_question_content() -> None:
    """data/commercial-approved/ 只允许 README / policy（.md），不包含题目内容。"""
    root = REPO_ROOT / "data" / "commercial-approved"
    assert root.is_dir()
    content_files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix not in {".md", ".markdown", ".txt"}:
                content_files.append(str(path))
    assert not content_files, f"commercial-approved 包含非 policy 文件: {content_files}"
    markdowns = [path for path in sorted(root.rglob("*")) if path.is_file()]
    assert markdowns, "commercial-approved 至少需要 README / policy"