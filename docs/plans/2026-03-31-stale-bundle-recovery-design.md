# Stale Bundle Recovery Design

This design hardens the frontend against deploy-time stale-tab failures like the issue `#33` bundle: the browser keeps an older app shell open, the backend restarts onto a newer build, hashed JS assets disappear, and the tab gets stuck showing stale UI state.

Recommended approach:

1. Add a small deploy-recovery helper in the UI runtime layer.
2. Classify only deploy-like failures:
   - dynamic import / chunk-load failures
   - backend/frontend version mismatch observed through owner health checks
3. On the first matching signal for a given version signature, perform a guarded one-shot reload.
4. Persist the attempted signature in `sessionStorage` so the same stale-tab condition cannot cause a reload loop.
5. If the same condition is seen again after that guarded reload, stop reloading and show a warning toast instead.

Why this approach:

- It directly addresses the failure mode seen in issue `#33` instead of treating all runtime errors as deploy issues.
- It stays local to the app shell and does not require backend API changes.
- It avoids the biggest second-order risk, reload loops, by keying attempts to the actual version/failure signature.
- It composes cleanly with the existing service-worker/controller refresh path in `src/main.ts`.

Guardrails:

- Do not reload on generic runtime exceptions.
- Do not clear or mutate unrelated UI state from this helper.
- When a backend version mismatch resolves, normal app behavior resumes without extra banners.
- If the browser still hits the same stale-bundle condition after one forced reload, show a warning toast and leave control to the user.
