"""Internal Tool Gateway 安全与契约测试。

覆盖：M2M 认证、payload 校验、结构化错误、未知资源、超时、
search limit 硬上限、错误响应不泄漏 traceback/路径/secret。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import _GatewayHttpError, gateway_error_handler
from app.modules.curriculum import CurriculumNode, InMemoryCurriculumCatalog
from app.modules.math_verifier import MathVerifier
from app.modules.question_bank import QuestionBank
from app.modules.question_quality import QuestionQualityWorkflow
from app.modules.question_similarity import QuestionSimilarityRegistry
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

    monkeypatch.setattr(gateway, "get_settings", lambda: settings)
    monkeypatch.setattr(gateway, "get_question_bank", lambda: bank)
    monkeypatch.setattr(gateway, "get_question_similarity_registry", lambda: registry)
    monkeypatch.setattr(gateway, "get_question_quality_workflow", lambda: workflow)
    monkeypatch.setattr(gateway, "_catalog_for_path", lambda _path: catalog)

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

    missing = gateway_client.post(
        "/internal/agent-tools/v1/get-question",
        json={"question_id": "q_does_not_exist"},
        headers=_auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "TOOL_NOT_FOUND"


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

