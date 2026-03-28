# Manual Tag Full-Visit Preserve Design

## Goal

Keep full-visit clip readiness tied to the Frigate event instead of the species label, so manual renames do not re-offer a redundant full-visit fetch.

## Approach

The persisted full-visit file is event-based and should remain valid across manual tag changes. The frontend should therefore refresh or preserve full-visit state by `frigate_event` after manual tag updates instead of treating the renamed detection like a new fetch candidate.

The smallest safe fix is:
- add an explicit refresh path in the full-visit store for event-based availability rechecks
- call that refresh after manual tag updates
- keep the cached filename and backend storage keyed by event ID only

## Scope

- Frontend full-visit store
- Manual tag flows in Events and Dashboard
- Regression tests
- Changelog update

## Non-Goals

- Renaming persisted clip files
- Changing backend clip storage keys
- Reworking full-visit generation logic
