# Storage measurement retry feedback

Issue #755's follow-up says Retry usually succeeds, but the error remains visible
while it runs. The Settings page only cleared its error after a successful
response, so it gave no indication that Retry had started.

The page now clears the old error and marks the measurement loading before
awaiting the API. The storage row announces “Measuring…” through a status element,
retains any earlier figure, and offers Retry again on failure. A loading guard
prevents concurrent client measurements; success and failure both release it in
`finally`. The Retry control uses the shared button style and touch-target size.

The browser regression exercises the real Settings page with mocked API responses:
an initial gateway error, a deliberately pending retry, and both successful and
failed retry outcomes. The original page failed the pending-state assertion.
No production requests or settings writes are involved in this fixture.

This changes feedback, not storage measurement performance. The API's existing
two-minute client timeout and shared background filesystem walk are unchanged.
The reporter's one-minute failure may involve a proxy or another timeout; the
attachment alone does not establish that cause. A new failure still needs request
and proxy timing evidence. Earlier measurements remain historical values while a
refresh is pending or fails, and no missing result becomes a false zero.
