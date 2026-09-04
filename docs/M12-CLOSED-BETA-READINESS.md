# M12 Closed Beta Readiness

## Goal

Prepare the existing teacher workflows for a small, explicitly admitted Closed Beta
without adding payment, organization, student or public-sharing scope.

M12 proves that a real browser session maps to one server-owned teacher identity,
that capabilities can be enabled safely, that failures are observable without
capturing private content, and that owner data can be backed up, restored and deleted
through rehearsed procedures.

## Fixed boundary

- M12 is Beta readiness, not M13 Beta validation and not production commercial auth.
- Browser, Agent and model payloads never select `owner_id`, role, tenant or trust state.
- Access codes and session tokens are secrets supplied through private environment
  configuration; they never enter Git, logs, analytics or browser-readable storage.
- Session cookies are opaque, HttpOnly and SameSite Strict. The server stores only a
  token hash, supports revocation and enforces expiry. HTTPS Beta deployments set
  `MATH_AI_BETA_SESSION_SECURE_COOKIE=true`; `false` is only for local HTTP development.
- Development may keep the existing fixed local teacher only while Beta access is
  explicitly disabled. Enabling Beta access fails closed without a valid session.
- No payment, subscription, RBAC hierarchy, organization, class, student, team library
  or school administration is added in M12.
- Operational events contain identifiers, capability/status/error classes and timing,
  never prompts, private resource text, private questions, answers or solutions.

## Deep module interface

`BetaAccess` exposes three operations:

1. `issue(access_code)` validates the private roster and creates an expiring opaque
   session grant.
2. `resolve(token)` returns the authenticated teacher identity for valid live sessions.
3. `revoke(token)` invalidates one session without exposing or deleting owner content.

Access-code comparison, token generation/hashing, expiry and SQLite persistence stay
inside the module. FastAPI routes adapt cookies to this interface; business modules
continue to receive only `CurrentTeacher`.

## Slices

1. Beta session identity: private access-code roster, opaque revocable HttpOnly session,
   fail-closed current-teacher dependency, access screen and sign-out.
2. Capability flags: server-owned per-Beta capability snapshot, safe defaults and
   visible unavailable states without weakening business gates.
3. Privacy-safe operations: request/capability/error/latency events, health/readiness
   checks and failure explanations without private payloads.
4. Backup and restore: inventory owner stores, encrypted/private destination contract,
   manifest/checksum verification and a temporary-environment restore drill.
5. Deletion rehearsal and Gate: current-owner export/deletion coverage across supported
   stores, retention record, fixed evaluation, IDOR/session-isolation regression and
   complete Gate E/Gate P/Gate Q readiness review.

## Slice 1 acceptance

- When Beta access is disabled, existing local development continues as
  `owner_teacher`; no access code is required and current data remains reachable.
- When enabled, protected owner routes return 401 without a valid session and never
  fall back to the local owner.
- A valid private access code creates an opaque, expiring, revocable session cookie;
  invalid codes reveal no participant identity.
- Session status exposes only authentication mode, a display label and expiry; it does
  not expose teacher/owner IDs or access codes.
- Two access codes produce isolated current-teacher identities. Using one teacher's
  session cannot read another teacher's Teacher Memory or other owner-only data.
- Sign-out revokes the server session and clears the cookie; replay is rejected.
- Teacher Web shows a dedicated Closed Beta access screen only when the backend requires
  it, keeps the access code out of persistent browser storage and returns to the access
  screen after sign-out.
- Slice 1 does not claim production authentication, password recovery, MFA, RBAC,
  tenant administration or M12 completion.

## Current implementation status

Slices 1–4 are implemented. Automated coverage includes owner isolation,
invalid-code, expiry, revocation, cookie contract, session-snapshot immutability,
Slice-1 database migration, server-side capability denial and local-development
compatibility. Teacher Web provides the access screen and a compact top-right User
settings menu for the current account, Teacher Preferences and sign-out; it preserves
the opaque cookie through same-origin proxies, disables unavailable navigation,
avoids mounting unavailable persistent workspaces and retains structured 403
explanations. The API now emits allow-listed privacy-safe operational events after a
response finishes and exposes a public `/ready` probe with stable component codes;
neither interface accepts or returns teacher content, secrets, identities, URLs or
exception messages. `BetaBackupRecovery` inventories durable owner-bearing stores,
creates consistent SQLite/file snapshots in an explicitly confirmed private
destination, verifies the manifest and every payload checksum, and restores only into
an isolated temporary drill directory. Slice 5 includes real-session, synthetic-store
lifecycle rehearsals and an owner-approved Beta-only block on unsafe legacy REST
workflows and the global model-operations dashboard. Private API responses and
Search/Solve stream proxies explicitly disallow caching. The separately approved
operator-only `BetaSessionMaintenance.preview/prune` supports preview-first,
explicitly confirmed cleanup of expired/revoked sessions, with atomic deletion and
live/unclassifiable record preservation. It has no browser/Agent route or scheduler;
real user records have not been cleaned. FastAPI 638 tests pass (one OS-privileged
symlink test skipped); Teacher Web 102 tests, typecheck and production build pass.
See [data lifecycle evidence and remaining gaps](M12-DATA-LIFECYCLE.md).
Slice 5 is partial and the complete M12 Gate remains open.

