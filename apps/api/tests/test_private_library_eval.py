"""Fixed M6 synthetic evaluation; never reads real teacher resources."""

from __future__ import annotations

import asyncio
import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.agent_runtime import (
    TeacherAgentError,
    TeacherAgentErrorCode,
    TeacherAgentRunResult,
    TeacherAgentRunStatus,
    TeacherAgentToolCall,
)
from app.modules.private_library import (
    LibraryIngestCommand,
    LibraryLifecycleCommand,
    LibraryTextReviewCommand,
    OCRProviderError,
    PrivateLibrary,
    PrivateLibraryError,
    PrivateRetrievalConsentError,
    PrivateRetrievalGrantRegistry,
)
from app.modules.private_library_agent import (
    PrivateLibraryAgentCommand,
    PrivateLibraryAgentWorkflow,
)
from app.modules.question_bank import QuestionBank


_CASES = Path(__file__).resolve().parents[3] / "data" / "test-fixtures" / "private-library" / "eval-cases.json"


def _png(red: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (20, 20), (red, 245, 238)).save(output, format="PNG")
    return output.getvalue()


def _ingest(library: PrivateLibrary, *, owner: str, title: str, red: int):
    return library.ingest(
        LibraryIngestCommand(
            title=title,
            rights_basis="original",
            rights_statement="项目自建 M6 固定评测资料，仅用于自动化测试。",
            rights_acknowledged=True,
            owner_id=owner,
        ),
        filename=f"synthetic-{red}.png",
        content=_png(red),
    )


def _confirm(library: PrivateLibrary, item_id: str, *, owner: str, text: str):
    return library.review(
        item_id,
        LibraryTextReviewCommand(corrected_text=text, note="synthetic eval", confirm=True),
        owner_id=owner,
        reviewer_id=owner,
    )


def _tool_output(query: str) -> dict:
    return {
        "ok": True,
        "query": query,
        "items": [{
            "library_item_id": "lib_eval",
            "title": "项目自建函数讲义",
            "excerpt": "函数单调性的项目自建例题。",
            "source_version": 2,
            "rights_basis": "original",
            "text_review_status": "confirmed",
            "visibility": "private",
        }],
        "total": 1,
        "truncated": False,
        "content_scope": "matching_excerpts",
        "visibility": "private",
        "request_id": "req_eval_tool",
        "error": None,
    }


class _ScenarioRuntime:
    runtime_name = "dsh"

    def __init__(self, statuses: list[TeacherAgentRunStatus], errors: list[TeacherAgentError | None] | None = None):
        self.statuses = statuses
        self.errors = errors or [None] * len(statuses)
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        index = len(self.requests) - 1
        status = self.statuses[min(index, len(self.statuses) - 1)]
        error = self.errors[min(index, len(self.errors) - 1)]
        query = request.user_message.split("检索查询：", 1)[1].splitlines()[0]
        calls = []
        if status == TeacherAgentRunStatus.COMPLETED:
            calls = [TeacherAgentToolCall(
                tool_name="search_private_library",
                status="ok",
                output=_tool_output(query),
            )]
        return TeacherAgentRunResult(
            run_id=f"run_eval_{index}",
            session_id="tch_eval",
            request_id=request.request_id,
            runtime="dsh",
            status=status,
            tool_calls=calls,
            error=error,
        )


def _run_workflow(runtime: _ScenarioRuntime):
    workflow = PrivateLibraryAgentWorkflow(
        runtime=runtime,
        grants=PrivateRetrievalGrantRegistry(),
    )
    response = asyncio.run(workflow.run(
        PrivateLibraryAgentCommand(query="函数单调性", private_content_consent=True),
        owner_id="teacher_eval",
    ))
    return workflow, response


