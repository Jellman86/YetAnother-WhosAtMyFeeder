# Implementation Plan: Dashboard UI Overhaul

## Overview
Differentiate the Dashboard from the Events Explorer by focusing on real-time activity, daily trends, and unique species summaries, inspired by BirdNET-Go.

## Phase 1: Component Refactor
- [ ] **The "Hero" Detection**: A large, prominent section at the top showing the absolute latest detection with full metadata (Temp, Confidence, Audio source).
- [ ] **Activity Histogram (The "Pulse")**: An SVG-based bar chart showing detection frequency over the last 24 hours to visualize peak feeding times.
- [ ] **"Top Visitors" Summary**: A grid of unique species seen today, showing a thumbnail and total visit count per species.
- [ ] **Live discovery ticker**: A vertical sidebar or scrolling list for incoming visual and audio detections.

## Phase 2: Backend Support
- [ ] **Summary API**: Create `GET /api/stats/daily-summary` to provide:
    - Hourly detection distribution (for histogram).
    - Top unique species counts for today.
    - Latest single detection details.

## Phase 3: Visual Polish & Real-time
- [ ] **Live Indicator**: A glowing status light for active SSE connections.
- [ ] **Listening State**: A pulse animation visible when BirdNET-Go is actively feeding data.
- [ ] **Transitions**: Smooth Svelte transitions when the Hero detection updates.