Task snapshots now bind the server-owned teacher, and `TeacherAgentSessions.resolve`
scopes model sessions by teacher AND workflow before Search, Solve, authoring or
private-library execution. Foreign/tampered signed session names are refused before
Runtime calls. Original/ancestor backup paths and Windows reparse points are checked
before normalization or IO; unsafe store identifiers are rejected before snapshotting.
Legacy paper creation/composition/update REST entries are also disabled in Beta.
The fixed evaluation entry is `python -m pytest -c apps/api/pytest-m12.ini -q`;
see [current Gate evidence](M12-GATE-REVIEW.md) and the
[session decision](ADR-2026-09-04-OWNER-AGENT-SESSIONS.md). This deployment remains
single API process; old model session names expire across API restarts, not saved content.

The object-level rehearsal now includes 42 real-cookie cases for library/capture,
candidate-parent substitution, background results and paper/lesson history/export.
OCR initialization, paper added-source resolution and lesson version validation
reject foreign object IDs before starting work; domain/transaction checks remain.
Backup CLI privacy has nine additional cases, including successful create/verify/drill:
unconfirmed creation stops before settings, and failures expose only stable codes.
These are isolation/error-handling fixes, not approval for new deletion semantics.

## Slice 2 interface and acceptance

The Closed Beta roster may assign only these product capabilities: `search`,
`solve`, `library`, `authoring`, `lesson`, `paper` and `teacher_memory`.
`BetaAccess.issue` captures the allow-listed capabilities in the opaque session;
`resolve` returns that immutable session snapshot. Unspecified capabilities default
to unavailable. Local development keeps every current capability available.

- Session status exposes capability names, never owner IDs or access codes.
- FastAPI rejects an authenticated Beta session with `403 CAPABILITY_UNAVAILABLE`
  before entering a disabled product module.
- Existing runtime flags and all owner, source, rights, verification, scope and
  persistence gates still run; a Beta capability cannot bypass them.
- Teacher Web disables unavailable navigation and task entries, does not mount a
  disabled persistent workspace, and explains the unavailable state.
- Capability changes require a new session; an already issued session cannot gain
  privileges because a roster is edited in place.
- Slice 2 is a Closed Beta rollout control, not RBAC, subscription entitlement,
  organization roles or a public feature marketplace.

## Slice 3 interface and acceptance

`PrivacySafeOperations` owns the operational-event schema and outcome classifier.
Its public interface accepts only `request_id`, allow-listed `capability`, HTTP
method, outcome, status code, stable error class and elapsed milliseconds. It has no
parameters for headers, query strings, request/response bodies, teacher identity,
resource IDs or exception messages. FastAPI middleware measures the complete HTTP
response, attaches an opaque `X-Request-Id` and emits the event as one structured log
record.

`ReadinessProbe.check` owns the readiness decision. `/ready` adapts its stable
component result to HTTP 200 when ready and 503 when degraded.

- Operational events never contain access codes, session tokens, prompts, private
  resource text, question text, answers, solutions, owner IDs or exception messages.
- Success, client failure, server failure and cancellation are classified from stable
  status/error fields; duration is measured after the response body has completed.
- Readiness checks the API, Beta session store/roster and required Agent runtime/model
  without returning roster entries, secrets, provider URLs or raw dependency errors.
- A required unavailable dependency makes readiness fail closed with a stable public
  code; optional disabled capabilities do not make the whole API unavailable.
- `/ready` is an operational probe, not an analytics endpoint, audit trail or teacher
  activity history. Slice 3 does not persist private task content.

## Slice 4 interface and acceptance

`BetaBackupRecovery.inventory/create_backup/verify_backup/restore_drill` owns the
backup and recovery workflow. Its configured inventory includes durable
owner-bearing question, media, private-library, capture, personal-question, import,
lesson, paper and Teacher Memory stores. The revocable Beta session database is
deliberately excluded so a restore cannot revive expired or revoked sessions;
derived similarity indexes and generated exports are rebuilt instead of backed up.

`PrivateBackupDestination` requires an operator to explicitly confirm that the target
is a private encrypted volume or equivalently protected storage mount. The product
does not expose a browser or Agent backup route.

- Inventory output contains only stable store IDs, kind, presence and file count; it
  does not return filesystem paths, owners, filenames or content.
- SQLite sources use the SQLite online backup API, not raw live-database copying.
  File stores reject symbolic links and junctions before recursion.
- A backup is written to a generated staging directory, verified, then atomically
  published. Manifest checksum, per-file size/SHA-256 and the exact payload file set
  must all match; corruption and unlisted files fail closed.
- A restore drill first verifies the backup, copies only manifest-listed files into a
  fresh temporary directory, rechecks every checksum and runs SQLite
  `PRAGMA integrity_check`. The temporary directory is removed afterwards and live
  stores are never overwritten.
- The operator CLI supports `inventory`, `create`, `verify` and `drill`; `create`
  requires `--confirm-private-storage`. Its output is summary metadata, not content or
  source paths.
- CLI exit code 2 reports `BACKUP_ARGUMENTS_INVALID` or
  `PRIVATE_DESTINATION_CONFIRMATION_REQUIRED` before loading configuration. Exit code
  1 reports `BACKUP_CONFIGURATION_UNAVAILABLE`, `BACKUP_CONTRACT_REJECTED`,
  `BACKUP_INTEGRITY_FAILED`, `BACKUP_STORAGE_UNAVAILABLE` or `BACKUP_OPERATION_FAILED`.
  Raw parameter values, configuration validation messages and exception tracebacks
  are not printed. Inspect the command's static `--help` for usage; do not add secrets
  to command arguments to diagnose a failure.
- Slice 4 proves a local/private backup contract and restoration rehearsal. Cloud
  retention, key management, scheduled backups, disaster-recovery RTO/RPO and live
  replacement remain production operations outside this slice.
