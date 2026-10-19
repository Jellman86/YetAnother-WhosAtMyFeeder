# Storage measurements through short requests

## Evidence and requirements

The #755 follow-up reports an error after about a minute and success on Retry.
The previous UI allowed 120 seconds, but that is only its own deadline; a proxy
can close a long request earlier. The diagnostics do not establish which timeout
occurred on the reporter's host. The filesystem walk is already off the event
loop and coalesced, but its HTTP response waits until the walk finishes.

A controlled pending collector reproduces the mechanism: the legacy stats request
stays pending while the new measurement endpoint immediately returns progress.
This is not a reproduction of the reporter's exact proxy configuration.

Required behavior: no missing-as-zero figure, one in-flight storage scan, short
owner-only requests, stable polling ids, recoverable process restart, bounded
client polling and server result retention, and no detection/media/settings writes.

## Design

`GET /api/cache/measurement` starts or joins one process-local measurement and
returns its status immediately. Polling by id retrieves that measurement even if
another client has since started a newer one. The server retains at most 16
records, retrieves abandoned task exceptions, and reports a generic failure while
logging only the exception type and measurement id. Owner authorization and
`no-store` apply to each request. The existing blocking endpoint remains compatible.

The UI uses requests bounded to ten seconds and polls every two seconds for at
most ten minutes. Calls in one tab share a promise; the backend also joins callers
across tabs. A pending id survives transport errors and the client polling deadline,
so Retry checks that scan's result. One expired-id recovery starts a new measurement
without an unbounded 404 loop. A completed or failed measurement releases the id
so a later explicit refresh can measure again.

## Second-order effects and limits

- A storage mount can remain slow or stuck. Polling keeps the API responsive but
  does not repair the mount or forcibly cancel an operating-system file read.
- The existing shared worker-thread walk remains the only filesystem traversal.
  Background collection holds its short database read separately from that walk.
- Completed measurements are historical samples, not atomic filesystem snapshots.
  An earlier displayed value stays visible while refreshing or after failure.
- Restart loses process-local results. A bounded restart recovery obtains a new id;
  older clients can keep using the unchanged blocking endpoint.
- Polls add small authenticated requests, bounded in duration and count. They do
  not load a model, replay MQTT, classify events or write application history.
- Read-only API collection may finish after a tab leaves. At most one scan remains
  active, and its retained result/task state is bounded.

Tests cover pending/shared/completed/failed and evicted results, missing ids without
new I/O, owner authorization, the old blocking versus new short request, same-tab
coalescing, expired-id recovery, a ten-minute client bound and retry continuity.
The actual Settings-page browser tests cover progress plus success/failure.
Full regression gates and external review are recorded with the delivering PR.
Rollback restores the previous UI request path and removes the additive endpoint;
there are no schema or data changes to undo.
