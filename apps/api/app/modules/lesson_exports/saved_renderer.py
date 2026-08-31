from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.lesson_plans.schemas import LessonSavedVersion

from .renderer import (
    ExportFormat,
    LessonPlanDocumentRenderer,
    LessonPlanExportError,
    RenderedLessonPlan,
)


class SavedLessonPlanDocumentRenderer(LessonPlanDocumentRenderer):
    """Document Adapter for an immutable M10 lesson snapshot.

    The compact-reference-guide token map and workshop-agenda first page keep
    the exported teacher document aligned with the existing product language.
    """

    def render_saved(
        self,
        saved: LessonSavedVersion,
        export_format: ExportFormat,
    ) -> RenderedLessonPlan:
        if export_format not in {"docx", "pdf"}:
            raise LessonPlanExportError(f"不支持的导出格式：{export_format}")
        target_dir = self.output_root / "saved-lesson-versions" / export_format
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "-", saved.lesson_plan_id)
        download_name = f"lesson-plan-{safe_id}-v{saved.version}.{export_format}"
        path = target_dir / download_name
        try:
            if export_format == "docx":
                self._render_saved_docx(saved, path)
                media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                self._render_saved_pdf(saved, path)
                media_type = "application/pdf"
        except LessonPlanExportError:
            raise
        except Exception as exc:  # pragma: no cover - third-party failure crosses the Adapter seam
            raise LessonPlanExportError(f"教案导出失败：{exc}") from exc
        return RenderedLessonPlan(path=path, media_type=media_type, download_name=download_name)

    def _render_saved_docx(self, saved: LessonSavedVersion, path: Path) -> None:
        draft = saved.draft
        blueprint = draft.source_draft.blueprint
        curriculum = draft.source_draft.curriculum
        document = Document()
        section = document.sections[0]
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.top_margin = section.bottom_margin = Inches(1)
        section.left_margin = section.right_margin = Inches(1)
        section.header_distance = section.footer_distance = Inches(0.492)
        self._configure_docx_styles(document)
        ordered = self._create_numbering(document, ordered=True)
        bullet = self._create_numbering(document, ordered=False)
        self._add_saved_docx_header_footer(section, saved.version)

        kicker = document.add_paragraph()
        kicker.paragraph_format.space_after = Pt(4)
        self._set_run_font(kicker.add_run("高中数学 · 已保存教师教案"), 9, self.BLUE, bold=True)
        title = document.add_paragraph()
        title.paragraph_format.space_after = Pt(5)
        self._set_run_font(title.add_run(draft.title), 24, self.TEXT, bold=True)
        subtitle = document.add_paragraph()
        subtitle.paragraph_format.space_after = Pt(12)
        curriculum_label = curriculum.name if curriculum else blueprint.grade_scope
        self._set_run_font(
            subtitle.add_run(f"{curriculum_label} · 精确版本 v{saved.version} · {saved.saved_at}"),
            10,
            self.MUTED,
        )

        metrics = [
            ("课型", self._lesson_type_label(blueprint.lesson_type)),
            ("课时", f"{blueprint.duration_minutes} 分钟"),
            ("教学目标", f"{len(draft.objectives)} 项"),
            ("例题练习", f"{len(draft.questions)} 道"),
        ]
        metric_table = document.add_table(rows=1, cols=4)
        self._set_table_geometry(metric_table, [2340] * 4)
        for cell, (label, value) in zip(metric_table.rows[0].cells, metrics, strict=True):
            self._shade_cell(cell, self.PALE_BLUE)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            self._set_run_font(paragraph.add_run(f"{label}\n"), 8, self.MUTED)
            self._set_run_font(paragraph.add_run(value), 10, self.TEXT, bold=True)

        status_table = document.add_table(rows=1, cols=1)
        self._set_table_geometry(status_table, [self.PAGE_WIDTH_DXA])
        self._shade_cell(status_table.cell(0, 0), self.WARNING)
        status = status_table.cell(0, 0).paragraphs[0]
        status.paragraph_format.space_after = Pt(0)
        self._set_run_font(status.add_run("内容状态："), 9, "805A00", bold=True)
        self._set_run_font(
            status.add_run("AI 组织文本待教师复核；保存和排版不会升级数学验证或教师审核状态。"),
            9,
            "805A00",
        )

        self._docx_heading(document, "一、教学目标与证据", 1)
        objective_table = document.add_table(rows=1, cols=3)
        self._set_table_geometry(objective_table, [900, 4230, 4230])
        for cell, label in zip(objective_table.rows[0].cells, ["目标", "目标描述", "可观察证据"], strict=True):
            self._shade_cell(cell, self.PALE_BLUE)
            self._set_run_font(cell.paragraphs[0].add_run(label), 9, self.DARK_BLUE, bold=True)
        self._repeat_table_header(objective_table.rows[0])
        for objective in draft.objectives:
            for cell, value in zip(
                objective_table.add_row().cells,
                [objective.objective_id, objective.text, objective.observable_evidence],
                strict=True,
            ):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                self._set_run_font(cell.paragraphs[0].add_run(value), 9, self.TEXT)

        self._docx_heading(document, "二、教学重点与难点", 1)
        self._docx_heading(document, "教学重点", 2)
        self._add_docx_list(document, draft.key_points, bullet)
        self._docx_heading(document, "教学难点", 2)
        self._add_docx_list(document, draft.difficulties, bullet)

        self._docx_heading(document, "三、教学流程", 1)
        flow_table = document.add_table(rows=1, cols=5)
        widths = [1200, 650, 2000, 3000, 2510]
        self._set_table_geometry(flow_table, widths)
        for cell, label in zip(
            flow_table.rows[0].cells,
            ["环节", "时间", "目的与目标", "师生活动", "评价与来源"],
            strict=True,
        ):
            self._shade_cell(cell, self.PALE_BLUE)
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            self._set_run_font(cell.paragraphs[0].add_run(label), 8.5, self.DARK_BLUE, bold=True)
        self._repeat_table_header(flow_table.rows[0])
        for phase in draft.teaching_flow:
            values = [
                phase.title,
                f"{phase.minutes}′",
                f"{phase.purpose}\n目标：{'、'.join(phase.objective_ids)}",
                f"教师：{phase.teacher_activity}\n学生：{phase.student_activity}",
                f"{phase.assessment}\n题目：{'、'.join(phase.question_ids) or '无'}\n资料：{'、'.join(phase.resource_ids) or '无'}",
            ]
            for index, (cell, value) in enumerate(zip(flow_table.add_row().cells, values, strict=True)):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER if index < 2 else WD_ALIGN_PARAGRAPH.LEFT
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                self._set_run_font(cell.paragraphs[0].add_run(value), 8, self.TEXT)

        self._docx_heading(document, "四、例题与练习", 1)
        if not draft.questions:
            document.add_paragraph("本教案未引用题目。")
        for index, question in enumerate(draft.questions, start=1):
            self._docx_heading(document, f"{index}. {question.usage}", 2)
            meta = document.add_paragraph()
            meta.paragraph_format.space_after = Pt(4)
            self._set_run_font(
                meta.add_run(
                    f"题号 {question.question_id} · revision {question.source_revision} · "
                    f"{question.source_kind} · 阶段 {question.phase_id}"
                ),
                8,
                self.MUTED,
            )
            document.add_paragraph(question.stem_plain)
            if question.options:
                self._add_docx_list(
                    document,
                    [f"{option.key}. {option.text}" for option in question.options],
                    bullet,
                )
            answer = document.add_paragraph()
            self._set_run_font(answer.add_run("参考答案："), 10, self.DARK_BLUE, bold=True)
            answer.add_run(question.answer_value)
            self._docx_heading(document, "解析", 3)
            self._add_docx_list(document, question.solution_steps, ordered)
            final = document.add_paragraph()
            self._set_run_font(final.add_run("最终答案："), 10, self.DARK_BLUE, bold=True)
            final.add_run(question.final_answer)
            trust = document.add_paragraph()
            self._set_run_font(
                trust.add_run(
                    f"权利：{question.rights_basis} · 验证：{question.verification_status} · "
                    f"审核：{question.review_status} · 范围：{question.owner_scope}"
                ),
                8,
                self.MUTED,
            )

        self._docx_heading(document, "五、评价设计", 1)
        assessment_table = document.add_table(rows=1, cols=4)
        self._set_table_geometry(assessment_table, [900, 2200, 3560, 2700])
        for cell, label in zip(assessment_table.rows[0].cells, ["编号", "评价", "方法", "达成标准与目标"], strict=True):
            self._shade_cell(cell, self.PALE_BLUE)
            self._set_run_font(cell.paragraphs[0].add_run(label), 9, self.DARK_BLUE, bold=True)
        self._repeat_table_header(assessment_table.rows[0])
        for item in draft.assessments:
            values = [item.assessment_id, item.title, item.method, f"{item.success_criteria}\n目标：{'、'.join(item.objective_ids)}"]
            for cell, value in zip(assessment_table.add_row().cells, values, strict=True):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                self._set_run_font(cell.paragraphs[0].add_run(value), 8.5, self.TEXT)

        self._docx_heading(document, "六、分层作业", 1)
        self._add_docx_list(document, draft.homework, ordered)
        self._docx_heading(document, "七、板书设计", 1)
        self._add_docx_list(document, draft.board_plan, bullet)
        self._docx_heading(document, "八、教师备注", 1)
        self._add_docx_list(document, draft.teacher_notes, bullet)
        document.add_page_break()
        self._docx_heading(document, "九、精确来源与可信摘要", 1)
        source_table = document.add_table(rows=1, cols=5)
        self._set_table_geometry(source_table, [1500, 2500, 1100, 1900, 2360])
        for cell, label in zip(source_table.rows[0].cells, ["类型", "精确 ID", "revision", "权利", "验证与 owner 范围"], strict=True):
            self._shade_cell(cell, self.PALE_BLUE)
            self._set_run_font(cell.paragraphs[0].add_run(label), 8.5, self.DARK_BLUE, bold=True)
        self._repeat_table_header(source_table.rows[0])
        for source in draft.source_manifest:
            values = [source.source_kind, source.source_id, source.source_revision, source.rights_basis, f"{source.verification_status}\n{source.owner_scope}"]
            for cell, value in zip(source_table.add_row().cells, values, strict=True):
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
                cell.paragraphs[0].paragraph_format.space_after = Pt(0)
                self._set_run_font(cell.paragraphs[0].add_run(value), 8, self.TEXT)

        document.core_properties.title = draft.title
        document.core_properties.subject = f"高中数学教师教案 · 精确版本 v{saved.version}"
        document.core_properties.author = "数研备课"
        document.core_properties.comments = (
            f"lesson_plan_id={saved.lesson_plan_id}; version={saved.version}; "
            f"fingerprint={saved.draft_fingerprint}; AI 组织文本待教师复核。"
        )
        document.save(path)

    def _render_saved_pdf(self, saved: LessonSavedVersion, path: Path) -> None:
        draft = saved.draft
        blueprint = draft.source_draft.blueprint
        curriculum = draft.source_draft.curriculum
        regular_path, bold_path = self._resolve_pdf_fonts()
        regular_name, bold_name = "MathSavedLessonCJK", "MathSavedLessonCJKBold"
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        styles = self._pdf_styles(regular_name, bold_name)
        curriculum_label = curriculum.name if curriculum else blueprint.grade_scope
        story = [
            Paragraph("高中数学 · 已保存教师教案", styles["Kicker"]),
            Paragraph(self._escape(draft.title), styles["LessonTitle"]),
            Paragraph(self._escape(f"{curriculum_label} · 精确版本 v{saved.version} · {saved.saved_at}"), styles["Subtitle"]),
        ]
        metrics = [
            ("课型", self._lesson_type_label(blueprint.lesson_type)),
            ("课时", f"{blueprint.duration_minutes} 分钟"),
            ("教学目标", f"{len(draft.objectives)} 项"),
            ("例题练习", f"{len(draft.questions)} 道"),
        ]
        metric_table = Table(
            [[Paragraph(f"<font size='8' color='#{self.MUTED}'>{label}</font><br/><b>{value}</b>", styles["Metric"]) for label, value in metrics]],
            colWidths=[1.625 * inch] * 4,
        )
        metric_table.setStyle(TableStyle(self._pdf_table_style(background=self.PALE_BLUE)))
        story.extend([metric_table, Spacer(1, 8)])
        warning = Table(
            [[Paragraph("<b>内容状态：</b>AI 组织文本待教师复核；保存和排版不会升级数学验证或教师审核状态。", styles["Warning"])]],
            colWidths=[6.5 * inch],
        )
        warning.setStyle(TableStyle(self._pdf_table_style(background=self.WARNING, border="E0C77A")))
        story.extend([warning, Spacer(1, 6)])

        story.append(Paragraph("一、教学目标与证据", styles["LessonHeading1"]))
        objective_rows = [[Paragraph(label, styles["TableHead"]) for label in ["目标", "目标描述", "可观察证据"]]]
        objective_rows.extend([
            [
                Paragraph(self._escape(item.objective_id), styles["TableCellCenter"]),
                Paragraph(self._escape(item.text), styles["TableCell"]),
                Paragraph(self._escape(item.observable_evidence), styles["TableCell"]),
            ]
            for item in draft.objectives
        ])
        table = Table(objective_rows, colWidths=[0.625 * inch, 2.9375 * inch, 2.9375 * inch], repeatRows=1)
        table.setStyle(TableStyle(self._pdf_table_style(header=True)))
        story.append(table)
        story.append(Paragraph("二、教学重点与难点", styles["LessonHeading1"]))
        story.append(Paragraph("教学重点", styles["LessonHeading2"]))
        story.extend(self._pdf_list(draft.key_points, styles, ordered=False))
        story.append(Paragraph("教学难点", styles["LessonHeading2"]))
        story.extend(self._pdf_list(draft.difficulties, styles, ordered=False))

        story.append(Paragraph("三、教学流程", styles["LessonHeading1"]))
        flow_rows = [[Paragraph(label, styles["TableHead"]) for label in ["环节", "时间", "目的与目标", "师生活动", "评价与来源"]]]
        for phase in draft.teaching_flow:
            flow_rows.append([
                Paragraph(self._escape(phase.title), styles["TableCellCenter"]),
                Paragraph(f"{phase.minutes}′", styles["TableCellCenter"]),
                Paragraph(self._escape(f"{phase.purpose}\n目标：{'、'.join(phase.objective_ids)}"), styles["TableCell"]),
                Paragraph(self._escape(f"教师：{phase.teacher_activity}\n学生：{phase.student_activity}"), styles["TableCell"]),
                Paragraph(self._escape(f"{phase.assessment}\n题目：{'、'.join(phase.question_ids) or '无'}\n资料：{'、'.join(phase.resource_ids) or '无'}"), styles["TableCell"]),
            ])
        flow = Table(flow_rows, colWidths=[0.8 * inch, 0.45 * inch, 1.4 * inch, 2.05 * inch, 1.8 * inch], repeatRows=1)
        flow.setStyle(TableStyle(self._pdf_table_style(header=True)))
        story.append(flow)

        story.append(Paragraph("四、例题与练习", styles["LessonHeading1"]))
        if not draft.questions:
            story.append(Paragraph("本教案未引用题目。", styles["Body"]))
        for index, question in enumerate(draft.questions, start=1):
            story.append(Paragraph(f"{index}. {self._escape(question.usage)}", styles["LessonHeading2"]))
            story.append(Paragraph(self._escape(
                f"题号 {question.question_id} · revision {question.source_revision} · {question.source_kind} · 阶段 {question.phase_id}"
            ), styles["Small"]))
            story.append(Paragraph(self._escape(question.stem_plain), styles["Body"]))
            if question.options:
                story.extend(self._pdf_list([f"{option.key}. {option.text}" for option in question.options], styles, ordered=False))
            story.append(Paragraph(f"<b>参考答案：</b>{self._escape(question.answer_value)}", styles["Body"]))
            story.append(Paragraph("解析", styles["LessonHeading2"]))
            story.extend(self._pdf_list(question.solution_steps, styles, ordered=True))
            story.append(Paragraph(f"<b>最终答案：</b>{self._escape(question.final_answer)}", styles["Body"]))
            story.append(Paragraph(self._escape(
                f"权利：{question.rights_basis} · 验证：{question.verification_status} · 审核：{question.review_status} · 范围：{question.owner_scope}"
            ), styles["Small"]))

        story.append(Paragraph("五、评价设计", styles["LessonHeading1"]))
        assessment_rows = [[Paragraph(label, styles["TableHead"]) for label in ["编号", "评价", "方法", "达成标准与目标"]]]
        for item in draft.assessments:
            assessment_rows.append([
                Paragraph(item.assessment_id, styles["TableCellCenter"]),
                Paragraph(self._escape(item.title), styles["TableCell"]),
                Paragraph(self._escape(item.method), styles["TableCell"]),
                Paragraph(self._escape(f"{item.success_criteria}\n目标：{'、'.join(item.objective_ids)}"), styles["TableCell"]),
            ])
        assessment = Table(assessment_rows, colWidths=[0.55 * inch, 1.5 * inch, 2.45 * inch, 2 * inch], repeatRows=1)
        assessment.setStyle(TableStyle(self._pdf_table_style(header=True)))
        story.append(assessment)
        story.extend(self._pdf_list_section("六、分层作业", draft.homework, styles, ordered=True))
        story.extend(self._pdf_list_section("七、板书设计", draft.board_plan, styles, ordered=False))
        story.extend(self._pdf_list_section("八、教师备注", draft.teacher_notes, styles, ordered=False))

        story.append(Paragraph("九、精确来源与可信摘要", styles["LessonHeading1"]))
        source_rows = [[Paragraph(label, styles["TableHead"]) for label in ["类型", "精确 ID", "revision", "权利", "验证与 owner 范围"]]]
        for source in draft.source_manifest:
            source_rows.append([
                Paragraph(self._escape(source.source_kind), styles["TableCell"]),
                Paragraph(self._escape(source.source_id), styles["TableCell"]),
                Paragraph(self._escape(source.source_revision), styles["TableCellCenter"]),
                Paragraph(self._escape(source.rights_basis), styles["TableCell"]),
                Paragraph(self._escape(f"{source.verification_status}\n{source.owner_scope}"), styles["TableCell"]),
            ])
        sources = Table(source_rows, colWidths=[1 * inch, 1.7 * inch, 0.7 * inch, 1.25 * inch, 1.85 * inch], repeatRows=1)
        sources.setStyle(TableStyle(self._pdf_table_style(header=True)))
        story.append(sources)

        pdf = SimpleDocTemplate(
            str(path),
            pagesize=letter,
            leftMargin=inch,
            rightMargin=inch,
            topMargin=inch,
            bottomMargin=inch,
            title=draft.title,
            author="数研备课",
            subject=f"高中数学教师教案 · 精确版本 v{saved.version}",
        )

        def decorate_page(canvas, document) -> None:
            canvas.saveState()
            canvas.setFont(regular_name, 8)
            canvas.setFillColor(colors.HexColor(f"#{self.MUTED}"))
            canvas.drawString(inch, 10.5 * inch, "数研备课 | 高中数学教师教案")
            canvas.drawString(inch, 0.48 * inch, f"已保存版本 v{saved.version} · 待教师复核")
            canvas.drawRightString(7.5 * inch, 0.48 * inch, f"第 {document.page} 页")
            canvas.restoreState()

        pdf.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)

    def _add_saved_docx_header_footer(self, section, version: int) -> None:
        header = section.header.paragraphs[0]
        header.paragraph_format.space_after = Pt(0)
        self._set_run_font(header.add_run("数研备课 | 高中数学教师教案"), 8, self.MUTED)
        footer = section.footer.paragraphs[0]
        footer.paragraph_format.space_after = Pt(0)
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._set_run_font(footer.add_run(f"已保存版本 v{version} · 待教师复核"), 8, self.MUTED)
