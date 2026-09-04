from __future__ import annotations

import json
import re
from functools import lru_cache
from threading import Lock
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.core.config import get_settings
from app.core.deletion import (
    execute_owner_permanent_delete,
    OwnerPermanentDeleteCommand,
    OwnerPermanentDeleteResult,
    get_owner_deletion_ledger,
)
from app.core.identity import CurrentTeacher, get_current_teacher
from app.core.ephemeral_exports import remove_ephemeral_export
from app.modules.private_library import (
    CandidateImportResult,
    LibraryIngestCommand,
    LibraryLifecycleCommand,
    LibraryOCRCommand,
    LibraryOCRResult,
    LibraryAIRepairCommand,
    LibraryAIRepairResult,
    LibraryQuestionExtractionCommand,
    LibraryItemList,
    LibraryItemView,
    LibraryStats,
    LibraryTextReviewCommand,
    LibraryTextRevisionList,
    DeepSeekResourceOCRProvider,
    OCRProviderError,
    OpenAIResourceOCRProvider,
    LocalMathOCRProvider,
    PrivateLibrary,
    PrivateLibraryError,
    QuestionCandidateList,
    QuestionCandidateCurriculum,
    QuestionCandidateCurriculumCommand,
    QuestionCandidateUpdate,
    QuestionCandidateView,
    RightsBasis,
)
from app.modules.question_bank import QuestionBank, QuestionBankError
from app.modules.curriculum import CsvCurriculumCatalog
from app.modules.pdf_imports import ImportBatchCommand, ImportBatchResult, PdfImportError
from app.routes.imports import get_pdf_import_studio
from app.routes.model_operations import get_model_operations_registry
from app.routes.curriculum import get_catalog
from app.modules.private_library.exports import LibraryExportError, LibraryTextRenderer
from app.modules.deepseek import DeepSeekClientError, DeepSeekJsonClient
from app.modules.background_jobs import BackgroundJobRegistry, BackgroundJobView


router = APIRouter(prefix="/library", tags=["private-library"])
_local_math_ocr_lock = Lock()
_background_jobs = BackgroundJobRegistry()


@lru_cache
def get_private_library() -> PrivateLibrary:
    settings = get_settings()
    return PrivateLibrary(settings.private_library_db, settings.private_library_dir)


@lru_cache
def get_library_question_bank() -> QuestionBank:
    settings = get_settings()
    return QuestionBank(settings.question_bank_db, settings.question_media_dir)


def get_library_ocr_provider() -> DeepSeekResourceOCRProvider | OpenAIResourceOCRProvider:
    settings = get_settings()
    if settings.deepseek_api_key:
        return DeepSeekResourceOCRProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_vision_model,
            base_url=settings.deepseek_base_url,
            timeout_seconds=settings.deepseek_timeout_seconds,
            recorder=get_model_operations_registry(),
        )
    if not settings.openai_api_key:
        raise RuntimeError(
            "尚未配置题目识别服务；请配置 MATH_AI_DEEPSEEK_API_KEY"
        )
    return OpenAIResourceOCRProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        timeout_seconds=settings.openai_timeout_seconds,
        recorder=get_model_operations_registry(),
    )


def get_local_math_ocr_provider(progress=None) -> LocalMathOCRProvider:
    return LocalMathOCRProvider(progress=progress)


@lru_cache
def get_library_text_renderer() -> LibraryTextRenderer:
    return LibraryTextRenderer(get_settings().lesson_export_dir)


def get_library_ai_repair_client() -> DeepSeekJsonClient:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("尚未配置大模型识别服务")
    return DeepSeekJsonClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )


def get_library_question_extraction_client() -> DeepSeekJsonClient:
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("尚未配置大模型题目提取服务")
    return DeepSeekJsonClient(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        timeout_seconds=settings.deepseek_timeout_seconds,
    )