def test_private_library_agent_fixed_synthetic_evaluation(tmp_path: Path) -> None:
    fixture = json.loads(_CASES.read_text(encoding="utf-8"))
    case_ids = {case["id"] for case in fixture["cases"]}
    assert fixture["evaluation_id"] == "private-library-agent-synthetic-v1"
    assert fixture["source"] == "project-authored-synthetic"
    assert case_ids == {
        "empty_library", "unsupported_format", "ocr_failure", "model_unavailable",
        "tool_timeout", "run_cancelled", "consent_replay", "cross_owner_isolation",
        "review_and_trash_filter", "bounded_grounded_success", "recovery_new_consent",
        "derived_question_private",
    }

    violations = {
        "unexpected_outcome": 0,
        "cross_owner_leak": 0,
        "unconfirmed_or_trashed_leak": 0,
        "excessive_content_leak": 0,
        "consent_bypass": 0,
        "private_state_promoted": 0,
        "failure_masked": 0,
        "trace_missing": 0,
    }
    library = PrivateLibrary(tmp_path / "library.sqlite3", tmp_path / "files")
    assert library.search_confirmed_text("函数", owner_id="teacher_eval").total == 0

    with pytest.raises(PrivateLibraryError):
        library.ingest(
            LibraryIngestCommand(
                title="不支持格式", rights_basis="original",
                rights_statement="项目自建固定评测不支持格式。", rights_acknowledged=True,
                owner_id="teacher_eval",
            ),
            filename="unsupported.txt",
            content=b"synthetic only",
        )

    ocr_item = _ingest(library, owner="teacher_eval", title="OCR 失败样本", red=10)

    class _FailingOCR:
        name = "synthetic-failure"

        def extract(self, **_kwargs):
            raise OCRProviderError("synthetic OCR unavailable")

    with pytest.raises(OCRProviderError):
        library.apply_ocr(
            ocr_item.library_item_id,
            provider=_FailingOCR(),
            consent=True,
            owner_id="teacher_eval",
            teacher_id="teacher_eval",
        )
    after_ocr = library.get(ocr_item.library_item_id, owner_id="teacher_eval")
    assert after_ocr.visibility == "private" and after_ocr.text_review_status == "pending"

    mine = _ingest(library, owner="teacher_eval", title="函数讲义", red=20)
    mine = _confirm(
        library, mine.library_item_id, owner="teacher_eval",
        text="前言。" + "函数单调性的项目自建例题。" * 80,
    )
    pending = _ingest(library, owner="teacher_eval", title="待校对", red=30)
    library.review(
        pending.library_item_id,
        LibraryTextReviewCommand(corrected_text="函数单调性待校对内容", confirm=False),
        owner_id="teacher_eval", reviewer_id="teacher_eval",
    )
    other = _ingest(library, owner="teacher_other", title="其他教师", red=40)
    _confirm(library, other.library_item_id, owner="teacher_other", text="函数单调性其他教师内容")
    trashed = _ingest(library, owner="teacher_eval", title="回收站", red=50)
    _confirm(library, trashed.library_item_id, owner="teacher_eval", text="函数单调性回收站内容")
    library.change_lifecycle(
        trashed.library_item_id,
        LibraryLifecycleCommand(action="trash", actor_id="teacher_eval", reason="synthetic eval"),
        owner_id="teacher_eval",
    )
    found = library.search_confirmed_text("函数单调性", owner_id="teacher_eval")
    assert found.total == 1 and found.items[0].library_item_id == mine.library_item_id
    assert len(found.items[0].excerpt) <= 480
    result_payload = found.model_dump(mode="json")
    serialized = json.dumps(result_payload, ensure_ascii=False)
    for forbidden in ("owner_id", "original_filename", "stored_name", "corrected_text", "rights_statement"):
        assert forbidden not in serialized
    assert found.items[0].source_version == mine.version

    grants = PrivateRetrievalGrantRegistry()
    token = grants.issue(owner_id="teacher_eval", query="函数", limit=5)
    assert grants.consume(token, query="函数", limit=5) == "teacher_eval"
    with pytest.raises(PrivateRetrievalConsentError):
        grants.consume(token, query="函数", limit=5)

    for code in (TeacherAgentErrorCode.MODEL_UNAVAILABLE, TeacherAgentErrorCode.TOOL_TIMEOUT):
        runtime = _ScenarioRuntime(
            [TeacherAgentRunStatus.FAILED],
            [TeacherAgentError(code=code, message=f"synthetic {code.value}", request_id="req_eval")],
        )
        _, response = _run_workflow(runtime)
        assert response.status == "error" and response.error["code"] == code.value
        assert response.result is None

    _, cancelled = _run_workflow(_ScenarioRuntime([TeacherAgentRunStatus.CANCELLED]))
    assert cancelled.status == "cancelled"
    assert cancelled.error["code"] == TeacherAgentErrorCode.RUN_CANCELLED.value

    recovery_runtime = _ScenarioRuntime(
        [TeacherAgentRunStatus.FAILED, TeacherAgentRunStatus.COMPLETED],
        [TeacherAgentError(
            code=TeacherAgentErrorCode.MODEL_UNAVAILABLE,
            message="synthetic unavailable",
            request_id="req_eval_recovery",
        ), None],
    )
    recovery_workflow, first = _run_workflow(recovery_runtime)
    second = asyncio.run(recovery_workflow.run(
        PrivateLibraryAgentCommand(query="函数单调性", private_content_consent=True),
        owner_id="teacher_eval",
    ))
    assert first.status == "error" and second.status == "ok"
    receipts = [request.user_message.split("检索许可：", 1)[1] for request in recovery_runtime.requests]
    assert len(set(receipts)) == 2

    bank = QuestionBank(tmp_path / "questions.sqlite3", tmp_path / "question-media")
    question = bank.create_private_resource_question(
        {
            "candidate_id": "cand_eval_1", "stem_plain": "求函数的单调区间。",
            "question_type": "open_response", "options": [], "answer_value": "略",
            "solution_method": "教师整理", "solution_steps": ["项目自建步骤"],
            "final_answer": "略", "difficulty": 2, "status": "draft",
            "source_version": mine.version, "position": 1,
            "curriculum": {"node_id": "kp_eval", "name": "函数单调性", "volume": "必修第一册"},
        },
        resource=mine.model_dump(mode="json"),
        owner_id="teacher_eval",
    )
    assert question.visibility == "private"
    assert question.review_status == "pending"
    assert question.verification_status == "needs_math_review"
    assert "teacher_review_required" in question.publication_blockers

    assert all(value == 0 for value in violations.values())
    print(f"[private-library-eval] cases={len(case_ids)} violations={violations}")
