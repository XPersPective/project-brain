# Project Brain 3.0 — Frontend, Backend & State Machine Quality Rubric

Load this file during Genesis/planning of UI or backend domains, before writing task specs that touch UI or backend areas, and during `PB review`.

Apply requirements to the actual change and target platform. Reuse the existing design
system and architecture. A small defect needs its reproduction, shared fix and relevant
check; it does not need a new framework, layers, theme or product interview. Record a
reason when a state, database migration or backend is inapplicable. Tool gates check
evidence freshness and coverage; a reviewer must judge its truth and product quality.

## 0. Product and end-to-end delivery

- In `target.md`, record users, the main journey, non-goals, measurable success and the
  riskiest unresolved assumption. No separate product document is required.
- For a new visual direction, flow or architecture, compare 2–3 concrete options and
  record the selected direction in an ADR. Existing accepted choices stay the baseline.
- Order milestones: cheapest risk probe → one real working journey → remaining scope.
  Show the representative render and working journey early; feedback changes shared
  tokens, components or transitions. Silence is not approval.
- Frontend and backend share one data/error/state contract. A UI save must persist and
  read back through the real service; mock success is recorded as mock-only evidence.
- Name realistic performance budgets where relevant: bounded page/payload size, query
  count and latency. Review authorization per actor/resource, recovery, privacy and
  observability with the same attention as the happy path.

---

## 1. Frontend & UI/UX Excellence Rubric

Generic, unstyled, or fragile UI output is treated as a **blocking defect** (`QUALITY` or `MAJOR` finding). Every project with a user interface must satisfy three requirements:

### 1.1 Design System & Token Foundation (Mandatory First UI Milestone)
Before feature screens, establish or identify the shared Design System & Token Foundation
(ADR + foundation task for a new UI; reuse and extend an existing foundation):
- **Typography Scale**: Display, headline, title, body, caption, and monospace roles with explicit font family, size, weight, line-height, and letter-spacing tokens.
- **Semantic Color Tokens**: Theme roles (`surface`, `text-primary`, `text-muted`, `accent`, `border`, `danger`, `success`); light/dark variants when required. Feature components use shared tokens, with reasoned exceptions recorded once.
- **Spacing, Radius & Elevation Grid**: 4px/8px spatial rhythm, consistent border-radius scale, and elevation/shadow tokens.
- **Motion & Micro-interaction Tokens**: Fast (`120-160ms`), standard (`200-260ms`), and emphasized (`320ms`) transitions with `prefers-reduced-motion` support.
- **Responsive Breakpoints & Shell**: Choose breakpoints from the real content and target devices; name compact and wide test viewports. No clipped content or unreachable actions.

### 1.2 The UI Verification Triad (Required on Every UI Task)
Every task touching UI/frontend domains or files must include typed Acceptance items covering all three legs of the UI Triad, proven via `PB evidence` before `PB accept`:

1. **`[visual]` — Rendered Viewport Proof**:
   - Verified on real rendered output (browser screenshot, Flutter golden/emulator capture, desktop window capture) attached via `PB evidence <PB-NNN> --kind visual --criterion <id> --file <screenshot.png>`.
   - Reading JSX/HTML/Dart/CSS source code is **never** accepted as `[visual]` proof.
   - Must verify both compact/narrow and wide viewports, hierarchy clarity, alignment, and absence of clipped text or overlapping controls.
2. **`[interaction]` — Complete State & Flow Proof**:
   - Exercise each applicable view state (record why an inapplicable state is absent):
     - `initial / idle`
     - `loading / skeleton / optimistic pending`
     - `empty` (with a clear explanation and primary action, never a blank box)
     - `error` (human-readable cause + non-destructive retry that preserves user input)
     - `populated / success`
   - Rapid double-click / double-tap on submit or destructive actions must be idempotent (disabled while in flight or deduplicated).
   - Recorded via `PB evidence <PB-NNN> --kind interaction --criterion <id> --note "action -> state transition -> result"`.
3. **`[accessibility]` — Ergonomics & Contrast Proof**:
   - Keyboard navigation and visible `:focus-visible` ring on web/desktop; logical focus order and `Escape` dismissal for modals/drawers.
   - Touch targets follow platform units: 48dp on Android, 44pt on iOS, and an appropriate web target size (44 CSS px for touch is the preferred project baseline). Do not equate dp, pt and CSS px.
   - Semantic labels (`aria-label` / `Semantics`) on all icon-only buttons and inputs.
   - WCAG AA contrast ratios ($\ge 4.5:1$ normal text, $\ge 3:1$ large text and active controls) and layout survival at `200%` text scaling.

