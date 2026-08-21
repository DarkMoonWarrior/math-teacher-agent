# Repository instructions for development agents

This file is the short, operational source of truth for agents working in this repository. Read it before changing code. Product details live in `docs/DEVELOPMENT-BOUNDARY.md`; the current route and gates live in `docs/ROADMAP.md` and `docs/PRODUCT-GATES.md`; implementation status lives in `docs/PROJECT-STATUS.md`.

## Product

Build a trustworthy AI workbench for Chinese high-school mathematics teachers. It is not a generic chat product or a traditional question-search website. A teacher should be able to describe a teaching task, provide an image/PDF/private resource, and eventually complete the main preparation workflow through a Teacher Agent.

The current product line is the new `apps/teacher-web` experience. `apps/web` is retained as a legacy reference implementation and source of mature business-flow knowledge; do not copy its visual shell into the new product or add new UI there unless the owner explicitly requests it.

## Non-negotiable rules

1. Mathematical correctness outranks speed. Model output is not a verification result; never bypass `MathVerifier`.
2. Source and rights evidence must remain traceable. Unknown content goes to quarantine/review, never directly to commercial-approved data.
3. Teacher uploads and all derivatives are private by default. Private-to-shared/public requires explicit authorization.
4. Agent code never accesses SQL, SQLite, PostgreSQL, ORM objects, or database files. The only allowed path is Agent → Tool → FastAPI business module → rights/permission/verification gates → storage.
5. AI output starts as `draft` or `needs_teacher_review`. Agent code cannot publish, approve rights, approve verification, permanently delete, or silently relax a hard constraint.
6. DeepSeek Harness is replaceable infrastructure. Business code depends on the product-owned `TeacherAgentRuntime` interface, not Harness types.
7. Do not broaden the audience beyond Chinese high-school mathematics teachers or add student, parent, LMS, ERP, community, payment, or multi-tenant scope ahead of the roadmap.
8. Work on one milestone at a time. A legacy REST module, visible navigation item, or model-generated draft does not prove that the corresponding Agent workflow is complete.

## Current product state

- `Search Agent`: implemented in the FastAPI business backend and exposed in the new teacher workbench.
- `TeacherAgentRuntime` and the isolated DeepSeek Harness adapter: implemented with six controlled read-only tools; `solve_question` was added for M5 through the FastAPI business module.
- `Lesson Agent` and `Paper Agent`: navigation and requirement-drafting previews only in `apps/teacher-web`; their Agent runtimes/tools are not connected.
- Mature lesson-plan, paper, import, library, solution, curriculum, question-bank, and verification modules exist in the migrated backend/legacy UI. Existing REST workflows do not mean the corresponding new Agent capability is complete.
- Teacher identity, cloud isolation, billing, and public commercial operation are not implemented.
- M0-M4 are complete. M5 Solve Agent is the only active milestone; M6 and later must not start before the M5 Gate and owner confirmation.

## Repository seams

- `apps/teacher-web`: primary product UI. It depends on product-owned `TeacherWorkspace` contracts and same-origin `/api/v1` routes.
- `apps/api`: modular FastAPI business backend and the only owner of business rules, validation, rights decisions, and storage access.
- `apps/agent`: isolated Node/TypeScript Agent runtime. DeepSeek Harness imports stay here. It uses only the allowlisted internal Tool gateway.
- `apps/web`: legacy/reference UI. Preserve it for behaviour comparison and incremental extraction; it is not the default product entry.
- `data/test-fixtures`: synthetic test data only. Never turn fixtures into production content.
- `data/commercial-approved`: commercial content only after RightsGate + MathVerifier + Teacher Review.
- `data/runtime` and `data/private-runtime`: local/private runtime data, always ignored by Git.

## Decision policy

Proceed autonomously for clear bugs, tests, refactors, type errors, performance work, documentation corrections, and implementation details that preserve behaviour.

Stop and explain impact before changing product behaviour, teacher workflow, data meaning, rights rules, private/public state, deletion semantics, destructive migrations, permissions, publication gates, or commercial rules.

Do not invent requirements to finish a task. When old documents conflict with the current sources of truth, use this order:

1. explicit owner instruction;
2. `docs/DEVELOPMENT-BOUNDARY.md`;
3. `docs/ROADMAP.md` and `docs/PRODUCT-GATES.md`;
4. `docs/PROJECT-STATUS.md` and `docs/ARCHITECTURE.md`;
5. historical documents under `docs/commercial-v1`, `docs/high-school-math-ai`, and the planning PDF.

## Verification

Run checks proportional to the changed seam:

- Primary UI: `pnpm typecheck:teacher` and `pnpm build:teacher`.
- Agent runtime: `pnpm typecheck:agent`, `pnpm test:agent`, and `pnpm build:agent`.
- Backend: `python -m pytest apps/api/tests` from an environment with `apps/api[dev]` installed.
- Legacy UI only when touched: `pnpm typecheck:legacy-web` and `pnpm build:legacy-web`.

Never use real model credentials in automated tests. Never commit `.env`, databases, uploads, exports, private resources, or third-party question content.

Before declaring a milestone complete, apply Gate E from `docs/PRODUCT-GATES.md`, record what is complete/partial/unstarted, and do not begin the next milestone until the owner confirms the transition.
