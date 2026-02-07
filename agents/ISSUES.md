# Issues - YA-WAMF (Agents)

This document tracks unresolved issues discovered during AI-assisted development. These should be treated as **P0/P1** until resolved, and must appear at the top of the roadmap.

---

## 🔴 P0 - AI Analysis Formatting & Contrast (Detection Modal)

**Status:** Open (not fixed)

### Summary
The AI analysis panel and follow-up conversation bubbles in the Detection Modal are still inconsistent in formatting and contrast. The initial AI analysis often renders with uniform bright text (losing hierarchy), while the conversation reply bubble appears with darker text and inconsistent heading treatment. The result looks flat, hard to scan, and visually inconsistent between the analysis and conversation threads.

### Evidence
- Screenshot: `agents/Screenshot_20260207_121427.png`
  - **Observed:**
    - Assistant response in conversation is darker and low-contrast compared to the main AI analysis panel.
    - Section headers such as “Seasonal Context” are not styled as headings in the assistant bubble.
    - List structure is inconsistent (paragraph-like blocks instead of bullets).
- Historical context: earlier dark-mode AI analysis contrast issues were partially addressed but still not resolved consistently across all markdown rendering surfaces.

### Expected
- **Consistent Markdown rendering** between the analysis panel and conversation bubbles.
- **Headers should render as headings** (e.g., `## Appearance`, `## Behavior`) with clear visual hierarchy.
- **Bullet lists should render as lists** with consistent spacing.
- **Contrast should match dark-mode defaults** for other UI text (off-white, readable, not gray).

### Current Behavior
- Main AI analysis panel appears uniformly white, losing heading emphasis.
- Conversation assistant bubble displays darker, low-contrast text.
- Headings are inconsistently parsed or not recognized in conversation replies.

### Likely Root Causes (Hypotheses)
1. **Markdown normalization gap:** conversational output often lacks explicit Markdown headings, so parsing falls back to plain paragraphs.
2. **Styling scope mismatch:** `.ai-markdown` styles may apply to the analysis panel but not to conversation bubble content, or bubble styling overrides text color.
3. **Contrast override missing:** assistant bubble background is darker, but text color is not explicitly set to bright, causing low contrast.
4. **Prompt structure drift:** system prompts for analysis and conversation are not aligned, leading to inconsistent format even if renderer is correct.

### Prior Attempts
- Added global markdown styling for `.ai-markdown`.
- Added `markdown-it` rendering with normalization pass.
- Added prompt templates with localized styles and a debug editor.

### Remaining Gaps
- Need a **single formatting pipeline** that guarantees heading + bullet structure in both analysis and conversation outputs.
- Need **explicit contrast enforcement** for assistant bubble text in dark mode.
- Need **prompt alignment** (analysis + conversation use identical section structure).

### Next Steps
- Add a deterministic markdown schema for both analysis + conversation prompts (identical headings + bullet rules).
- Add a visual regression snapshot for `DetectionModal` in dark + light mode to catch contrast drift.
- Ensure `.ai-bubble__content` inherits text color from the bubble surface and remove any global `text-slate-*` overrides.
- Add a test fixture that includes headings, lists, blockquotes, code, and tables to validate markdown rendering consistency.

### Diagnostics Tooling (AI Styling)
- Detection modal now includes an **AI Diagnostics** panel with one-click **Copy All** that copies:
  - computed styles (text colors, backgrounds, borders),
  - root/body classes,
  - markdown element counts + sample styles,
  - raw AI analysis + latest assistant reply,
  - active prompt templates.
- Use this to capture a full bundle when reporting formatting/contrast issues.

### Acceptance Criteria
- Conversation replies render with the same headings and bullet structure as analysis panel.
- Assistant bubble text contrast is readable in dark mode (off-white, not gray).
- Headings are visually distinct (size/weight/letter-spacing) and consistent across both areas.
- Regression test: screenshots in both dark + light themes show consistent formatting.

---

## Notes
If new formatting issues are found, add them here and ensure they are promoted above feature work in the roadmap.
