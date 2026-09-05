from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    # Resolve the private runtime configuration from the repository root no
    # matter whether Uvicorn is launched from the root or from apps/api.
    model_config = SettingsConfigDict(
        env_prefix="MATH_AI_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    app_name: str = "高中数学 AI 备课工作台"
    environment: str = "development"
    cors_origins: str = (
        "http://localhost:3001,http://127.0.0.1:3001"
    )
    curriculum_csv: Path = Field(
        default=PROJECT_ROOT
        / "docs"
        / "high-school-math-ai"
        / "curriculum"
        / "pep-a-full-knowledge-tree-v1.csv"
    )
    curriculum_baseline_manifest: Path = Field(
        default=PROJECT_ROOT
        / "docs"
        / "high-school-math-ai"
        / "curriculum"
        / "pep-a-sealed-baseline-v1.json"
    )
    question_bank_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "question-bank.sqlite3"
    )
    question_media_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "question-media"
    )
    question_similarity_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "question-similarity.sqlite3"
    )
    private_library_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "private-library.sqlite3"
    )
    private_library_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "private-library-files"
    )
    question_capture_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "question-capture.sqlite3"
    )
    question_capture_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "question-capture-files"
    )
    personal_question_library_db: Path = Field(
        default=PROJECT_ROOT
        / "data"
        / "private-runtime"
        / "personal-question-library.sqlite3"
    )
    pdf_import_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "pdf-imports.sqlite3"
    )
    pdf_import_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "pdf-import-files"
    )
    pdf_question_estimates_csv: Path = Field(
        default=PROJECT_ROOT
        / "docs"
        / "high-school-math-ai"
        / "audits"
        / "batch-2026-08-001-question-estimates.csv"
    )
    lesson_plan_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "lesson-plans.sqlite3"
    )
    exam_paper_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "exam-papers.sqlite3"
    )
    exam_paper_asset_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "exam-paper-assets"
    )
    model_operations_db: Path = Field(
        default=PROJECT_ROOT / "data" / "runtime" / "model-operations-v1.sqlite3"
    )
    teacher_memory_db: Path = Field(
        default=PROJECT_ROOT / "data" / "private-runtime" / "teacher-memory.sqlite3"
    )
    beta_session_db: Path = Field(
        default=PROJECT_ROOT / "data" / "private-runtime" / "beta-sessions.sqlite3"
    )
    beta_validation_db: Path = Field(
        default=PROJECT_ROOT / "data" / "private-runtime" / "beta-validation.sqlite3"
    )
    beta_backup_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "private-runtime" / "backups"
    )
    owner_deletion_ledger_db: Path = Field(
        default=PROJECT_ROOT / "data" / "private-runtime" / "owner-deletions.sqlite3"
    )
    lesson_export_dir: Path = Field(default=PROJECT_ROOT / "output")
    cjk_font_regular: Path | None = None
    cjk_font_bold: Path | None = None
    lesson_plan_provider: str = "auto"
    question_variant_provider: str = "auto"
    question_authoring_provider: str = "auto"
    solution_provider: str = "auto"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    openai_reasoning_effort: str = "low"
    openai_timeout_seconds: int = 90
    openai_input_usd_per_million: float | None = None
    openai_cached_input_usd_per_million: float | None = None
    openai_output_usd_per_million: float | None = None
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_vision_model: str = "deepseek-v4-flash-vision-exp"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_timeout_seconds: int = 90
    pilot_batch_json: Path = Field(
        default=PROJECT_ROOT / "data" / "pilot" / "batch-2026-08-001-30q.json"
    )
    set_curation_json: Path = Field(
        default=PROJECT_ROOT / "data" / "curated" / "set-10q-corrections-v1.json"
    )
    probability_curation_json: Path = Field(
        default=PROJECT_ROOT / "data" / "curated" / "probability-4q-corrections-v1.json"
    )
    probability_curation_2_json: Path = Field(
        default=PROJECT_ROOT / "data" / "curated" / "probability-6q-corrections-v1.json"
    )
    function_pilot_batch_json: Path = Field(
        default=PROJECT_ROOT / "data" / "pilot" / "function-properties-5q-v1.json"
    )
    function_curation_json: Path = Field(
        default=PROJECT_ROOT / "data" / "curated" / "function-properties-5q-corrections-v1.json"
    )

    # -- Teacher Agent Runtime --------------------------------------------
    # legacy（默认）保持现有产品行为；dsh 通过独立 Agent Service 接入 Harness。
    agent_runtime: str = "legacy"
    # 默认禁止静默降级；启用后必须记录 fallback 审计日志。
    agent_allow_legacy_fallback: bool = False
    agent_service_url: str = "http://127.0.0.1:4100"
    agent_service_token: str = ""
    agent_request_timeout_seconds: int = 900
    # Agent -> FastAPI internal tool gateway 的机器身份。
    tool_gateway_token: str = ""
    tool_gateway_timeout_seconds: float = 30.0
    solve_tool_timeout_seconds: float = 120.0
    question_authoring_tool_timeout_seconds: float = 900.0

    # -- Agent workflow feature gates ---------------------------------------
    # 默认关闭：现有传统页面行为不变。仅在相应 Runtime/Tool/UI Gate 就绪后开启。
    search_agent_enabled: bool = False
    solve_agent_enabled: bool = False
    question_authoring_agent_enabled: bool = False
    search_agent_max_query_length: int = 2000

    # -- Closed Beta access -------------------------------------------------
    # Disabled keeps the fixed local-development teacher. Enabled mode fails
    # closed unless a valid opaque HttpOnly session is present.
    beta_access_enabled: bool = False
    beta_access_roster_json: str = "{}"
    beta_session_ttl_hours: int = Field(default=12, ge=1, le=168)
    beta_session_cookie_name: str = "math_ai_beta_session"
    beta_session_secure_cookie: bool = False

    # M13 validation is separately gated and remains off even when Beta access is on.
    # A participant must acknowledge the current notice before the module records facts.
    beta_validation_enabled: bool = False
    beta_validation_identity_secret: SecretStr = SecretStr("")
    beta_validation_retention_days: int = Field(default=90, ge=90, le=90)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