def _split_latex_repair_draft(text: str, *, max_chars: int = 7000) -> list[str]:
    """Split long papers on page boundaries so DeepSeek can return complete JSON."""
    page_parts = re.split(r"(?=【第\s*\d+\s*页】)", text)
    parts = [part for part in page_parts if part]
    if not parts:
        parts = [text]
    chunks: list[str] = []
    current = ""
    for part in parts:
        if current and len(current) + len(part) > max_chars:
            chunks.append(current)
            current = ""
        while len(part) > max_chars:
            split_at = part.rfind("\n", 0, max_chars)
            if split_at < max_chars // 2:
                split_at = max_chars
            if current:
                chunks.append(current)
                current = ""
            chunks.append(part[:split_at])
            part = part[split_at:]
        current += part
    if current:
        chunks.append(current)
    return chunks


def _question_extraction_schema() -> dict:
    nullable_string = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "questions": {
                "type": "array",
                "maxItems": 100,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question_type": {
                            "type": "string",
                            "enum": [
                                "single_choice",
                                "multiple_choice",
                                "fill_blank",
                                "open_response",
                            ],
                        },
                        "stem_plain": {"type": "string"},
                        "stem_latex": nullable_string,
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "key": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["key", "text"],
                            },
                        },
                        "answer_value": nullable_string,
                        "solution_method": {"type": "string"},
                        "solution_steps": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "final_answer": nullable_string,
                        "difficulty": {"type": "integer", "minimum": 1, "maximum": 5},
                        "warnings": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "question_type",
                        "stem_plain",
                        "stem_latex",
                        "options",
                        "answer_value",
                        "solution_method",
                        "solution_steps",
                        "final_answer",
                        "difficulty",
                        "warnings",
                    ],
                },
            }
        },
        "required": ["questions"],
    }


def _extract_questions_with_deepseek(
    text: str, *, client: DeepSeekJsonClient
) -> list[tuple[QuestionCandidateUpdate, list[str]]]:
    extracted: list[tuple[QuestionCandidateUpdate, list[str]]] = []
    seen: set[str] = set()
    chunks = _split_latex_repair_draft(text, max_chars=7000)
    for index, chunk in enumerate(chunks, start=1):
        raw = client.request(
            instructions=(
                "你是高中数学 PDF 逐题提取助手。只依据教师已确认的 PDF 转录文本，按原顺序逐题提取"
                "题干、选项、答案和解析；删除页眉、页脚、目录、题型说明与无关正文。"
                "不得补造原文没有的条件、答案或解析。stem_plain 必须是正常可读的中文题面，"
                "不能包含 JSON、OCR 占位符或私用区乱码；stem_latex 保留完整中文并把数学表达式写在"
                " $...$ 或 $$...$$ 中。原文没有答案或解析时使用 null 或空数组，并在 warnings 说明。"
            ),
            input_text=json.dumps(
                {
                    "chunk_position": f"{index}/{len(chunks)}",
                    "confirmed_pdf_text": chunk,
                },
                ensure_ascii=False,
            ),
            action="私人 PDF 逐题提取",
            output_schema=_question_extraction_schema(),
            max_tokens=8192,
        )
        content = json.loads(raw["output"][0]["content"][0]["text"])
        questions = content.get("questions")
        if not isinstance(questions, list):
            raise ValueError("questions 不是数组")
        for raw_question in questions:
            if not isinstance(raw_question, dict):
                raise ValueError("题目条目不是对象")
            value = dict(raw_question)
            warning_values = value.pop("warnings", [])
            if not isinstance(warning_values, list):
                raise ValueError("warnings 不是数组")
            warnings = [
                str(item).strip() for item in warning_values if str(item).strip()
            ]
            draft = QuestionCandidateUpdate.model_validate(value)
            stem = draft.stem_plain.strip()
            if re.search(r"[\ue000-\uf8ff�□■]", stem):
                raise ValueError("题面仍包含 PDF 私有字体或缺失映射字符")
            key = re.sub(r"\s+", "", stem)
            if key in seen:
                continue
            seen.add(key)
            extracted.append(
                (
                    draft,
                    list(
                        dict.fromkeys(
                            [
                                *warnings,
                                "大模型仅完成逐题结构化；题面、答案和解析仍需教师逐项核对。",
                            ]
                        )
                    ),
                )
            )
    return extracted


