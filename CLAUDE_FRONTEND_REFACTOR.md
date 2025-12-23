# Claude Frontend Refactoring Instructions

## Task Overview
Refactor the YA-WAMF (Yet Another WhosAtMyFeeder) frontend into a modern, clean, and neutral UI with full functionality.

## Extra notes from scott:
I asked gemini to implement the steps in this ocument, which it did but there are some serious issues:
- the dark mode button does not respond when first pressed, if you toggle on and off then it responds.
- please improve the theme, its abit boring and basic.
- when viewing via mobile, none of the other sections are visable, only the first front page about how many birds have been detected today.
- in the settings page there is test frigate connection button which allways comes up with an error, however note that it actually does fetch the configured cameras from frigate so could this be working but the error actually is incorrect?
- can you implement the new auth method aswell as the falback frigate port 5000 please.
- Please give the system its proper name in the container, currently its called whos at my feeder, but the proper title is yet another whos at my feeder. 
- please check over all the work that gemini has done, i have no faith in that guy.

## Current State
- **Framework**: Svelte 5 + TypeScript + Tailwind CSS + Vite
- **Location**: `/apps/ui/src/`
- **Issues**:
  - Settings page is a placeholder (shows "Configuration options will appear here")
  - Events page is a placeholder
  - Species page is a placeholder
  - UI looks outdated/unpolished
  - No dark mode toggle (only system preference)

## Design Requirements

### Visual Style
- **Modern & Clean**: Minimalist design with plenty of whitespace
- **Neutral Colors**: Use grays, slate, or zinc color palette as base
- **Accent Color**: Subtle blue or teal for interactive elements
- **Rounded Corners**: Use `rounded-lg` or `rounded-xl` consistently on cards, buttons, inputs
- **Shadows**: Subtle shadows (`shadow-sm`, `shadow-md`) for depth
- **Typography**: Clean, readable fonts with clear hierarchy

### Dark Mode
- Add a **dark mode toggle** in the header (sun/moon icon)
- Persist preference to localStorage
- Support three states: Light / Dark / System
- Ensure all components look good in both modes

### Layout
- Responsive grid layouts
- Consistent spacing (`gap-4`, `gap-6`)
- Maximum content width with centered container
- Sticky header with blur effect

## Pages to Implement

### 1. Dashboard (`/`)
**Current**: Shows detection cards in a grid - mostly working
**Improvements**:
- Better card design with actual snapshot images from `/api/frigate/{event_id}/snapshot.jpg`
- Hover effects and transitions
- Loading skeleton states
- Empty state design
- Connection status indicator (already exists, polish it)

### 2. Events Explorer (`/events`)
**Current**: Placeholder only
**Implement**:
- Paginated list/grid of all detections
- Filters: by species, by camera, by date range
- Sort options: newest first, oldest first, highest confidence
- Click to view detail modal with full image and metadata
- Infinite scroll or pagination controls

### 3. Species Leaderboard (`/species`)
**Current**: Placeholder only
**Implement**:
- Ranked list of species by detection count
- Visual bars or charts showing relative frequency
- Click species to filter Events view
- Fun stats: "Most active hour", "First seen", "Last seen"
- Optional: small thumbnail of most recent detection per species

### 4. Settings (`/settings`)
**Current**: Placeholder only
**Implement full settings form**:
- **Frigate Connection**:
  - Frigate URL input
  - Test connection button
- **MQTT Settings**:
  - Server hostname
  - Port
  - Authentication toggle
  - Username/Password fields (show/hide password)
- **Classification Settings**:
  - Confidence threshold slider (0.0 - 1.0)
  - Show current model info
- **Camera Selection**:
  - Multi-select for which cameras to monitor
  - Fetch available cameras from Frigate
- **Appearance**:
  - Dark mode toggle
- **Save button** with loading state
- **Success/error notifications**

## Component Structure

