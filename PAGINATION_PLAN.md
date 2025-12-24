# Pagination & UI Polish Plan

## Current Issues

### Dashboard (Live View)
- Array grows infinitely via SSE (memory leak)
- No limit on displayed detections
- No way to see older detections

### Events Page
- "Load More" infinite scroll exists but is basic
- Filtering/sorting is client-side only (broken for large datasets)
- No total count shown
- No page navigation (can't jump to page 5)
- Filter dropdowns only show species/cameras from loaded events

---

## Implementation Plan

### Phase 1: Dashboard Improvements

#### 1.1 Limit Live Detections Display
- Cap displayed detections at 24 (configurable)
- New SSE detections push old ones out: `detections = [newDet, ...detections].slice(0, MAX_DISPLAY)`
- Add "View all in Events" link

#### 1.2 Add Summary Stats Banner
- Show today's detection count
- Most common species today
- Link to Events page with "Today" filter pre-selected

### Phase 2: Events Page - Server-Side Filtering

#### 2.1 Backend API Updates
- Add `species` and `camera` query params to `/api/events`
- Add `/api/events/filters` endpoint returning available species & cameras
- Update `/api/events/count` to support all filters

#### 2.2 Frontend Filter Updates
- Fetch filter options from `/api/events/filters`
- Pass filters to server instead of filtering client-side
- Show loading state while fetching filtered results

### Phase 3: Proper Pagination

#### 3.1 Page-Based Navigation
- Replace "Load More" with page numbers
- Show: `< 1 2 3 ... 10 11 12 >`
- Allow page size selection (12, 24, 48)
- Show total count: "Showing 25-48 of 1,234 detections"

#### 3.2 URL State
- Store page, filters, sort in URL query params
- Allow sharing/bookmarking filtered views
- Back button works correctly

### Phase 4: UI Polish

#### 4.1 Detection Cards
- Add subtle hover animations
- Lazy load images with intersection observer
- Add skeleton loading state for cards

#### 4.2 Empty States
- Better messaging when no results match filters
- Suggest clearing filters

#### 4.3 Responsive Improvements
- Better mobile filter UX (collapsible filter panel)
- Touch-friendly pagination

#### 4.4 Performance
- Consider virtual scrolling for very large result sets
- Image loading optimization

---

## API Changes Required

### New Endpoint: GET /api/events/filters
```json
{
  "species": ["Blue Tit", "Robin", "Sparrow"],
  "cameras": ["front_garden", "back_feeder"]
}
```

### Updated: GET /api/events
Add query params:
- `species` - filter by species name
- `camera` - filter by camera name
- `sort` - "newest", "oldest", "confidence"

### Updated: GET /api/events/count
Add same filter params for accurate counts

---

## File Changes

### Backend
- `backend/app/routers/events.py` - Add filter params, new filters endpoint
- `backend/app/repositories/detection_repository.py` - Add filter methods

### Frontend
- `apps/ui/src/App.svelte` - Limit dashboard detections
- `apps/ui/src/lib/pages/Dashboard.svelte` - Add summary stats, "View all" link
- `apps/ui/src/lib/pages/Events.svelte` - Server-side filtering, pagination UI
- `apps/ui/src/lib/api.ts` - New API functions
- `apps/ui/src/lib/components/Pagination.svelte` - New component

---

## Priority Order

1. **Fix memory leak** (Dashboard limit) - Critical
2. **Server-side filtering** - Important for usability
3. **Page navigation** - Nice to have
4. **UI polish** - Ongoing
