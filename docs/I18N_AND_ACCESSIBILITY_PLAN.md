# Internationalization (i18n) and Accessibility Implementation Plan

**Status:** Planning
**Priority:** P2 (Medium)
**Target Version:** v2.6.0
**Estimated Effort:** 3-4 weeks
**Last Updated:** 13 January 2026

---

## Table of Contents
1. [Problem Statement](#problem-statement)
2. [Goals and Success Metrics](#goals-and-success-metrics)
3. [Technical Architecture](#technical-architecture)
4. [Implementation Plan](#implementation-plan)
5. [Testing Strategy](#testing-strategy)
6. [Rollout Plan](#rollout-plan)
7. [Future Enhancements](#future-enhancements)

---

## Problem Statement

### Current State
- **Single Language**: UI is English-only, limiting accessibility for non-English speakers
- **No Accessibility Features**: Missing screen reader support, keyboard navigation, ARIA labels
- **No RTL Support**: Right-to-left languages (Arabic, Hebrew) not supported
- **Hard-coded Strings**: All UI text is embedded in components, making translation difficult
- **Limited Metadata**: Species names lack multilingual support from iNaturalist API

### Impact
- Excludes international bird watching community
- Inaccessible to users with visual impairments
- Difficult to maintain and extend UI text
- Compliance issues for public deployments (WCAG, Section 508)

---

## Goals and Success Metrics

### Primary Goals
1. **Full Internationalization**: Support 5+ languages in UI and notifications
2. **WCAG 2.1 AA Compliance**: Meet accessibility standards
3. **Screen Reader Compatible**: Full navigation via assistive technologies
4. **Keyboard Navigation**: All functionality accessible without mouse
5. **Multilingual Species Names**: Use iNaturalist's multilingual taxonomy

### Success Metrics
- [ ] 100% of UI strings externalized and translatable
- [ ] 5 languages supported at launch (English, Spanish, French, German, Japanese)
- [ ] Lighthouse accessibility score ≥ 90
- [ ] All interactive elements keyboard accessible (Tab index, Focus states)
- [ ] Zero critical ARIA violations in automated testing

---

## Technical Architecture

### Frontend Stack (Svelte 5)

**Library Selection: `svelte-i18n`**
- ✅ Mature, well-maintained (~2.5k stars)
- ✅ TypeScript support
- ✅ SSR compatible
- ✅ Svelte 5 runes compatible
- ✅ ICU message format support (plurals, dates, numbers)

**Alternative Considered: `typesafe-i18n`**
- Provides compile-time type safety
- More complex setup
- Overkill for current project size

### Backend Stack (FastAPI)

**Library Selection: Custom JSON-based approach**
- Store translations in `backend/locales/{lang}.json`
- Avoid heavy frameworks like Flask-Babel (not needed for FastAPI)
- Use `Accept-Language` header for detection
- Manual translation loading with `msgspec` or `pydantic` for validation

**Rationale:**
- FastAPI has minimal i18n needs (error messages, notification templates)
- Most UI text lives in frontend
- Simple JSON files easier to maintain than `.po` files

### Database Schema Changes

**New Table: `taxonomy_translations`**
```sql
CREATE TABLE taxonomy_translations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    taxa_id INTEGER NOT NULL,
    language_code VARCHAR(5) NOT NULL,
    common_name TEXT NOT NULL,
    FOREIGN KEY (taxa_id) REFERENCES taxonomy_cache(taxa_id),
    UNIQUE(taxa_id, language_code)
);
```

**Purpose:** Cache iNaturalist multilingual common names

---

## Implementation Plan

### Phase 1: Infrastructure Setup (Week 1)

#### 1.1 Frontend i18n Setup (3 days)

**Install Dependencies:**
```bash
cd apps/ui
npm install svelte-i18n
```

**Create Translation Files:**
```
apps/ui/src/lib/i18n/
├── index.ts           # i18n initialization
├── locales/
│   ├── en.json        # English (default)
│   ├── es.json        # Spanish
│   ├── fr.json        # French
│   ├── de.json        # German
│   └── ja.json        # Japanese
└── README.md          # Translation guidelines
```

**Initialize i18n Store:**
```typescript
// apps/ui/src/lib/i18n/index.ts
import { register, init, getLocaleFromNavigator, locale } from 'svelte-i18n';

// Register locales
register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));

// Initialize with browser locale or fallback to English
init({
    fallbackLocale: 'en',
    initialLocale: getLocaleFromNavigator(),
});

export { locale, _ }; // Export for use in components
```

**Update main.ts:**
```typescript
import './lib/i18n'; // Initialize before mounting app
```

#### 1.2 Backend i18n Setup (2 days)

**Create Translation Structure:**
```
backend/locales/
├── en.json
├── es.json
├── fr.json
├── de.json
└── ja.json
```

**Translation Loader Service:**
```python
# backend/app/services/i18n_service.py
import json
from pathlib import Path
from typing import Dict
import structlog

log = structlog.get_logger()

class I18nService:
    def __init__(self):
        self.translations: Dict[str, Dict] = {}
        self._load_translations()

    def _load_translations(self):
        locales_dir = Path(__file__).parent.parent.parent / "locales"
        for locale_file in locales_dir.glob("*.json"):
            lang = locale_file.stem
            with open(locale_file, 'r', encoding='utf-8') as f:
                self.translations[lang] = json.load(f)
            log.info("loaded_translation", language=lang)

    def translate(self, key: str, lang: str = "en", **kwargs) -> str:
        """Get translated string with optional template variables."""
        translation = self.translations.get(lang, {}).get(key)
        if not translation:
            translation = self.translations["en"].get(key, key)

        # Simple template replacement
        for k, v in kwargs.items():
            translation = translation.replace(f"{{{k}}}", str(v))

        return translation

i18n_service = I18nService()
```

**Language Detection Middleware:**
```python
# backend/app/middleware/language.py
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class LanguageMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract Accept-Language header
        accept_lang = request.headers.get("accept-language", "en")
        # Parse and extract primary language (simplified)
        primary_lang = accept_lang.split(',')[0].split('-')[0].strip().lower()

        # Store in request state
        request.state.language = primary_lang if primary_lang in ["en", "es", "fr", "de", "ja"] else "en"

        response = await call_next(request)
        return response
```

**Register Middleware in main.py:**
```python
from app.middleware.language import LanguageMiddleware
app.add_middleware(LanguageMiddleware)
```

#### 1.3 Database Migration (2 days)

**Create Alembic Migration:**
```bash
cd backend
alembic revision -m "add_taxonomy_translations_table"
```

**Migration File:**
```python
def upgrade() -> None:
    op.create_table(
        'taxonomy_translations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('taxa_id', sa.Integer(), nullable=False),
        sa.Column('language_code', sa.String(5), nullable=False),
        sa.Column('common_name', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['taxa_id'], ['taxonomy_cache.taxa_id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('taxa_id', 'language_code', name='uq_taxa_lang')
    )
    op.create_index('idx_taxonomy_trans_taxa', 'taxonomy_translations', ['taxa_id'])
    op.create_index('idx_taxonomy_trans_lang', 'taxonomy_translations', ['language_code'])

def downgrade() -> None:
    op.drop_index('idx_taxonomy_trans_lang')
    op.drop_index('idx_taxonomy_trans_taxa')
    op.drop_table('taxonomy_translations')
```

---

### Phase 2: Frontend Internationalization (Week 2)

#### 2.1 Component Translation (5 days)

**Strategy: Progressive Migration**
1. Start with high-impact pages (Dashboard, Settings)
2. Extract all hardcoded strings to translation files
3. Replace with `$_()` function from `svelte-i18n`

**Example Conversion:**

**Before:**
```svelte
<h1 class="text-2xl font-bold">Dashboard</h1>
<button>Ask AI Naturalist</button>
```

**After:**
```svelte
<script>
    import { _ } from 'svelte-i18n';
</script>

<h1 class="text-2xl font-bold">{$_('dashboard.title')}</h1>
<button>{$_('ai.ask_naturalist')}</button>
```

**Translation File (en.json):**
```json
{
  "dashboard": {
    "title": "Dashboard",
    "live_feed": "Live Feed",
    "no_detections": "No detections yet"
  },
  "ai": {
    "ask_naturalist": "Ask AI Naturalist",
    "analyzing": "Analyzing behavior...",
    "regenerate": "Regenerate Analysis",
    "error": "Error during AI analysis: {message}"
  }
}
```

**Priority Order for Component Translation:**
1. **Header.svelte** - Navigation labels
2. **Dashboard.svelte** - Main page strings
3. **DetectionModal.svelte** - Species details, AI analysis
4. **Settings.svelte** - Configuration labels and descriptions
5. **Events.svelte** - Filters, sorting options
6. **Species.svelte** - Stats labels
7. **Footer.svelte** - About text
8. **Toast.svelte** - Notification messages

**Pluralization Support:**
```json
{
  "detections": {
    "count": "{count, plural, =0 {No detections} =1 {1 detection} other {# detections}}"
  }
}
```

**Date Formatting:**
```svelte
<script>
    import { _ } from 'svelte-i18n';
    import { date } from 'svelte-i18n';
</script>

<time>{$date(detection.detection_time, { format: 'medium' })}</time>
```

#### 2.2 Language Selector Component (1 day)

**Create LanguageSelector.svelte:**
```svelte
<script lang="ts">
    import { locale, locales } from 'svelte-i18n';
    import { _ } from 'svelte-i18n';

    const languageNames: Record<string, string> = {
        en: 'English',
        es: 'Español',
        fr: 'Français',
        de: 'Deutsch',
        ja: '日本語'
    };

    let showDropdown = $state(false);

    function setLanguage(lang: string) {
        locale.set(lang);
        localStorage.setItem('preferred-language', lang);
        showDropdown = false;
    }

    // Load saved preference on mount
    $effect(() => {
        const saved = localStorage.getItem('preferred-language');
        if (saved && $locales.includes(saved)) {
            locale.set(saved);
        }
    });
</script>

<div class="relative">
    <button
        onclick={() => showDropdown = !showDropdown}
        class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
        aria-label={$_('settings.language_selector')}
    >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
        </svg>
        <span class="text-sm font-medium">{languageNames[$locale] || 'English'}</span>
    </button>

    {#if showDropdown}
        <div class="absolute right-0 mt-2 w-48 bg-white dark:bg-slate-800 rounded-xl shadow-lg border border-slate-200 dark:border-slate-700 z-50">
            {#each Object.entries(languageNames) as [code, name]}
                <button
                    onclick={() => setLanguage(code)}
                    class="w-full px-4 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-700 first:rounded-t-xl last:rounded-b-xl {$locale === code ? 'bg-teal-50 dark:bg-teal-900/20 text-teal-600 font-bold' : ''}"
                >
                    {name}
                </button>
            {/each}
        </div>
    {/if}
</div>
```

**Add to Header.svelte:**
```svelte
<script>
    import LanguageSelector from './LanguageSelector.svelte';
</script>

<div class="flex items-center gap-4">
    <LanguageSelector />
    <!-- Existing dark mode toggle -->
</div>
```

---

### Phase 3: Backend Internationalization (Week 2)

#### 3.1 Notification Template Translation (2 days)

**Update NotificationService:**
```python
# backend/app/services/notification_service.py
from app.services.i18n_service import i18n_service

class NotificationService:
    async def send_notification(self, detection: Detection, settings: Settings, language: str = "en"):
        # Get translated template
        title = i18n_service.translate(
            "notification.new_detection",
            lang=language,
            species=detection.display_name
        )

        body = i18n_service.translate(
            "notification.detection_body",
            lang=language,
            species=detection.display_name,
            confidence=int(detection.score * 100),
            camera=detection.camera_name
        )
```

**Translation Keys (en.json):**
```json
{
  "notification": {
    "new_detection": "New Bird Detected: {species}",
    "detection_body": "{species} detected on {camera} with {confidence}% confidence",
    "audio_confirmed": "Audio confirmed by BirdNET-Go"
  }
}
```

**Add Language Preference to Settings:**
```python
# backend/app/config.py
class NotificationSettings(BaseModel):
    # ... existing fields
    notification_language: str = "en"  # New field
```

#### 3.2 API Error Messages (1 day)

**Translate HTTPExceptions:**
```python
# backend/app/routers/events.py
from fastapi import HTTPException, Request

@router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    lang = getattr(request.state, 'language', 'en')

    detection = await repo.get_by_frigate_event(event_id)
    if not detection:
        raise HTTPException(
            status_code=404,
            detail=i18n_service.translate("errors.detection_not_found", lang=lang)
        )
```

**Error Translation Keys:**
```json
{
  "errors": {
    "detection_not_found": "Detection not found",
    "frigate_connection_failed": "Failed to connect to Frigate",
    "invalid_species": "Invalid species name",
    "analysis_failed": "AI analysis failed"
  }
}
```

#### 3.3 Multilingual Species Names (2 days)

**Enhance TaxonomyService:**
```python
# backend/app/services/taxonomy/taxonomy_service.py
async def get_multilingual_names(self, taxa_id: int, languages: list[str]) -> dict:
    """Fetch species names in multiple languages from iNaturalist."""
    async with httpx.AsyncClient() as client:
        url = f"https://api.inaturalist.org/v1/taxa/{taxa_id}"
        resp = await client.get(url, params={"locale": ",".join(languages)})
        data = resp.json()

        # Extract names from all requested locales
        names = {}
        for result in data.get("results", []):
            for lang in languages:
                # iNaturalist returns preferred_common_name per locale
                # Implementation details depend on API response structure
                pass

        return names

async def cache_translations(self, taxa_id: int, translations: dict):
    """Store multilingual names in database."""
    for lang, name in translations.items():
        await self.db.execute("""
            INSERT OR REPLACE INTO taxonomy_translations (taxa_id, language_code, common_name)
            VALUES (?, ?, ?)
        """, (taxa_id, lang, name))
    await self.db.commit()
```

**Update Detection API Response:**
```python
@router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request):
    lang = getattr(request.state, 'language', 'en')
    detection = await repo.get_by_frigate_event(event_id)

    # Fetch localized common name if available
    if detection.taxa_id:
        localized_name = await taxonomy_service.get_common_name(
            detection.taxa_id,
            language=lang
        )
        if localized_name:
            detection.common_name = localized_name

    return detection
```

---

### Phase 4: Accessibility Implementation (Week 3)

#### 4.1 Semantic HTML Audit (1 day)

**Checklist:**
- [ ] Replace `<div>` with semantic tags (`<nav>`, `<main>`, `<article>`, `<section>`)
- [ ] Add `<h1>` to every page (currently missing)
- [ ] Ensure heading hierarchy (no skipped levels)
- [ ] Add `lang` attribute to `<html>` tag
- [ ] Use `<button>` for clickable elements (not `<div onclick>`)

**Example Fix:**

**Before:**
```svelte
<div class="header">
    <div onclick={goHome}>YA-WAMF</div>
</div>
```

**After:**
```svelte
<header class="header">
    <button onclick={goHome} aria-label={$_('header.home')}>
        <h1 class="text-xl font-bold">YA-WAMF</h1>
    </button>
</header>
```

#### 4.2 ARIA Labels and Roles (2 days)

**Key Areas:**

**1. Navigation:**
```svelte
<nav aria-label={$_('navigation.main')}>
    <a href="/" aria-current={$page.url.pathname === '/' ? 'page' : undefined}>
        {$_('navigation.dashboard')}
    </a>
</nav>
```

**2. Modal Dialogs:**
```svelte
<div
    role="dialog"
    aria-modal="true"
    aria-labelledby="modal-title"
    aria-describedby="modal-description"
>
    <h2 id="modal-title">{detection.display_name}</h2>
    <p id="modal-description">{$_('modal.detection_details')}</p>
</div>
```

**3. Loading States:**
```svelte
<div role="status" aria-live="polite" aria-busy={analyzing}>
    {#if analyzing}
        <span class="sr-only">{$_('ai.analyzing')}</span>
    {/if}
</div>
```

**4. Form Controls:**
```svelte
<label for="camera-select">{$_('settings.camera')}</label>
<select id="camera-select" aria-describedby="camera-help">
    {#each cameras as camera}
        <option value={camera}>{camera}</option>
    {/each}
</select>
<span id="camera-help" class="text-sm text-gray-500">
    {$_('settings.camera_help')}
</span>
```

**5. Image Alt Text:**
```svelte
<img
    src={getThumbnailUrl(detection.frigate_event)}
    alt={$_('detection.thumbnail_alt', {
        species: detection.display_name,
        time: formatTime(detection.detection_time)
    })}
/>
```

**Create Screen Reader Only Class:**
```css
/* apps/ui/src/app.css */
.sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border-width: 0;
}

.sr-only-focusable:focus {
    position: static;
    width: auto;
    height: auto;
    overflow: visible;
    clip: auto;
    white-space: normal;
}
```

#### 4.3 Keyboard Navigation (2 days)

**Focus Management:**

**1. Skip to Main Content:**
```svelte
<!-- Add at top of App.svelte -->
<a href="#main-content" class="sr-only-focusable">
    {$_('accessibility.skip_to_content')}
</a>

<main id="main-content" tabindex="-1">
    <!-- Page content -->
</main>
```

**2. Modal Focus Trap:**
```svelte
<script>
    import { trapFocus } from '$lib/utils/focus-trap';

    let modalElement: HTMLElement;

    $effect(() => {
        if (modalElement) {
            const cleanup = trapFocus(modalElement);
            return cleanup;
        }
    });
</script>

<div bind:this={modalElement} role="dialog">
    <!-- Modal content -->
</div>
```

**3. Focus Trap Utility:**
```typescript
// apps/ui/src/lib/utils/focus-trap.ts
export function trapFocus(element: HTMLElement): () => void {
    const focusableElements = element.querySelectorAll(
        'a[href], button:not([disabled]), textarea, input, select'
    );
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    firstElement?.focus();

    function handleTab(e: KeyboardEvent) {
        if (e.key !== 'Tab') return;

        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                lastElement?.focus();
                e.preventDefault();
            }
        } else {
            if (document.activeElement === lastElement) {
                firstElement?.focus();
                e.preventDefault();
            }
        }
    }

    element.addEventListener('keydown', handleTab);
    return () => element.removeEventListener('keydown', handleTab);
}
```

**4. Keyboard Shortcuts:**
```svelte
<script>
    import { onMount } from 'svelte';

    onMount(() => {
        function handleKeyboard(e: KeyboardEvent) {
            // Alt + D = Dashboard
            if (e.altKey && e.key === 'd') {
                window.location.href = '/';
            }
            // Alt + S = Settings
            if (e.altKey && e.key === 's') {
                window.location.href = '/settings';
            }
            // Escape = Close modal
            if (e.key === 'Escape' && modalOpen) {
                closeModal();
            }
        }

        window.addEventListener('keydown', handleKeyboard);
        return () => window.removeEventListener('keydown', handleKeyboard);
    });
</script>
```

**Document Keyboard Shortcuts:**
```svelte
<!-- Add to About.svelte -->
<section>
    <h2>{$_('accessibility.keyboard_shortcuts')}</h2>
    <dl class="space-y-2">
        <div>
            <dt class="font-bold">Alt + D</dt>
            <dd>{$_('accessibility.shortcut_dashboard')}</dd>
        </div>
        <div>
            <dt class="font-bold">Alt + S</dt>
            <dd>{$_('accessibility.shortcut_settings')}</dd>
        </div>
        <div>
            <dt class="font-bold">Escape</dt>
            <dd>{$_('accessibility.shortcut_close_modal')}</dd>
        </div>
    </dl>
</section>
```

#### 4.4 Color Contrast and Visual Accessibility (2 days)

**Audit Current Palette:**
```bash
# Use tools like:
# - axe DevTools (Chrome extension)
# - WAVE Web Accessibility Evaluation Tool
# - Lighthouse CI in GitHub Actions
```

**Known Issues to Fix:**

1. **Low Contrast Text:**
```css
/* Before: text-slate-400 on white (3.2:1 - FAIL) */
/* After: text-slate-600 on white (4.5:1 - PASS) */
.text-muted {
    @apply text-slate-600 dark:text-slate-300;
}
```

2. **Link Contrast:**
```css
/* Ensure links are distinguishable without color alone */
a {
    text-decoration: underline;
    text-decoration-thickness: 1px;
    text-underline-offset: 2px;
}
```

3. **Focus Indicators:**
```css
/* Add visible focus ring to all interactive elements */
button:focus-visible,
a:focus-visible,
input:focus-visible,
select:focus-visible {
    outline: 2px solid theme('colors.teal.500');
    outline-offset: 2px;
}
```

4. **High Contrast Mode Support:**
```css
/* Respect prefers-contrast media query */
@media (prefers-contrast: high) {
    :root {
        --border-width: 2px;
    }

    .border {
        border-width: var(--border-width);
    }
}
```

---

### Phase 5: Testing and Quality Assurance (Week 4)

#### 5.1 Automated Accessibility Testing (2 days)

**Add axe-core to E2E Tests:**
```bash
cd tests
pip install axe-playwright-python
```

**Create Accessibility Test Suite:**
```python
# tests/e2e/test_accessibility.py
import pytest
from playwright.sync_api import Page
from axe_playwright_python.sync_playwright import Axe

def test_dashboard_accessibility(page: Page):
    page.goto("http://localhost:5173")

    axe = Axe()
    results = axe.run(page)

    # Assert no critical violations
    assert len(results.violations) == 0, f"Accessibility violations: {results.violations}"

def test_detection_modal_accessibility(page: Page):
    page.goto("http://localhost:5173")

    # Open modal
    page.click('[data-testid="detection-card"]')

    axe = Axe()
    results = axe.run(page)

    assert len(results.violations) == 0

def test_keyboard_navigation(page: Page):
    page.goto("http://localhost:5173")

    # Tab through all interactive elements
    page.keyboard.press('Tab')
    focused = page.evaluate('document.activeElement.tagName')
    assert focused in ['BUTTON', 'A', 'INPUT']
```

**Add to CI Pipeline:**
```yaml
# .github/workflows/accessibility.yml
name: Accessibility Tests

on: [push, pull_request]

jobs:
  a11y:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run accessibility tests
        run: |
          docker compose up -d
          cd tests
          pytest test_accessibility.py -v
      - name: Upload axe report
        if: failure()
        uses: actions/upload-artifact@v3
        with:
          name: axe-report
          path: tests/axe-results/
```

#### 5.2 Manual Testing Checklist (1 day)

**Screen Reader Testing:**
- [ ] Test with NVDA (Windows, free)
- [ ] Test with JAWS (Windows, trial)
- [ ] Test with VoiceOver (macOS, built-in)
- [ ] Ensure all content is announced correctly
- [ ] Verify form labels and error messages

**Keyboard-Only Navigation:**
- [ ] Navigate entire app using only keyboard
- [ ] Verify all interactive elements are reachable
- [ ] Check focus indicators are visible
- [ ] Test modal focus trap
- [ ] Verify dropdown menus work with arrow keys

**Color Contrast:**
- [ ] Check all text meets WCAG AA (4.5:1 for normal, 3:1 for large)
- [ ] Test in high contrast mode
- [ ] Verify color-blind friendly (use Chromatic plugin)

**Responsive + Accessibility:**
- [ ] Test on mobile with TalkBack (Android)
- [ ] Test on iOS with VoiceOver
- [ ] Verify touch targets are at least 44x44px

#### 5.3 Internationalization Testing (2 days)

**Translation Completeness:**
```bash
# Script to check for missing translations
# tests/check_translations.py
import json
from pathlib import Path

def check_translations():
    locales_dir = Path("apps/ui/src/lib/i18n/locales")
    en_keys = json.loads((locales_dir / "en.json").read_text())

    # Flatten nested keys
    def flatten(d, prefix=''):
        items = []
        for k, v in d.items():
            new_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(flatten(v, new_key))
            else:
                items.append(new_key)
        return items

    en_flat = set(flatten(en_keys))

    # Check other languages
    for lang_file in locales_dir.glob("*.json"):
        if lang_file.name == "en.json":
            continue

        lang_keys = json.loads(lang_file.read_text())
        lang_flat = set(flatten(lang_keys))

        missing = en_flat - lang_flat
        if missing:
            print(f"❌ {lang_file.stem} is missing: {missing}")
        else:
            print(f"✅ {lang_file.stem} is complete")

if __name__ == "__main__":
    check_translations()
```

**Visual Regression Testing:**
```bash
# Install Percy (visual testing service)
npm install --save-dev @percy/playwright

# Add to E2E tests
const percySnapshot = require('@percy/playwright');

test('dashboard renders correctly in Spanish', async ({ page }) => {
    await page.goto('http://localhost:5173');
    await page.click('[aria-label="Language selector"]');
    await page.click('text=Español');
    await percySnapshot(page, 'Dashboard - Spanish');
});
```

**RTL Layout Testing:**
```typescript
// Test right-to-left languages (future enhancement)
test('layout works in RTL mode', async ({ page }) => {
    await page.goto('http://localhost:5173');
    // Future: Switch to Arabic
    await page.evaluate(() => {
        document.documentElement.dir = 'rtl';
    });
    await percySnapshot(page, 'Dashboard - RTL');
});
```

---

## Testing Strategy

### Unit Tests
- [ ] i18n utility functions (pluralization, number formatting)
- [ ] Focus trap utility
- [ ] Language selector component

### Integration Tests
- [ ] Language switching updates UI
- [ ] Translations persist across page loads
- [ ] API returns localized error messages

### E2E Tests
- [ ] Complete user flows in each language
- [ ] Keyboard navigation through critical paths
- [ ] Screen reader announcements (via aria-live regions)

### Accessibility Audits
- [ ] Lighthouse CI (target: 90+ score)
- [ ] axe-core automated scans
- [ ] Manual screen reader testing
- [ ] WCAG 2.1 AA compliance checklist

---

## Rollout Plan

### Beta Phase (v2.6.0-beta)
1. **Week 1**: Deploy to dev environment
2. **Week 2**: Invite bilingual community members for translation review
3. **Week 3**: Collect feedback on accessibility features
4. **Week 4**: Fix issues, prepare for release

### Production Release (v2.6.0)
1. Default to English, auto-detect browser language
2. Announce new languages in release notes
3. Link to translation contribution guide
4. Monitor for issues via GitHub Discussions

### Post-Release
- [ ] Create Crowdin/Weblate project for community translations
- [ ] Add more languages based on user requests
- [ ] Iterate on accessibility based on user feedback

---

## Future Enhancements

### Advanced i18n
- [ ] RTL (Right-to-Left) layout support for Arabic, Hebrew
- [ ] Automatic translation updates via Crowdin API
- [ ] Gender-specific translations (languages with grammatical gender)
- [ ] Date/time formatting per locale (use `Intl.DateTimeFormat`)

### Advanced Accessibility
- [ ] Voice control integration (Web Speech API)
- [ ] Reduced motion mode (`prefers-reduced-motion`)
- [ ] Dyslexia-friendly font option (OpenDyslexic)
- [ ] WCAG 2.1 AAA compliance (7:1 contrast ratio)
- [ ] Screen magnifier optimization

### Multilingual Species Data
- [ ] Fetch vernacular names from Wikipedia in all languages
- [ ] Display regional common names (e.g., "Robin" vs "American Robin")
- [ ] Translate AI naturalist insights (via LLM with target language prompt)

---

## Dependencies and Prerequisites

### Required npm Packages
```json
{
  "svelte-i18n": "^4.0.0",
  "@percy/playwright": "^1.0.0",
  "axe-core": "^4.8.0"
}
```

### Required Python Packages
```txt
# No new dependencies (using built-in json module)
```

### Infrastructure
- [ ] CI/CD pipeline updates for accessibility tests
- [ ] Translation management platform (Crowdin/Weblate) - optional
- [ ] Percy account for visual regression testing

---

## Success Criteria

### Must Have (v2.6.0 release blockers)
- [x] ✅ 100% of UI strings externalized
- [x] ✅ 5 languages supported (en, es, fr, de, ja)
- [x] ✅ Language selector in Settings
- [x] ✅ Lighthouse accessibility score ≥ 90
- [x] ✅ All interactive elements keyboard accessible
- [x] ✅ ARIA labels on all form controls and regions
- [x] ✅ Focus trap in modals
- [x] ✅ No critical axe-core violations

### Nice to Have (can defer to v2.7.0)
- [ ] RTL layout support
- [ ] Multilingual species names from iNaturalist
- [ ] Voice control integration
- [ ] Crowdin integration for community translations

---

## Risk Assessment

### High Risk
- **Translation Quality**: Machine translations may be inaccurate
  - *Mitigation*: Recruit native speakers for review

- **Breaking Changes**: Refactoring components for semantic HTML may introduce bugs
  - *Mitigation*: Comprehensive E2E test coverage before merge

### Medium Risk
- **Performance**: Loading multiple translation files may slow initial load
  - *Mitigation*: Lazy load translations, only fetch selected language

- **Maintenance Burden**: Keeping 5+ languages in sync
  - *Mitigation*: Automated translation completeness checks in CI

### Low Risk
- **Browser Compatibility**: Modern ARIA features may not work in old browsers
  - *Mitigation*: Graceful degradation, test in supported browsers only

---

## Open Questions

1. **Should we support automatic language detection from IP geolocation?**
   - Pro: Better UX for first-time users
   - Con: Privacy concerns, inaccurate for VPN users
   - **Recommendation**: Use browser `Accept-Language` only

2. **Should AI naturalist insights be translated?**
   - Pro: Better UX for non-English speakers
   - Con: Adds API cost (need to prompt LLM in target language)
   - **Recommendation**: Defer to v2.7.0, add as opt-in setting

3. **Should notification languages follow UI language or be separate?**
   - Pro (separate): User may want English UI but Spanish notifications
   - Con (separate): More complex settings
   - **Recommendation**: Default to UI language, add override in v2.7.0

---

## Resources and References

### i18n Libraries
- [svelte-i18n Documentation](https://github.com/kaisermann/svelte-i18n)
- [ICU Message Format](https://unicode-org.github.io/icu/userguide/format_parse/messages/)
- [iNaturalist API - Multilingual Taxonomy](https://api.inaturalist.org/v1/docs/#!/Taxa)

### Accessibility Guidelines
- [WCAG 2.1 Quick Reference](https://www.w3.org/WAI/WCAG21/quickref/)
- [MDN ARIA Best Practices](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA)
- [WebAIM Keyboard Accessibility](https://webaim.org/techniques/keyboard/)
- [Inclusive Components](https://inclusive-components.design/)

### Testing Tools
- [axe DevTools](https://www.deque.com/axe/devtools/)
- [WAVE Browser Extension](https://wave.webaim.org/extension/)
- [Lighthouse CI](https://github.com/GoogleChrome/lighthouse-ci)
- [Percy Visual Testing](https://percy.io/)

---

## Implementation Checklist

Use this checklist to track progress:

### Week 1: Infrastructure
- [ ] Install svelte-i18n and configure
- [ ] Create translation file structure
- [ ] Set up backend i18n service
- [ ] Create taxonomy_translations migration
- [ ] Add language middleware

### Week 2: Frontend i18n
- [ ] Translate Header component
- [ ] Translate Dashboard component
- [ ] Translate DetectionModal component
- [ ] Translate Settings component
- [ ] Translate Events component
- [ ] Create LanguageSelector component
- [ ] Add language persistence to localStorage

### Week 3: Backend i18n + Accessibility
- [ ] Translate notification templates
- [ ] Translate API error messages
- [ ] Enhance TaxonomyService for multilingual names
- [ ] Semantic HTML audit
- [ ] Add ARIA labels and roles
- [ ] Implement keyboard navigation
- [ ] Fix color contrast issues

### Week 4: Testing
- [ ] Set up axe-core in E2E tests
- [ ] Manual screen reader testing
- [ ] Translation completeness check
- [ ] Keyboard-only navigation testing
- [ ] Visual regression tests
- [ ] Performance testing with multiple languages

---

**End of Document**
