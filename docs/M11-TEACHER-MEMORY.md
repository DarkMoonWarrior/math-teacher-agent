# M11 Teacher Memory

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

- A teacher can open the profile from the global task menu.
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