```
src/
├── App.svelte              # Main app with router and dark mode state
├── main.ts                 # Entry point
├── app.css                 # Global styles, Tailwind imports
└── lib/
    ├── api.ts              # API functions (already has some)
    ├── stores/
    │   └── theme.ts        # Dark mode store with localStorage
    ├── components/
    │   ├── Header.svelte         # Sticky header with nav and dark mode toggle
    │   ├── DetectionCard.svelte  # Card for single detection (improve)
    │   ├── DetectionModal.svelte # Full-screen detail view
    │   ├── SpeciesCard.svelte    # Card for species stats
    │   ├── FilterBar.svelte      # Filters for events page
    │   ├── Pagination.svelte     # Pagination controls
    │   ├── LoadingSkeleton.svelte# Loading placeholder
    │   ├── EmptyState.svelte     # Empty state messaging
    │   ├── Toast.svelte          # Notification toasts
    │   └── Toggle.svelte         # Reusable toggle switch
    └── pages/
        ├── Dashboard.svelte      # Home page with live detections
        ├── Events.svelte         # Events explorer
        ├── Species.svelte        # Species leaderboard
        └── Settings.svelte       # Settings form
```

## API Endpoints Available

```typescript
// Already implemented in backend:
GET  /api/events?limit=50&offset=0   // List detections
GET  /api/species                     // Species counts
GET  /api/settings                    // Current settings
POST /api/settings                    // Update settings
GET  /api/sse                         // Server-sent events stream
GET  /api/frigate/{event_id}/snapshot.jpg  // Proxy to Frigate snapshot
GET  /api/frigate/{event_id}/thumbnail.jpg // Proxy to Frigate thumbnail
GET  /api/frigate/{event_id}/clip.mp4      // Proxy to Frigate clip
GET  /health                          // Health check
```

## Technical Requirements

### Svelte 5 Patterns
- Use `$state()` for reactive state
- Use `$derived()` for computed values
- Use `$effect()` for side effects
- Use `$props()` for component props
- Use `onclick` not `on:click` (Svelte 5 syntax)

### Dark Mode Implementation
```typescript
// stores/theme.ts
import { writable } from 'svelte/store';

type Theme = 'light' | 'dark' | 'system';

function createThemeStore() {
  const stored = localStorage.getItem('theme') as Theme | null;
  const { subscribe, set } = writable<Theme>(stored || 'system');

  return {
    subscribe,
    set: (value: Theme) => {
      localStorage.setItem('theme', value);
      set(value);
      applyTheme(value);
    }
  };
}

function applyTheme(theme: Theme) {
  const isDark = theme === 'dark' ||
    (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', isDark);
}
```

### Tailwind Dark Mode
Already configured with `class` strategy. Use `dark:` prefix:
```html
<div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-white">
```

### Image Loading
```svelte
<img
  src="/api/frigate/{detection.frigate_event}/thumbnail.jpg"
  alt={detection.display_name}
  class="w-full h-48 object-cover rounded-t-lg"
  loading="lazy"
  onerror={(e) => e.target.src = '/placeholder-bird.svg'}
/>
```

## Color Palette Suggestion

```css
/* Neutral base - Slate */
--color-bg: theme('colors.slate.50');        /* light */
--color-bg-dark: theme('colors.slate.900');  /* dark */

--color-card: theme('colors.white');
--color-card-dark: theme('colors.slate.800');

--color-border: theme('colors.slate.200');
--color-border-dark: theme('colors.slate.700');

/* Accent - Teal */
--color-accent: theme('colors.teal.500');
--color-accent-hover: theme('colors.teal.600');
```

## Deliverables

1. Refactored `App.svelte` with proper routing and dark mode
2. New `Header.svelte` component with dark mode toggle
3. Improved `DetectionCard.svelte` with real images
4. Fully functional `Settings.svelte` page
5. Fully functional `Events.svelte` page with filters
6. Fully functional `Species.svelte` page with stats
7. Theme store for dark mode persistence
8. Any additional reusable components needed
9. Updated `api.ts` with all necessary API functions

## Notes

- Keep the existing functionality working (SSE connection, live updates)
- Test both light and dark modes
- Ensure responsive design (mobile-friendly)
- Use semantic HTML for accessibility
- Add appropriate loading and error states
- The backend API is already complete - just need to connect the frontend

## Do NOT

- Add unnecessary dependencies
- Over-engineer with complex state management
- Break existing SSE/live detection functionality
- Ignore TypeScript types
- Create files without being asked