@router.get("", response_model=LibraryItemList)
def list_library_items(
    limit: int = Query(default=50, ge=1, le=100),
    lifecycle_state: str = Query(default="active"),
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryItemList:
    try:
        return get_private_library().list(
            limit=limit,
            lifecycle_state=lifecycle_state,
            owner_id=current_teacher.teacher_id,
        )
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/stats", response_model=LibraryStats)
def library_stats(
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryStats:
    return get_private_library().stats(owner_id=current_teacher.teacher_id)


@router.post("", response_model=LibraryItemView, status_code=201)
async def upload_library_item(
    file: UploadFile = File(...),
    title: str = Form("", max_length=300),
    rights_basis: RightsBasis = Form("private_teaching_only"),
    rights_statement: str = Form(""),
    rights_acknowledged: bool = Form(True),
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryItemView:
    try:
        content = await file.read(PrivateLibrary.MAX_FILE_BYTES + 1)
        return get_private_library().ingest(
            LibraryIngestCommand(
                title=title,
                rights_basis=rights_basis,
                rights_statement=rights_statement,
                rights_acknowledged=rights_acknowledged,
                owner_id=current_teacher.teacher_id,
            ),
            filename=file.filename or "未命名资料",
            content=content,
        )
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{item_id}", response_model=LibraryItemView)
def get_library_item(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryItemView:
    try:
        return get_private_library().get(
            item_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc


@router.patch("/{item_id}/review", response_model=LibraryItemView)
def review_library_text(
    item_id: str,
    command: LibraryTextReviewCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryItemView:
    try:
        return get_private_library().review(
            item_id,
            command,
            owner_id=current_teacher.teacher_id,
            reviewer_id=current_teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{item_id}/revisions", response_model=LibraryTextRevisionList)
def list_library_text_revisions(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryTextRevisionList:
    try:
        return get_private_library().list_text_revisions(
            item_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc


@router.post("/{item_id}/lifecycle", response_model=LibraryItemView)
def change_library_item_lifecycle(
    item_id: str,
    command: LibraryLifecycleCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryItemView:
    try:
        secured_command = command.model_copy(
            update={"actor_id": current_teacher.teacher_id}
        )
        return get_private_library().change_lifecycle(
            item_id,
            secured_command,
            owner_id=current_teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc


@router.delete("/{item_id}", response_model=OwnerPermanentDeleteResult)
def permanently_delete_library_item(
    item_id: str,
    command: OwnerPermanentDeleteCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    deletion_ledger=Depends(get_owner_deletion_ledger),
) -> OwnerPermanentDeleteResult:
    try:
        execute_owner_permanent_delete(
            ledger=deletion_ledger,
            object_kind="library_item",
            object_id=item_id,
            owner_id=current_teacher.teacher_id,
            operation=lambda: get_private_library().permanently_delete(
                item_id,
                owner_id=current_teacher.teacher_id,
                expected_updated_at=command.expected_updated_at,
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OwnerPermanentDeleteResult(object_id=item_id, object_kind="library_item")


@router.post("/{item_id}/ocr", response_model=LibraryOCRResult)
def run_library_ocr(
    item_id: str,
    command: LibraryOCRCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryOCRResult:
    try:
        library = get_private_library()
        library.get(item_id, owner_id=current_teacher.teacher_id)
        provider = get_library_ocr_provider()
        item, provider_name, warnings = library.apply_ocr(
            item_id,
            provider=provider,
            consent=command.external_processing_consent,
            owner_id=current_teacher.teacher_id,
            teacher_id=current_teacher.teacher_id,
        )
        return LibraryOCRResult(item=item, provider=provider_name, warnings=warnings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except OCRProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{item_id}/local-math-ocr", response_model=LibraryOCRResult)
def run_local_math_ocr(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryOCRResult:
    try:
        library = get_private_library()
        library.get(item_id, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    if not _local_math_ocr_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="本地数学 OCR 正在处理另一份资料，请等待当前任务完成后再试")
    try:
        item, provider_name, warnings = library.apply_local_ocr(
            item_id,
            provider=get_local_math_ocr_provider(),
            owner_id=current_teacher.teacher_id,
            teacher_id=current_teacher.teacher_id,
        )
        return LibraryOCRResult(item=item, provider=provider_name, warnings=warnings)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except OCRProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        _local_math_ocr_lock.release()


@router.post("/{item_id}/local-math-ocr/jobs", response_model=BackgroundJobView, status_code=202)
def start_local_math_ocr_job(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    try:
        get_private_library().get(item_id, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    if not _local_math_ocr_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="本地数学 OCR 正在处理另一份资料，请等待当前任务完成")

    def runner(progress):
        try:
            item, provider_name, warnings = get_private_library().apply_local_ocr(
                item_id,
                provider=get_local_math_ocr_provider(progress),
                owner_id=current_teacher.teacher_id,
                teacher_id=current_teacher.teacher_id,
            )
            return LibraryOCRResult(item=item, provider=provider_name, warnings=warnings).model_dump(mode="json")
        finally:
            _local_math_ocr_lock.release()

    return _background_jobs.start(
        kind="local_math_ocr",
        subject_id=item_id,
        owner_id=current_teacher.teacher_id,
        runner=runner,
    )


@router.post("/{item_id}/ocr/jobs", response_model=BackgroundJobView, status_code=202)
def start_library_ocr_job(
    item_id: str,
    command: LibraryOCRCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    if not command.external_processing_consent:
        raise HTTPException(
            status_code=422,
            detail="使用外部 OCR 前必须明确同意发送当前私人文件",
        )
    try:
        get_private_library().get(item_id, owner_id=current_teacher.teacher_id)
        provider = get_library_ocr_provider()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    def runner(progress):
        provider_label = "大模型视觉识别" if provider.name == "deepseek" else "大模型识别"
        progress(0, 1, f"正在调用{provider_label}")
        item, provider_name, warnings = get_private_library().apply_ocr(
            item_id,
            provider=provider,
            consent=True,
            owner_id=current_teacher.teacher_id,
            teacher_id=current_teacher.teacher_id,
        )
        progress(1, 1, "可读题目草稿已生成，等待教师校对")
        return LibraryOCRResult(
            item=item,
            provider=provider_name,
            warnings=warnings,
        ).model_dump(mode="json")

    return _background_jobs.start(
        kind="external_ocr",
        subject_id=item_id,
        owner_id=current_teacher.teacher_id,
        runner=runner,
    )


@router.post("/{item_id}/ai-repair/jobs", response_model=BackgroundJobView, status_code=202)
def start_library_ai_repair_job(
    item_id: str,
    command: LibraryAIRepairCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    # Validate consent and item synchronously so invalid jobs never enter the queue.
    if not command.external_processing_consent:
        raise HTTPException(status_code=422, detail="使用大模型修复前必须允许处理当前校对草稿")
    try:
        get_private_library().get(item_id, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc

    def runner(progress):
        progress(0, 1, "正在调用大模型修复 LaTeX 草稿")
        result = repair_library_latex(item_id, command, current_teacher)
        progress(1, 1, "大模型草稿修复完成")
        return result.model_dump(mode="json")

    return _background_jobs.start(
        kind="library_ai_repair",
        subject_id=item_id,
        owner_id=current_teacher.teacher_id,
        runner=runner,
    )


@router.get("/jobs/{job_id}", response_model=BackgroundJobView)
def get_library_background_job(
    job_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> BackgroundJobView:
    try:
        return _background_jobs.get(job_id, owner_id=current_teacher.teacher_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="后台任务不存在或 API 已重启") from exc


@router.post("/{item_id}/ai-repair", response_model=LibraryAIRepairResult)
def repair_library_latex(
    item_id: str,
    command: LibraryAIRepairCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> LibraryAIRepairResult:
    if not command.external_processing_consent:
        raise HTTPException(
            status_code=422,
            detail="使用大模型修复前必须允许处理当前校对草稿；原 PDF 不会发送",
        )
    try:
        item = get_private_library().get(
            item_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    if item.lifecycle_state == "trashed":
        raise HTTPException(status_code=409, detail="回收站中的资料不能运行 AI 修复")
    settings = get_settings()
    try:
        client = get_library_ai_repair_client()
        chunks = _split_latex_repair_draft(command.draft_text)
        repaired_chunks: list[str] = []
        warnings: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            raw = client.request(
                instructions=(
                    "你是高中数学试卷 LaTeX 校对助手。修复 OCR 文本中的数学公式、上下标、分式、"
                    "集合符号、向量、题号和选项排版。保留原有中文、页码、题目顺序、答案和解析，"
                    "不得补造原文没有的题目、答案、数值或图形。数学表达式统一放在单个美元符号中。"
                    "无法可靠判断的内容原样保留，并写入 warnings。"
                ),
                input_text=json.dumps(
                    {
                        "teacher_instruction": command.instruction,
                        "chunk_position": f"{index}/{len(chunks)}",
                        "draft_text": chunk,
                    },
                    ensure_ascii=False,
                ),
                action="私人资料 LaTeX 校对",
                output_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "repaired_text": {"type": "string"},
                        "warnings": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["repaired_text", "warnings"],
                },
                max_tokens=6000,
            )
            content = json.loads(raw["output"][0]["content"][0]["text"])
            repaired_chunk = str(content["repaired_text"]).strip()
            if not repaired_chunk:
                raise ValueError(f"第 {index}/{len(chunks)} 段修复结果为空")
            repaired_chunks.append(repaired_chunk)
            warnings.extend(str(value) for value in content.get("warnings", []))
        repaired = "\n\n".join(repaired_chunks)
        if not repaired:
            raise ValueError("修复结果为空")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (
        DeepSeekClientError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=503, detail=f"大模型 LaTeX 修复失败：{exc}") from exc
    return LibraryAIRepairResult(
        repaired_text=repaired,
        provider="deepseek",
        model=settings.deepseek_model,
        warnings=warnings,
    )


@router.post("/{item_id}/send-to-structured-import", response_model=ImportBatchResult)
def send_library_item_to_structured_import(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> ImportBatchResult:
    try:
        path, item = get_private_library().file_for_download(
            item_id, owner_id=current_teacher.teacher_id
        )
        if item.file_kind != "pdf":
            raise PrivateLibraryError("只有 PDF 可以转入逐页可视化结构化加工")
        rights_basis = {
            "original": "original",
            "licensed": "licensed",
            "private_teaching_only": "private_research_only",
        }[item.rights_basis]
        return get_pdf_import_studio().create_batch(
            ImportBatchCommand(
                title=f"{item.title} · 可视化重建",
                rights_basis=rights_basis,
                rights_statement=item.rights_statement,
                rights_acknowledged=True,
                owner_id=current_teacher.teacher_id,
            ),
            [(item.original_filename, path.read_bytes())],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except (PrivateLibraryError, PdfImportError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{item_id}/question-candidates", response_model=QuestionCandidateList)
def list_question_candidates(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionCandidateList:
    try:
        return get_private_library().list_question_candidates(
            item_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc


@router.post("/{item_id}/question-candidates", response_model=QuestionCandidateList)
def propose_question_candidates(
    item_id: str,
    command: LibraryQuestionExtractionCommand | None = None,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionCandidateList:
    try:
        library = get_private_library()
        existing = library.list_question_candidates(
            item_id, owner_id=current_teacher.teacher_id
        )
        if existing.items:
            return existing
        item = library.get(item_id, owner_id=current_teacher.teacher_id)
        if item.text_review_status != "confirmed":
            raise PrivateLibraryError("只有教师已确认的文本才能生成拆题候选")
        if item.file_kind != "pdf":
            return library.propose_questions(
                item_id, owner_id=current_teacher.teacher_id
            )
        command = command or LibraryQuestionExtractionCommand()
        if not command.external_processing_consent:
            raise PrivateLibraryError(
                "使用大模型提取 PDF 题目之前，必须允许处理已确认的校对文本"
            )
        structured = _extract_questions_with_deepseek(
            item.corrected_text,
            client=get_library_question_extraction_client(),
        )
        return library.propose_questions(
            item_id,
            owner_id=current_teacher.teacher_id,
            structured_questions=structured,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (
        DeepSeekClientError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(status_code=503, detail=f"大模型 PDF 题目提取失败：{exc}") from exc


@router.patch(
    "/{item_id}/question-candidates/{candidate_id}", response_model=QuestionCandidateView
)
def update_question_candidate(
    item_id: str,
    candidate_id: str,
    command: QuestionCandidateUpdate,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionCandidateView:
    try:
        return get_private_library().update_question_candidate(
            item_id,
            candidate_id,
            command,
            owner_id=current_teacher.teacher_id,
            editor_id=current_teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="拆题候选不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{item_id}/question-candidates/{candidate_id}/curriculum",
    response_model=QuestionCandidateView,
)
def map_question_candidate_curriculum(
    item_id: str,
    candidate_id: str,
    command: QuestionCandidateCurriculumCommand,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
    catalog: CsvCurriculumCatalog = Depends(get_catalog),
) -> QuestionCandidateView:
    try:
        node = catalog.get_node(command.node_id)
        if node.node_type != "knowledge_point":
            raise PrivateLibraryError("必须选择具体知识点，不能只选择册次、章节或小节")
        path = catalog.path_for(node.node_id)
        return get_private_library().map_question_candidate_curriculum(
            item_id,
            candidate_id,
            QuestionCandidateCurriculum(
                node_id=node.node_id,
                name=node.name,
                volume=node.volume,
                chapter=path.get("chapter", ""),
                section=path.get("section", ""),
            ),
            owner_id=current_teacher.teacher_id,
            editor_id=current_teacher.teacher_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="资料、候选或教材知识点不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/{item_id}/question-candidates/{candidate_id}", response_model=QuestionCandidateView
)
def discard_question_candidate(
    item_id: str,
    candidate_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> QuestionCandidateView:
    try:
        return get_private_library().discard_question_candidate(
            item_id, candidate_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="拆题候选不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{item_id}/question-candidates/{candidate_id}/import",
    response_model=CandidateImportResult,
)
def import_question_candidate(
    item_id: str,
    candidate_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> CandidateImportResult:
    try:
        library = get_private_library()
        candidate, resource = library.get_question_candidate(
            item_id, candidate_id, owner_id=current_teacher.teacher_id
        )
        if candidate.imported_question_id:
            return CandidateImportResult(
                candidate=candidate,
                question_id=candidate.imported_question_id,
                already_imported=True,
            )
        if candidate.curriculum is None:
            raise PrivateLibraryError("导入私人题库前必须确认教材知识点")
        question_bank = get_library_question_bank()
        question = question_bank.create_private_resource_question(
            candidate.model_dump(),
            resource=resource.model_dump(),
            owner_id=current_teacher.teacher_id,
        )
        if resource.file_kind == "image" and not question.images:
            source_path, _ = library.file_for_download(
                item_id, owner_id=current_teacher.teacher_id
            )
            question_bank.add_image(
                question.question_id,
                source_path.read_bytes(),
                resource.original_filename,
                "stem",
                f"来源于私人资料《{resource.title}》的原题图片",
                "拆题时保留的原始题图；请教师确认裁剪范围与题目对应关系。",
                "private_resource_question_pipeline",
            )
        marked = library.mark_candidate_imported(
            item_id,
            candidate_id,
            question.question_id,
            owner_id=current_teacher.teacher_id,
        )
        return CandidateImportResult(candidate=marked, question_id=question.question_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="资料或拆题候选不存在") from exc
    except (PrivateLibraryError, QuestionBankError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{item_id}/file")
def download_library_file(
    item_id: str,
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> FileResponse:
    try:
        path, item = get_private_library().file_for_download(
            item_id, owner_id=current_teacher.teacher_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except PrivateLibraryError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return FileResponse(
        path,
        media_type=item.mime_type,
        filename=item.original_filename,
        content_disposition_type="inline",
    )


@router.get("/{item_id}/export")
def export_library_text(
    item_id: str,
    format: Literal["docx", "pdf"] = Query(default="docx"),
    current_teacher: CurrentTeacher = Depends(get_current_teacher),
) -> FileResponse:
    try:
        item = get_private_library().get(
            item_id, owner_id=current_teacher.teacher_id
        )
        rendered = get_library_text_renderer().render(item, format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="私人资料不存在") from exc
    except LibraryExportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(
        rendered.path,
        media_type=rendered.media_type,
        filename=rendered.download_name,
        background=BackgroundTask(
            remove_ephemeral_export,
            rendered.path,
            output_root=get_settings().lesson_export_dir,
        ),
    )
