# M11 Teacher Memory

> 状态同步（2026-09-05）：M0–M12 已完成，项目所有者已确认进入 M13，当前进行中。本文的切片过程、测试数量和 Gate 结论保留为当时证据；后续行为与当前边界见 [开发状态](PROJECT-STATUS.md) 和 [开发边界](DEVELOPMENT-BOUNDARY.md)。

## Goal

Give each teacher a private, inspectable and reversible preference profile that can
support later teacher workflows without silently storing lesson, question or source
content.

## Fixed boundary

- Owner identity is supplied by the server. Browser payloads never select an owner.
- The first slice stores only allow-listed structured preferences.
- Explicit preferences are labelled `teacher_explicit` with confidence `1.0`.
- Raw prompts, question stems, solutions, lesson bodies and private-library text are
  not teacher-memory values.
- Automatic learning defaults to off and is controlled by the teacher.
- M11 does not add accounts, roles, sharing, students, billing or multi-tenant admin.

## Deep module interface

`TeacherMemory` exposes three operations:

1. `profile(owner_id)` returns the complete current profile.
2. `apply(owner_id, command)` validates and applies one preference mutation.
3. `planning_defaults(owner_id)` returns only allow-listed defaults, without owner
   identity or task/private content, for product-owned planners.

SQLite schema, value encoding, provenance creation and version checks stay behind
this interface. HTTP routes adapt owner-scoped browser requests to these operations.

## Slices

1. Explicit preferences: view, add/change, remove and control automatic learning.
2. Preference use: apply saved defaults only when a task field is absent, with a
   visible indication and one-click override.
3. Explainable inference: when enabled, propose inferred preferences with evidence
   category and confidence; never promote silently.
4. Feedback loop: teacher accepts, rejects or corrects proposals; rejected signals
   are not immediately relearned.
5. Evaluation and lifecycle: isolation, retention, export/deletion and regression
   coverage across supported workflows.

## Slice 1 acceptance

- A teacher can open the profile from the top-right Settings / User menu (moved out of New Task).
- Empty state has automatic learning off.
- Allowed preferences can be saved, changed and removed.
- Every saved item shows source and confidence.
- A second teacher cannot read or mutate the first teacher's profile.
- Arbitrary text and unsupported keys are rejected at the module boundary.

## Slice 2 acceptance

- Lesson and Paper planning read defaults using the current server-owned teacher.
- A brief that explicitly states grade, lesson duration or paper difficulty always
  wins over memory.
- Missing lesson grade/duration and missing paper grade/difficulty can use saved
  allow-listed defaults; lesson duration is not reused as an exam duration.
- Every value actually applied is returned with its source and confidence and is
  shown in the editable blueprint.
- Editing a field in the current blueprint removes its applied-default marker and
  does not mutate the saved preference profile.
- Preferences do not bypass high-school scope, source, rights, owner, review,
  verification, selection, save or export gates.

## Slice 3 acceptance

- Inference runs only while the current teacher has automatic learning enabled.
- Only product-owned signals from explicitly saved lesson and paper versions are
  observed; browser requests cannot submit evidence, owner, source or confidence.
- Observations contain only allow-listed structured values and an opaque saved-version
  identifier. Briefs, titles, question content, lesson bodies and private-source text
  are never stored as memory evidence.
- A proposal appears only after the same structured value is observed at least three
  times within one evidence category. Duplicate saved-version signals are idempotent.
- Every proposal shows its evidence category, occurrence count and server-calculated
  confidence, remains owner-scoped and is clearly marked as pending teacher review.
- Proposals are stored separately from explicit preferences and are never returned by
  `planning_defaults`. Saving an explicit preference removes stale proposals and
  observations for that key; no proposal is automatically promoted.
- Slice 3 itself did not simulate accept, reject or correction; those actions are
  delivered by the separate Slice 4 controls below.

## Slice 4 acceptance

- Every pending proposal offers three explicit owner actions: accept, reject, or
  correct and accept. Browser requests identify a proposal but cannot provide owner,
  evidence category, occurrence count, source, or confidence.
- Accepting uses the server-owned proposed value; correcting validates the replacement
  against the same allow-list. Both actions become confidence `1.0`
  `teacher_explicit` preferences because a teacher explicitly confirmed the result.
- Accepted and corrected values become eligible for `planning_defaults`; the original
  proposal and same-key observations are removed so no inferred value remains active
  beside the explicit preference.
- Rejecting does not create or change a preference. The rejection records only the
  structured proposed value, evidence category, count, confidence and owner-scoped
  proposal identifier; it stores no task or private content.
- A rejected value cannot be proposed again until at least three new distinct saved
  version signals of the same value and evidence category have arrived. Duplicate
  evidence remains idempotent.
- Proposal lookup and feedback are owner-scoped, optimistic profile version checks
  still apply, and another teacher receives the same not-found result as a missing or
  already-handled proposal.
- Feedback history export/deletion, retention policy, fixed evaluation and the full
  M11 Gate remain Slice 5 work.

## Slice 5 acceptance

- The profile exposes a readable retention note and a structured feedback history.
  Feedback includes the preference key, proposed/corrected structured value, action,
  evidence category, occurrence count and confidence, but never owner identifiers,
  saved-version identifiers or task/private content.
- The current teacher can export the complete inspectable profile as JSON. Export is
  resolved from server-owned identity and cannot include another teacher's memory.
- Full deletion requires the exact phrase `删除全部教师记忆`. It removes the current
  owner's explicit preferences, observations, pending proposals and feedback, turns
  automatic learning off, and leaves other owners untouched.
- Deletion advances rather than resets the profile version, so a stale pre-deletion
  page cannot recreate deleted preferences without first refreshing.
- A fixed 26-case project-authored synthetic evaluation covers preferences, planning
  precedence, inference, feedback, export, deletion, owner isolation and Agent
  privilege. All 12 violation categories are zero.
- FastAPI, Teacher Web, Agent and legacy compatibility regression/typecheck/build
  pass. The real Teacher Web panel shows export and lifecycle controls, keeps delete
  disabled without the fixed phrase, scrolls within the panel, has no page overflow
  and produces no browser console warning/error.
- Slice 5 completes the functional M11 Gate, but does not authorize M12. A rollback
  commit and explicit owner transition confirmation are still required.