### 1.3 Blocking `QUALITY` Review Severity
Reviewers (`PB review`) must emit `- finding QUALITY: <defect>` whenever a UI implementation uses unstyled browser defaults, hardcoded color/spacing literals instead of tokens, missing empty/loading/error states, broken responsive wrapping, or jarring layout shifts.
- A `QUALITY` finding cannot be deferred to a follow-up task by an agent. A waiver needs actual user approval, named in the finding; `owner: user` is a declared record, not authenticated approval.

---

## 2. Backend, API & State Architecture Excellence Rubric

### 2.1 Layer Boundaries (Clean Architecture)
- Preserve existing conventions and keep responsibilities separate. Small programs may use functions/modules for these boundaries; do not invent repositories, interfaces or classes with no consumer.
- **Domain Layer**: Pure business rules, entities, value objects, and repository interfaces. Zero dependency on UI frameworks, HTTP clients, ORMs, or platform SDKs.
- **Data / Infrastructure Layer**: Repository implementations, DTO mappers, SQL/ORM queries, external API clients, and local caches.
- **Presentation / Transport Layer**: HTTP/RPC handlers, CLI entrypoints, or UI state controllers. Thin adapters that validate input, invoke Domain use cases, and map structured results.
- Cross-layer shortcuts (e.g., SQL queries or raw HTTP calls inside UI widgets or route templates) are `MAJOR` or `BLOCKER` review findings.

### 2.2 Explicit State Machines (No Boolean Flag Soup)
- Model stateful workflows, async lifecycles, and domain entities with **explicit state machines** (`sealed` classes, discriminated unions, or transition tables) and named events.
- Impossible state combinations (e.g., `isLoading == true && hasError == true && data != null` via independent booleans) are forbidden.
- Every state transition must define its guard conditions, side effects, and recovery path.
- Persistence writes affecting state transitions must be atomic (`write -> fsync -> os.replace` or database transaction).

### 2.3 Boundary Validation & Structured Error Contract
- Validate and parse all external input (request bodies, query params, CLI args, webhook payloads, environment variables, third-party API responses) at the system boundary before reaching domain logic.
- Use the platform's existing structured failure contract (e.g. typed errors, stable CLI exit codes, or HTTP Problem Details); no dependency or wrapper solely to match an example.
- Never leak stack traces, raw SQL errors, file paths, or secrets (`API_KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `DATABASE_URL`) in responses or logs.

### 2.4 Concurrency, Idempotency & Data Integrity
- Mutating operations must define idempotency behavior (idempotency keys, unique constraints, or file/row locks) and be tested against duplicate/concurrent requests.
- Database/schema changes verify forward migration and a safe rollback or backward-compatibility recovery path against non-empty data. Never fabricate a destructive `down` merely to tick a box.
- List/collection endpoints must bound page size and eliminate N+1 query patterns.
- External side effects must be tracked in `## External` (`prepared -> sent -> confirmed | failed | response_unknown`) so interrupted sessions perform readback before retrying.

## 3. Shared task protocol and scenario matrix

Before a worker starts, the director specifies the product journey, existing decisions,
exact ownership/data/error contract, applicable states, affected callers and observable
acceptance. Reuse standard/native patterns before adding code. The approved session
pool selects a model and supported effort for that bounded job; no expensive fallback.

| Scenario | Required observation where applicable |
| --- | --- |
| First journey | UI action → real service/storage → readback; no mock presented as real acceptance |
| Loading/empty/failure | Visible state, meaningful copy, input preserved, retry/back/cancel works |
| Permission/authorization | Allowed actor/resource succeeds; denied actor cannot read/mutate |
| Double submit/concurrent retry | Exactly one effect or a documented conflict; pending UI remains usable |
| Lost response after commit | Readback resolves uncertainty before resend; persistence is not duplicated |
| Storage/network failure and restart | Data preserved, bounded retries/timeouts, recoverable state visible |
| Migration/schema evolution | Nonempty old data survives forward change and rollback/compatibility path |
| Visual/accessibility | Named compact/wide renders, long locale/text, keyboard/focus and platform targets |
| Agent interruption | Source/spec digests checked, Resume matches actual files, reserved jobs settled |
| Model/quota change | Excluded/changed route cannot launch; explicit approval and reserve checks hold |

Independent review checks each tick against its own current evidence and reports
BLOCKER/MAJOR/QUALITY gaps. Source review never substitutes for rendered or interaction
proof. When a capability is absent, record its concrete blocker rather than claiming
the scenario passed. This is an engineering protocol, not an AWS/cloud service or a
guarantee made from a checklist alone.
