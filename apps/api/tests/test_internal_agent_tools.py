"""Internal Tool Gateway 安全与契约测试。

覆盖：M2M 认证、payload 校验、结构化错误、未知资源、超时、
search limit 硬上限、错误响应不泄漏 traceback/路径/secret。
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.main import _GatewayHttpError, gateway_error_handler
from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier
from app.modules.private_library import (
    LibraryStats,
    PrivateLibrarySearchItem,
    PrivateLibrarySearchResult,
    PrivateRetrievalGrantRegistry,
)
from app.modules.question_bank import QuestionBank
from app.modules.question_capture import (
    QuestionCapture,
    QuestionCaptureCommand,
    QuestionOption,
    QuestionRecognitionCommand,
    QuestionRecognitionResult,
    QuestionRecognitionReviewCommand,
    QuestionSolveGrantRegistry,
    QuestionSolveReference,
)
from app.modules.question_quality import QuestionQualityWorkflow
from app.modules.question_similarity import QuestionSimilarityRegistry
from app.modules.solution_assistant import (
    GeneratedSolution,
    SolutionAssistant,
    SolutionExplanation,
    SolutionRequest,
    SolutionProviderResponseError,
    SolutionVisualInput,
)
from app.routes import internal_agent_tools as gateway
from app.routes.internal_agent_tools import router as gateway_router

_FIXTURES = Path(__file__).resolve().parents[3] / "data" / "test-fixtures" / "question-bank"
_TOKEN = "gw-test-token-000"


@pytest.fixture()
def gateway_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    settings = Settings(
        tool_gateway_token=_TOKEN,
        tool_gateway_timeout_seconds=30.0,
        agent_runtime="legacy",
    )

    bank = QuestionBank(tmp_path / "bank.sqlite3")
    bank.import_batch(_FIXTURES / "pilot" / "batch-synthetic-set-probability-30q-v1.json")
    bank.apply_curation_package(
        _FIXTURES / "curated" / "set-10q-synthetic-corrections-v1.json", MathVerifier()
    )
    bank.apply_curation_package(
        _FIXTURES / "curated" / "probability-4q-synthetic-corrections-v1.json",
        MathVerifier(),
    )
    bank.apply_curation_package(
        _FIXTURES / "curated" / "probability-6q-synthetic-corrections-v1.json",
        MathVerifier(),
    )
    bank.import_batch(
        _FIXTURES / "pilot" / "similarity-pair-synthetic-2q-v1.json"
    )

    registry = QuestionSimilarityRegistry(tmp_path / "similarity.sqlite3", question_bank=bank)
    registry.scan()

    nodes = [
        CurriculumNode(
            node_id="sec_test_01",
            parent_id=None,
            volume="必修第一册",
            node_type="section",
            code="S-01",
            name="测试小节",
            description="测试用小节节点",
            prerequisite_node_ids=[],
            primary_competencies=[],
            typical_question_types=[],
            common_errors=[],
            gaokao_priority="medium",
            status="active",
            reviewed_by="teacher",
        ),
        CurriculumNode(
            node_id="kp_test_00",
            parent_id="sec_test_01",
            volume="必修第一册",
            node_type="knowledge_point",
            code="T-00",
            name="前置知识点",
            description="测试用前置知识点",
            prerequisite_node_ids=[],
            primary_competencies=[],
            typical_question_types=[],
            common_errors=[],
            gaokao_priority="medium",
            status="active",
            reviewed_by="teacher",
        ),
        CurriculumNode(
            node_id="kp_test_01",
            parent_id="sec_test_01",
            volume="必修第一册",
            node_type="knowledge_point",
            code="T-01",
            name="集合的基本运算",
            description="交集、并集、补集",
            prerequisite_node_ids=["kp_test_00"],
            primary_competencies=[],
            typical_question_types=[],
            common_errors=[],
            gaokao_priority="high",
            status="active",
            reviewed_by="teacher",
        )
    ]
    catalog = InMemoryCurriculumCatalog(nodes)
    workflow = QuestionQualityWorkflow(question_bank=bank, curriculum_catalog=catalog)
    solution_assistant = SolutionAssistant(question_bank=bank)

    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway, "get_question_bank", lambda: bank)
    monkeypatch.setattr(gateway, "get_question_similarity_registry", lambda: registry)
    monkeypatch.setattr(gateway, "get_question_quality_workflow", lambda: workflow)
    monkeypatch.setattr(gateway, "get_solution_assistant", lambda: solution_assistant)
    monkeypatch.setattr(gateway, "_catalog_for_path", lambda _path: catalog)

    class FakePrivateLibrary:
        def stats(self, *, owner_id: str) -> LibraryStats:
            assert owner_id == "owner_teacher"
            return LibraryStats(
                total=3,
                pending_review=2,
                confirmed=1,
                needs_ocr=1,
                trashed=1,
                by_file_kind={"pdf": 2, "docx": 1},
            )

        def search_confirmed_text(self, query: str, *, limit: int, owner_id: str) -> PrivateLibrarySearchResult:
            assert owner_id == "owner_teacher"
            return PrivateLibrarySearchResult(
                query=query,
                items=[PrivateLibrarySearchItem(
                    library_item_id="lib_1",
                    title="函数讲义",
                    excerpt="函数单调性的课堂例题。",
                    source_version=3,
                    rights_basis="original",
                )][:limit],
                total=1,
                truncated=False,
            )

    monkeypatch.setattr(gateway, "get_private_library", lambda: FakePrivateLibrary())
    grants = PrivateRetrievalGrantRegistry()
    monkeypatch.setattr(gateway, "get_private_retrieval_grants", lambda: grants)
    setattr(grants, "test_token", grants.issue(owner_id="owner_teacher", query="函数", limit=5))

    app = FastAPI()
    app.add_exception_handler(_GatewayHttpError, gateway_error_handler)
    app.include_router(gateway_router)
    return TestClient(app)


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}", "X-Request-Id": "req_test_001"}


def test_missing_token_rejected(gateway_client: TestClient) -> None:
    response = gateway_client.post("/internal/agent-tools/v1/search-questions", json={"query": ""})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOOL_UNAUTHORIZED"


def test_wrong_token_rejected(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": ""},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOOL_UNAUTHORIZED"


def test_private_search_requires_matching_one_use_consent(gateway_client: TestClient) -> None:
    grants = gateway.get_private_retrieval_grants()
    token = getattr(grants, "test_token")
    body = {"query": "函数", "consent_token": token, "limit": 5}
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-private-library", json=body, headers=_auth()
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["excerpt"] == "函数单调性的课堂例题。"
    assert payload["content_scope"] == "matching_excerpts"
    assert "owner_id" not in payload["items"][0]
    replay = gateway_client.post(
        "/internal/agent-tools/v1/search-private-library", json=body, headers=_auth()
    )
    assert replay.status_code == 403
    assert replay.json()["error"]["code"] == "PRIVATE_CONSENT_REQUIRED"


def test_private_search_rejects_model_owner_selector(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-private-library",
        json={"query": "函数", "consent_token": "x" * 32, "limit": 5, "owner_id": "other"},
        headers=_auth(),
    )
    assert response.status_code == 422


def test_gateway_disabled_when_token_unconfigured(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.add_exception_handler(_GatewayHttpError, gateway_error_handler)
    app.include_router(gateway_router)
    monkeypatch.setattr(gateway, "get_settings", lambda: Settings(tool_gateway_token=""))
    client = TestClient(app)
    response = client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": ""},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOOL_UNAUTHORIZED"


def test_search_questions_contract(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 5},
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req_test_001"
    assert payload["total"] >= 1
    assert len(payload["items"]) <= 5
    assert payload["truncated"] == (payload["total"] > len(payload["items"]))
    for item in payload["items"]:
        assert set(item) >= {
            "question_id",
            "stem",
            "question_type",
            "knowledge_points",
            "difficulty",
            "verification_status",
            "source_status",
            "visibility",
        }
        assert item["verification_status"] == "passed"


def test_search_questions_hard_limit(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 100},
        headers=_auth(),
    )
    assert response.status_code == 422


def test_get_question_known_and_unknown(gateway_client: TestClient) -> None:
    search = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 1},
        headers=_auth(),
    ).json()
    question_id = search["items"][0]["question_id"]

    response = gateway_client.post(
        "/internal/agent-tools/v1/get-question",
        json={"question_id": question_id},
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == question_id
    assert "stem" in payload and "answer" in payload
    assert payload["solution_steps"]
    assert all(isinstance(step, str) and not step.lstrip().startswith("{") for step in payload["solution_steps"])

    missing = gateway_client.post(
        "/internal/agent-tools/v1/get-question",
        json={"question_id": "q_does_not_exist"},
        headers=_auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TOOL_NOT_FOUND"


def test_solve_question_prefers_verified_bank_solution(gateway_client: TestClient) -> None:
    search = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 1},
        headers=_auth(),
    ).json()
    source = search["items"][0]

    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": source["stem"], "solution_mode": "standard"},
        headers=_auth(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req_test_001"
    assert payload["matched_question_id"] == source["question_id"]
    assert payload["matched_question_revision_count"] >= 0
    assert payload["mode"] == "verified_bank"
    assert payload["confidence_status"] == "program_verified"
    assert payload["math_verification"]["status"] == "passed"
    assert payload["math_verification"]["scope"] == "question_answer"
    assert payload["verification_evidence"]
    assert payload["explanation"]["steps"]


def test_solve_question_generated_result_is_never_marked_verified(
    gateway_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeSolutionProvider:
        name = "fake_model"
        model = "fake-solver-v1"

        def solve(self, request: SolutionRequest) -> GeneratedSolution:
            return GeneratedSolution(
                explanation=SolutionExplanation(
                    method="代数法",
                    steps=["移项并合并同类项。", "解得 x=2。"],
                    final_answer="x=2",
                ),
                knowledge_points=["一元一次方程"],
                common_mistakes=["移项时忘记变号"],
                teaching_notes=["请教师复核后使用"],
            )

    assistant = SolutionAssistant(
        question_bank=QuestionBank(tmp_path / "empty-solve-bank.sqlite3"),
        provider=FakeSolutionProvider(),
    )
    monkeypatch.setattr(gateway, "get_solution_assistant", lambda: assistant)

    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": "解方程 2x-4=0。"},
        headers=_auth(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "live_ai"
    assert payload["confidence_status"] == "teacher_review_required"
    assert payload["math_verification"]["status"] == "inconclusive"
    assert payload["math_verification"]["capability"] == "unsupported"
    assert "不支持" in " ".join(payload["verification_evidence"])


def test_solve_question_visual_bundle_is_owner_scoped_revision_pinned_and_consented(
    gateway_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class VisualRecognitionProvider:
        name = "synthetic_vision_ocr"
        model = "synthetic-ocr-v1"

        def recognize(self, **_kwargs) -> QuestionRecognitionResult:
            return QuestionRecognitionResult(
                stem_plain="如图，在三角形 ABC 中求角 A。",
                stem_latex="",
                options=[QuestionOption(key="A", text="30°")],
                requires_visual_reasoning=True,
            )

    image = Image.new("RGB", (1000, 700), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon(((150, 600), (500, 100), (850, 600)), outline="black", width=5)
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    capture = QuestionCapture(
        tmp_path / "visual-capture.sqlite3",
        tmp_path / "visual-media",
        recognition_providers={"local": VisualRecognitionProvider()},
    )
    created = capture.prepare(
        QuestionCaptureCommand(
            owner_id="owner_teacher",
            source="upload",
            private_storage_acknowledged=True,
        ),
        filename="triangle.png",
        content=encoded.getvalue(),
    )
    capture.recognize(
        created.asset.asset_id,
        QuestionRecognitionCommand(mode="local"),
        owner_id="owner_teacher",
    )
    confirmed = capture.review_recognition(
        created.asset.asset_id,
        QuestionRecognitionReviewCommand(
            stem_plain="如图，在三角形 ABC 中求角 A。",
            options=[QuestionOption(key="A", text="30°")],
            confirm=True,
        ),
        owner_id="owner_teacher",
    )

    class VisualSolutionProvider:
        name = "fake_model"
        model = "fake-text-v1"
        vision_model = "fake-vision-v1"

        def __init__(self) -> None:
            self.visual_input: SolutionVisualInput | None = None

        def solve(
            self,
            _request: SolutionRequest,
            visual_input: SolutionVisualInput | None = None,
        ) -> GeneratedSolution:
            self.visual_input = visual_input
            return GeneratedSolution(
                explanation=SolutionExplanation(
                    method="图形分析",
                    steps=["结合原图条件分析。"],
                    final_answer="待教师核对",
                )
            )

    provider = VisualSolutionProvider()
    monkeypatch.setattr(gateway, "get_question_capture", lambda: capture)
    monkeypatch.setattr(
        gateway,
        "get_solution_assistant",
        lambda: SolutionAssistant(
            question_bank=QuestionBank(tmp_path / "visual-empty-bank.sqlite3"),
            provider=provider,
        ),
    )
    body = {
        "question_text": "如图，在三角形 ABC 中求角 A。\nA. 30°",
    }
    reference = QuestionSolveReference(
        asset_id=created.asset.asset_id,
        media_revision=1,
        recognition_revision=confirmed.recognition_revision,
        visual_processing_consent=True,
    )
    grants = QuestionSolveGrantRegistry()
    monkeypatch.setattr(gateway, "get_question_solve_grants", lambda: grants)
    no_consent_reference = reference.model_copy(
        update={"visual_processing_consent": False}
    )
    no_consent_grant = grants.issue(
        owner_id="owner_teacher",
        question_text=body["question_text"],
        solution_mode="standard",
        teacher_instruction="",
        reference=no_consent_reference,
    )
    no_consent = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={**body, "capture_grant": no_consent_grant},
        headers=_auth(),
    )
    assert no_consent.status_code == 422
    assert "逐次确认" in no_consent.json()["error"]["message"]

    grant = grants.issue(
        owner_id="owner_teacher",
        question_text=body["question_text"],
        solution_mode="standard",
        teacher_instruction="按课堂板书格式",
        reference=reference,
    )
    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={
            **body,
            "question_text": "模型改写了题面，但该值不是授权来源",
            "solution_mode": "alternative",
            "teacher_instruction": "模型改写了要求",
            "capture_grant": grant,
        },
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["visual_context"]["image_used"] is True
    assert payload["visual_context"]["media_revision"] == 1
    assert payload["model"] == "fake-vision-v1"
    assert payload["question_text"] == body["question_text"]
    assert payload["solution_mode"] == "standard"
    assert provider.visual_input is not None
    assert provider.visual_input.image_bytes == encoded.getvalue()

    replayed = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={
            **body,
            "capture_grant": grant,
        },
        headers={**_auth(), "X-Request-Id": "req_replay"},
    )
    assert replayed.status_code == 403
    assert "已使用" in replayed.json()["error"]["message"]


def test_solve_question_rejects_known_failed_bank_record(
    gateway_client: TestClient,
) -> None:
    bank = gateway.get_question_bank()
    source = bank.search(
        verification_status="source_inconsistency_detected", page_size=1
    ).items[0]

    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": source.stem_plain},
        headers=_auth(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERIFICATION_FAILED"


def test_solve_question_rejects_inconclusive_bank_record_without_model(
    gateway_client: TestClient,
) -> None:
    bank = gateway.get_question_bank()
    source = bank.search(verification_status="needs_math_review", page_size=1).items[0]

    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": source.stem_plain},
        headers=_auth(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "VERIFICATION_INCONCLUSIVE"


def test_solve_question_without_verified_match_or_model_is_explicit(
    gateway_client: TestClient,
) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": "求一个题库中不存在的复合虚构数学问题 987654321。"},
        headers=_auth(),
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_solve_question_reports_invalid_model_json_as_execution_error(
    gateway_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidResponseAssistant:
        def solve(self, *_args, **_kwargs):
            raise SolutionProviderResponseError("DeepSeek 返回的 JSON 无法解析")

    monkeypatch.setattr(
        gateway,
        "get_solution_assistant",
        lambda: InvalidResponseAssistant(),
    )
    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": "如图，在三棱柱中证明两条直线垂直。"},
        headers=_auth(),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "TOOL_EXECUTION_ERROR"
    assert "已返回内容" in response.json()["error"]["message"]


def test_find_similar_questions_contract(gateway_client: TestClient) -> None:
    from app.modules.question_similarity import QuestionSimilarityRegistry

    settings = Settings(tool_gateway_token=_TOKEN)
    # 直接复用 fixture 内的 registry 数据来源：通过 gateway 的 module 引用读取当前 workspace
    workspace = gateway.get_question_similarity_registry().workspace(limit=1000)
    assert workspace.items, "synthetic fixtures 应产生相似题候选"
    seed_id = workspace.items[0].members[0].question_id

    response = gateway_client.post(
        "/internal/agent-tools/v1/find-similar-questions",
        json={"question_id": seed_id, "limit": 5},
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["request_id"] == "req_test_001"
    assert isinstance(payload["items"], list)
    assert isinstance(payload["truncated"], bool)
    for item in payload["items"]:
        assert item["question_id"] != seed_id

    missing = gateway_client.post(
        "/internal/agent-tools/v1/find-similar-questions",
        json={"question_id": "q_does_not_exist", "limit": 5},
        headers=_auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TOOL_NOT_FOUND"


def test_verify_question_contract(gateway_client: TestClient) -> None:
    search = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 1},
        headers=_auth(),
    ).json()
    question_id = search["items"][0]["question_id"]

    response = gateway_client.post(
        "/internal/agent-tools/v1/verify-question",
        json={"question_id": question_id},
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["question_id"] == question_id
    assert payload["stored_status"] == "passed"
    assert set(payload) >= {
        "stored_status",
        "capability",
        "computed_answer",
        "method",
        "details",
    }

    missing = gateway_client.post(
        "/internal/agent-tools/v1/verify-question",
        json={"question_id": "q_does_not_exist"},
        headers=_auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TOOL_NOT_FOUND"


def test_get_curriculum_node_contract(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/get-curriculum-node",
        json={"node_id": "kp_test_01"},
        headers=_auth(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["node_id"] == "kp_test_01"
    assert payload["name"] == "集合的基本运算"
    assert payload["node_type"] == "knowledge_point"

    missing = gateway_client.post(
        "/internal/agent-tools/v1/get-curriculum-node",
        json={"node_id": "kp_does_not_exist"},
        headers=_auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TOOL_NOT_FOUND"


def test_inspect_private_library_returns_owner_scoped_aggregate_only(
    gateway_client: TestClient,
) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/inspect-private-library",
        json={},
        headers=_auth(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "total": 3,
        "pending_review": 2,
        "confirmed": 1,
        "needs_ocr": 1,
        "trashed": 1,
        "by_file_kind": {"pdf": 2, "docx": 1},
        "visibility": "private",
        "content_included": False,
        "request_id": "req_test_001",
    }
    assert not any(
        key in payload
        for key in ("owner_id", "title", "filename", "extracted_text", "corrected_text")
    )

    injected_owner = gateway_client.post(
        "/internal/agent-tools/v1/inspect-private-library",
        json={"owner_id": "other_teacher"},
        headers=_auth(),
    )
    assert injected_owner.status_code == 422


def test_tool_timeout_is_structured(gateway_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gateway,
        "get_settings",
        lambda: Settings(tool_gateway_token=_TOKEN, tool_gateway_timeout_seconds=1e-9),
    )
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 5},
        headers=_auth(),
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "TOOL_TIMEOUT"


def test_solve_tool_has_its_own_bounded_timeout(
    gateway_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowAssistant:
        def solve(self, _command: SolutionRequest) -> None:
            time.sleep(0.05)

    monkeypatch.setattr(
        gateway,
        "get_settings",
        lambda: Settings(
            tool_gateway_token=_TOKEN,
            tool_gateway_timeout_seconds=30,
            solve_tool_timeout_seconds=1e-9,
        ),
    )
    monkeypatch.setattr(gateway, "get_solution_assistant", lambda: SlowAssistant())
    response = gateway_client.post(
        "/internal/agent-tools/v1/solve-question",
        json={"question_text": "解方程 2x-4=0。"},
        headers=_auth(),
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "TOOL_TIMEOUT"


def test_unexpected_failure_never_leaks_internals(
    gateway_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenBank:
        def search(self, **_: object) -> None:
            raise RuntimeError("boom: D:\\secret-dir\\private.sqlite3")

    monkeypatch.setattr(gateway, "get_question_bank", lambda: BrokenBank())
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": 5},
        headers=_auth(),
    )
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "TOOL_EXECUTION_ERROR"
    text = str(body)
    assert "Traceback" not in text
    assert "secret-dir" not in text
    assert _TOKEN not in text


def test_invalid_payload_is_validation_error(gateway_client: TestClient) -> None:
    response = gateway_client.post(
        "/internal/agent-tools/v1/search-questions",
        json={"query": "", "limit": -1},
        headers=_auth(),
    )
    assert response.status_code == 422
    response = gateway_client.post(
        "/internal/agent-tools/v1/get-question",
        json={"question_id": ""},
        headers=_auth(),
    )
    assert response.status_code == 422
