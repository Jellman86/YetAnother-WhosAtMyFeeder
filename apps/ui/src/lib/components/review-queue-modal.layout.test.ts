import { describe, expect, it } from 'vitest';
import modalSource from './ReviewQueueModal.svelte?raw';
import dashboardSource from '../pages/Dashboard.svelte?raw';

describe('review queue walk-through', () => {
    it('is its own flow rather than the detection modal', () => {
        expect(dashboardSource).toContain('<ReviewQueueModal');
        expect(dashboardSource).toContain('reviewSessionOpen = true');
        // Working the queue must not bounce the user to Explorer.
        expect(dashboardSource).not.toContain("onreviewall={() => onnavigate?.('/events')}");
    });

    it('behaves as a dialog: labelled, trapped, escapable', () => {
        expect(modalSource).toContain('role="dialog"');
        expect(modalSource).toContain('aria-modal="true"');
        expect(modalSource).toContain('aria-labelledby="review-session-title"');
        expect(modalSource).toContain('trapFocus(dialogEl)');
        expect(modalSource).toContain("event.key === 'Escape'");
        expect(modalSource).toContain('use:portal');
    });

    it('states position, progress and the completed summary', () => {
        expect(modalSource).toContain('dashboard.review_session.position');
        expect(modalSource).toContain('dashboard.review_session.summary');
        expect(modalSource).toContain('motion-reduce:transition-none');
    });

    it('offers species this feeder sees before the full label list', () => {
        expect(modalSource).toContain('dashboard.review_session.seen_here');
        // The alphabetical head of an 11,000-label list is invertebrates, not birds.
        expect(modalSource).not.toContain('labels.slice(0, 8)');
    });

    it('offers the same feeder list as "Pick a different species" (#503)', () => {
        // One source for every picker: the feeder's own species, most visits first.
        // Today's sightings alone left the queue offering two species on a feeder with forty.
        expect(modalSource).toContain('fetchFeederSpecies()');
        expect(modalSource).toContain('withoutCurrentSpecies(');
        expect(modalSource).toContain('speciesPickerNames(');
        expect(modalSource).toContain('dashboard.review_session.suggestions_unavailable');
        expect(dashboardSource).not.toContain('recentSpecies');
        expect(dashboardSource).not.toContain('suggestions=');
    });

    it('keeps the chosen saved photograph while reading candidate framing metadata', () => {
        expect(modalSource).toContain('fetchSnapshotCandidates');
        expect(modalSource).toContain('getSnapshotUrl(session.current.frigate_event)');
        expect(modalSource).toContain('sources={photographSources}');
        expect(modalSource).toContain('sources={wholeSceneSources}');
        expect(modalSource).toContain('findMatchingFullFrameCandidate, sameFrameCropCandidates');
        expect(modalSource).toMatch(
            /findMatchingFullFrameCandidate\(\s*response\.candidates \?\? \[\],\s*photograph\?\.candidate_id \?\? null\s*\)/
        );
        // Crops only exist for scanned events, so their absence is stated, not hidden.
        expect(modalSource).toContain('dashboard.review_session.no_crop');
    });

    it('peeks at the whole scene like the detection record, with no switch and no strategy name (#256)', () => {
        expect(modalSource).toContain("import { WholeScenePeek } from '../utils/whole-scene-peek.svelte'");
        expect(modalSource).toContain('data-review-whole-scene-peek');
        expect(modalSource).toContain('onmouseenter={wholeScene.enter}');
        expect(modalSource).toContain('onfocus={wholeScene.show}');
        expect(modalSource).toContain('onclick={wholeScene.toggle}');
        expect(modalSource).toContain('wholeScene.measure(sceneEl, wholeSceneCrops[0]?.crop_box, otherCropBoxes)');
        expect(modalSource).toContain('data-review-other-bird-outline');
        expect(modalSource).toContain('detection.whole_scene_chip_pinned');
        expect(modalSource).not.toContain('dashboard.review_session.crop\'');
        expect(modalSource).not.toContain('dashboard.review_session.full_frame');
        // "sliced_2x2" is how the crop was found, not something a reviewer decides with.
        expect(modalSource).not.toContain('crop_strategy');
        // Escape unpins before it closes the queue.
        expect(modalSource).toMatch(/if \(wholeScene\.pinned\) \{\s*wholeScene\.reset\(\);\s*return;/);
    });

    it('shows every frame kept from the visit in the same strip as the record, and choosing one changes only the photograph', () => {
        expect(modalSource).toContain("import FrameStrip from './FrameStrip.svelte'");
        expect(modalSource).toContain('groupCandidatesIntoMoments(candidates.filter(');
        expect(modalSource).toContain('item.thumbnail_url || item.image_url || item.candidate_id === currentCandidateId');
        expect(modalSource).toContain('data-review-frame-strip');
        expect(modalSource).toContain('current={activeMoment}');
        expect(modalSource).toContain("applySnapshotCandidate(eventId, { mode: 'candidate', candidate_id: candidate.candidate_id })");
        // The photograph is whatever is chosen, crop or whole scene; the strip reflects it after a change.
        expect(modalSource).toContain('candidate.candidate_id === response.current_candidate_id');
        expect(modalSource).toContain('await loadCandidates(eventId, () => session.current?.frigate_event !== eventId);');
        // Regeneration stays on the full record, where the scan's status is shown.
        expect(modalSource).not.toContain('onregenerate=');
    });

    it('keeps the media block its own height on phones so it never overlaps the rail', () => {
        expect(modalSource).toContain('flex min-h-0 flex-1 flex-col overflow-y-auto md:grid');
        expect(modalSource).toContain('flex shrink-0 flex-col bg-slate-950 md:min-h-0 md:justify-center');
        expect(modalSource).toContain('flex flex-col gap-3 p-4 md:min-h-0 md:overflow-y-auto');
    });

    it('keeps a visible species heading below the photograph in the review queue (#481)', () => {
        const heading = modalSource.match(/<div[^>]*data-review-species-heading[^>]*>([\s\S]*?)<\/div>/)?.[1];
        expect(heading).toBeDefined();
        expect(heading).toMatch(/<h3[^>]*>\s*\{naming.primary\}\s*<\/h3>/);
        // No class hides or lifts it out of flow; decorative separators may still be aria-hidden.
        expect(heading).not.toMatch(/class="[^"]*\b(hidden|absolute)\b/);
        expect(modalSource.indexOf('data-review-species-heading')).toBeGreaterThan(modalSource.indexOf('sources={photographSources}'));
        expect(modalSource.indexOf('data-review-species-heading')).toBeLessThan(modalSource.indexOf('data-review-frame-strip'));
    });

    it('uses the record naming preferences for each current queue item', () => {
        expect(modalSource).toMatch(/getBirdNames\(current,\s*settingsStore.displayCommonNames,\s*settingsStore.scientificNamePrimary\)/);
        expect(modalSource).toContain('{#if naming.secondary}');
        expect(modalSource).toContain('{naming.secondary}');
    });

    it('offers a way out of every item, including one that is not a bird', () => {
        expect(modalSource).toContain('dashboard.review_session.skip');
        expect(modalSource).toContain('dashboard.review_session.not_a_bird');
        expect(modalSource).toContain('dashboard.review_session.full_record');
    });

    it('can delete a detection that was never a bird, and says it is permanent (#375)', () => {
        // Frigate fires on rocks. Hiding keeps the record, which is right for a real bird
        // mis-scored, but wrong for a rock, and reaching Explorer to delete broke the queue flow.
        expect(modalSource).toContain('ondelete');
        expect(modalSource).toContain('dashboard.review_session.delete');
        // The one copy already used for this, which names the loss and offers hiding instead.
        expect(modalSource).toContain('actions.confirm_delete');
        // Destructive work is not styled like the neutral way out beside it.
        expect(modalSource).toContain('text-red-600');
        expect(dashboardSource).toContain('ondelete={deleteFromQueue}');
        expect(dashboardSource).toContain('async function deleteFromQueue');
    });

    it('keeps hiding as the non-destructive option beside deleting', () => {
        // Deleting must not replace hiding: a real bird scored badly should still be hideable.
        expect(modalSource).toContain('dashboard.review_session.not_a_bird');
        expect(modalSource).toContain('onhide(current)');
    });

    it('ends with an honest summary rather than silently closing', () => {
        expect(modalSource).toContain('dashboard.review_session.done');
        expect(modalSource).toContain('dashboard.review_session.skipped_note');
    });

    it('degrades when a snapshot is missing instead of showing a hole', () => {
        expect(modalSource).toContain("import MediaImage from './MediaImage.svelte'");
        // The saved photograph first, then the camera's thumbnail of the same capture.
        expect(modalSource).toMatch(
            /getSnapshotUrl\(session\.current\.frigate_event\)[^\]]*getThumbnailUrl\(session\.current\.frigate_event[,)]/
        );
    });

    it('says why the item needs a person in words, under one heading, with species as hairline rows', () => {
        const reason = modalSource.match(/<p[^>]*data-review-reason[^>]*>([\s\S]*?)<\/p>/)?.[1];
        expect(reason).toContain('bg-amber-500');
        expect(reason).toContain('dashboard.review_session.threshold_note');
        expect(reason).toContain('dashboard.review_session.new_species_note');
        expect(modalSource).not.toContain('dashboard.review_session.what_is_it');
        // Rows inside a list are split by hairlines, not nested cards (layout-patterns §6).
        expect(modalSource).toMatch(/<ul\s+class="[^"]*divide-y[^"]*"\s+aria-labelledby="review-species-choices"/);
        expect(modalSource).not.toContain('rounded-xl border border-slate-200 px-3 py-2 text-left');
    });

    it('bands the score like every other surface and labels it for screen readers', () => {
        expect(modalSource).toContain('{scoreTone(current.score ?? 0)}');
        expect(modalSource).toContain("$_('detection.confidence', { default: 'Confidence' })");
        expect(modalSource).not.toContain('font-semibold text-accent-300');
    });

    it('closes from a labelled icon button and shows progress on every screen size', () => {
        expect(modalSource).toContain("aria-label={$_('common.close', { default: 'Close' })}");
        expect(modalSource).toContain('absolute inset-x-0 -bottom-px h-0.5');
        expect(modalSource).not.toContain('hidden h-1.5 w-32');
    });

    it('fills a phone like the detection record and floats as the same dialog from sm up', () => {
        const dialog = modalSource.match(/<div\s+bind:this=\{dialogEl\}[\s\S]*?class="([^"]*)"/)?.[1] ?? '';
        expect(dialog).toContain('max-h-[100dvh]');
        expect(dialog).toContain('rounded-none');
        expect(dialog).toContain('sm:max-h-[92vh]');
        expect(dialog).toContain('sm:rounded-3xl');
        expect(dialog).toContain('max-w-5xl');
        expect(dialog).toContain('dark:bg-slate-800');
        expect(modalSource).toContain('bg-slate-950/70 p-0 backdrop-blur-sm sm:p-4');
    });

    it('states the position beside the title in one header row', () => {
        const position = modalSource.match(/<p[^>]*data-review-position[^>]*>/)?.[0] ?? '';
        expect(position).toContain('tabular-nums');
        expect(modalSource.indexOf('data-review-position')).toBeGreaterThan(modalSource.indexOf('id="review-session-title"'));
        expect(modalSource).toMatch(/<div class="flex min-w-0 items-baseline[^"]*">\s*<h2 id="review-session-title"/);
    });

    it('flags the reason with the amber wash flagged rows use, not a nested card', () => {
        const reason = modalSource.match(/<p[^>]*data-review-reason[^>]*>/)?.[0] ?? '';
        expect(reason).toContain('bg-gradient-to-r from-amber-50');
        expect(reason).toContain('dark:from-amber-500/10');
        expect(reason).not.toMatch(/\brounded|\bborder\b|\bshadow/);
    });

    it('keeps one repeated Identify quiet until its row is pointed at or focused', () => {
        const identify = modalSource.match(/<span class="([^"]*)">\s*\{\$_\('dashboard\.field_log\.identify'/)?.[1] ?? '';
        expect(identify).toContain('text-slate-500');
        expect(identify).toContain('group-hover:text-brand-700');
        expect(identify).toContain('group-focus-visible:text-brand-700');
    });

    it('opens the full record from beneath the photograph, after Close in focus order', () => {
        const fullRecord = modalSource.indexOf("'dashboard.review_session.full_record'");
        expect(fullRecord).toBeGreaterThan(modalSource.indexOf("aria-label={$_('common.close', { default: 'Close' })}"));
        expect(fullRecord).toBeGreaterThan(modalSource.indexOf('data-review-species-heading'));
        expect(fullRecord).toBeLessThan(modalSource.indexOf('data-review-frame-strip'));
        const actions = modalSource.match(/<div[^>]*data-review-actions[^>]*>([\s\S]*?)<!-- The decision comes first/)?.[1] ?? '';
        expect(actions).not.toContain('full_record');
    });

    it('keeps the decisions in reach on a phone without covering the rail on wider screens', () => {
        const actions = modalSource.match(/<div[^>]*data-review-actions[^>]*>/)?.[0] ?? '';
        expect(actions).toContain('sticky bottom-0');
        expect(actions).toContain('md:static');
        expect(actions).toContain('border-t');
    });

    it('marks a clear queue with the success scale, which every theme keeps green', () => {
        expect(modalSource).not.toContain('emerald');
        expect(modalSource).toContain('bg-success-100 text-success-700');
    });
});
