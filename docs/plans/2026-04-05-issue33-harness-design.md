# Issue 33 Harness Refresh Design

## Goal
Make the `#33` soak harness reflect the current issue shape so a failed run indicates a real regression, not a stale BirdNET counter assumption.

## Problem
The current harness still hard-fails on BirdNET message-count growth. On current builds, `mqtt.topic_message_counts.birdnet` can reset or roll during reconnect/liveness recovery, so a healthy run can report a negative BirdNET delta even while BirdNET remains active and the backend behaves correctly.

## Recommended Approach
Keep the synthetic BirdNET publisher, but stop treating raw BirdNET count delta as a hard failure for `#33`.

Instead, issue-33-specific evaluation should require:
- the synthetic BirdNET publisher actually published successfully
- BirdNET remained fresh during the induced Frigate-stall window
- existing `#33` checks still hold: reconnect growth, no stall incidents, no video breaker opening, no video-failure growth, and no pending backlog explosion

## Behavior
- The shared issue-22 evaluator stays unchanged.
- The issue-33 script normalizes the generic evaluation and replaces the stale BirdNET-delta gate with a stall-window liveness check.
- Summary output should include BirdNET liveness facts so failures are easy to interpret.

## Non-Goals
- No MQTT backend changes.
- No classifier changes.
- No change to the synthetic publisher model itself.
