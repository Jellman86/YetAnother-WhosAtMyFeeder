# Code-quality standard

The researched code-craft bar for YA-WAMF's stack. This is the depth behind
[`CLAUDE.md`](../../CLAUDE.md) §4 — `CLAUDE.md` carries the enforceable rules; this page
carries the reasoning and the full checklist the file-by-file code-quality review works
against. When this page and `CLAUDE.md` disagree, `CLAUDE.md` wins.

It is grounded in the authoritative sources listed at the [end](#references).

---

## Python & FastAPI (backend)

**Style & formatting.** PEP 8, enforced by **Ruff** (`ruff check` + `ruff format`) in CI —
never hand-format. Line length, imports, and layout are the linter's job, not review's.

**Typing.** Type hints on every function signature and attribute (PEP 484). Pydantic models
for all request/response DTOs. Prefer precise types over `dict`/`Any`; a public function's
signature should document its contract.

**Async & the event loop.** `async def` for all I/O. Never run blocking calls on the event
loop — no bare `open()`, `requests`, `time.sleep`, or synchronous DB drivers; use `aiofiles`,
`httpx`, and async SQLAlchemy. Push CPU-heavy work to an executor. Small non-I/O helpers may
still be `async` to avoid the threadpool overhead FastAPI incurs for sync dependencies.

**Layering & dependency direction.** `routers → services → repositories → SQLite`, one
direction only (mirrors [`CLAUDE.md`](../../CLAUDE.md) §8):
- **Routers** compose HTTP: parse/validate input, call a service, shape the response. No
  business rules, no raw SQLAlchemy.
- **Services** hold domain logic and orchestration. Business rules that can be pure should be
  pure and unit-tested without a DB, network, or model (see `CLAUDE.md` §2).
- **Repositories** own all data access behind an async API; read paths paginate.

**Dependency injection.** Use FastAPI `Depends` for DB sessions, auth context, and settings so
handlers stay decoupled and testable. Don't reach for globals where a dependency fits.

**API contract.** Every endpoint declares a `response_model` so the OpenAPI artifact carries a
real shape (not `unknown`); the generated SPA types depend on it. Raise `HTTPException` with a
clear `detail`. All external input is untrusted — validate it (`CLAUDE.md` §1). The one honest
exception: open-ended diagnostic payloads (e.g. the model-eval run JSON) may return `dict` by
design rather than forcing a brittle model.

**Errors & logging.** Structured logging via `structlog` with context
(`log.info("event", event_id=id)`); never bare `print`, never secrets. Fail conservative — when
in doubt, do nothing and report why (`CLAUDE.md` §1).

**Hygiene.** Small, single-purpose functions; names that carry intent; comments explain *why*,
not *what*. No dead code, commented-out blocks, or `TODO` without a linked issue.

## TypeScript (frontend)

**Strictness.** `strict: true` (all strict flags: `strictNullChecks`, `noImplicitAny`, …). Add
`noUncheckedIndexedAccess` and `exactOptionalPropertyTypes` where practical. `svelte-check` runs
clean — **zero errors, zero warnings** — before commit.

**No `any` in application code.** Prefer `unknown` at untrusted boundaries and narrow before use.
If `any` is genuinely unavoidable, leave a comment explaining why. Avoid non-null assertions
(`!`) — narrow the type instead. Give exported/public functions explicit return types.

**Types come from the contract.** SPA request/response types are derived from the generated
OpenAPI contract (`apps/ui/src/lib/api/generated/`), not hand-written DTOs, so backend/frontend
drift fails CI. All network access goes through `apps/ui/src/lib/api/` — never inline `fetch`.

## Svelte 5 (frontend)

**Reactivity discipline** — the single most important rule, per the official Svelte guidance:
- **Reach for `$derived` before `$effect`.** Computed state is `$derived`; its expression must
  be side-effect free.
- **`$effect` is an escape hatch, not a default.** Use it only to synchronize with systems
  *outside* Svelte's reactivity (third-party libraries, canvas, manual DOM, subscriptions).
  **Never** use an effect to sync one piece of state to another, and avoid setting state inside
  effects — that's what `$derived` is for.
- **Mark reactive only what drives the view.** Use `$state` for values a template, `$derived`,
  or `$effect` depends on; everything else is a plain variable.
- **Use `$state.raw`** for large objects that are only ever reassigned (e.g. API responses) to
  skip deep-proxy overhead.

**Modern idioms.** Events as `onclick={…}` (not `on:click`). User-facing strings go through
`svelte-i18n` with `{ default: '…' }` fallbacks.

---

## References

- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/) · [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)
- [Ruff](https://docs.astral.sh/ruff/)
- [FastAPI documentation](https://fastapi.tiangolo.com/) · [zhanymkanov/fastapi-best-practices](https://github.com/zhanymkanov/fastapi-best-practices)
- [TypeScript `strict` compiler option](https://www.typescriptlang.org/tsconfig/strict.html)
- [Svelte — Best practices](https://svelte.dev/docs/svelte/best-practices) · [Svelte 5 runes](https://svelte.dev/docs/svelte/what-are-runes)
