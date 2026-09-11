import { describe, expect, it } from 'vitest';
import stripSource from './FrameStrip.svelte?raw';
import modalSource from './DetectionModal.svelte?raw';

describe('the frame strip is one ordered set of moments (#256)', () => {
    it('renders one thumbnail per moment and never a framing variant beside it', () => {
        expect(stripSource).toContain('{#each moments as moment, index (moment.key)}');
        expect(stripSource).not.toContain('source_mode');
        expect(stripSource).not.toContain('snapshot_source_');
        // The camera's own snapshot is a moment like the others, named as recorded.
        expect(stripSource).toContain('detection.snapshot_framing_as_recorded');
    });

    it('opens a comparison pop-out by hover and by keyboard, per the layout standard', () => {
        expect(stripSource).toContain('onmouseenter={() => show(index)}');
        expect(stripSource).toContain('onfocusin={() => show(index)}');
        expect(stripSource).toContain('const CLOSE_GRACE_MS = 120;');
        expect(stripSource).toContain("event.key === 'Escape'");
        expect(stripSource).toContain('aria-expanded={openIndex === index}');
        expect(stripSource).toContain('motion-safe:animate-in');
        expect(stripSource).toContain('use:portal');
        // Escape closes the pop-out and not the record behind it.
        expect(stripSource).toContain('event.stopPropagation();\n            const index = openIndex;\n            hide(true);');
    });

    it('is reachable by keyboard although the panel lives outside the dialog\'s focus trap', () => {
        expect(stripSource).toContain("event.key !== 'ArrowDown' && event.key !== 'ArrowUp'");
        expect(stripSource).toContain('onkeydown={(event) => handleTriggerKeydown(event, index)}');
        expect(stripSource).toContain('onkeydown={handlePanelKeydown}');
        expect(stripSource).toContain("if (event.key === 'Tab' || event.key === 'Escape')");
        expect(stripSource).toContain('onfocusout={handleFocusOut}');
    });

    it('labels what the model read in a frame as a read, with one action that names its effect', () => {
        expect(stripSource).toContain('detection.frame_model_read');
        expect(stripSource).toContain('detection.frame_read_note');
        expect(stripSource).toContain('detection.frame_use');
        expect(stripSource).toContain('onuse(moment)');
        // No second action: the whole scene belongs to the photograph, not to the pop-out.
        expect(stripSource).not.toContain('whole_scene');
    });

    it('marks the photograph in place rather than staging a preview', () => {
        expect(stripSource).toContain('aria-pressed={chosen}');
        expect(stripSource).toContain('detection.frame_chosen_badge');
        expect(stripSource).toContain('detection.frame_is_photograph');
        expect(stripSource).not.toContain('Preview, not saved');
        expect(stripSource).not.toContain('snapshot_save');
    });

    it('keeps overflowing moments clickable beneath a non-interactive fade', () => {
        expect(stripSource).toContain('.snapshot-strip');
        expect(stripSource).toContain('scrollbar-width: none');
        expect(stripSource).toContain('node.scrollLeft + node.clientWidth < node.scrollWidth - 1');
        expect(stripSource).toContain("node.addEventListener('scroll', update, { passive: true })");
        expect(stripSource).toContain("style.setProperty('--strip-fade-opacity', hasMoreToRight ? '1' : '0')");
        expect(stripSource).toContain('data-snapshot-strip-fade');
        expect(stripSource).toContain('pointer-events-none');
        expect(stripSource).not.toContain('mask-image:');
        // The container keeps its size when the moment list changes, so a resize observer
        // alone would leave the fade describing a strip that is no longer there.
        expect(stripSource).toContain('new MutationObserver(update)');
        expect(stripSource).toContain('{ childList: true }');
    });

    it('lifts the chosen moment like a dock item without using an active outline', () => {
        expect(stripSource).toContain("'z-10 -translate-y-1 scale-105 bg-white/15 opacity-100 shadow-lg shadow-black/50'");
        expect(stripSource).toContain('motion-reduce:transform-none');
        expect(stripSource).not.toContain("? 'ring-2 ring-brand-400'");
    });

    it('degrades a missing thumbnail to a placeholder of the same size', () => {
        expect(stripSource).toContain('failed.has(moment.key)');
        expect(stripSource).toContain('h-9 w-12 items-center justify-center rounded-md bg-slate-800');
    });
});

describe('the record uses the strip and drops the framing toggle (#256)', () => {
    it('mounts the strip in the media footer and hands it the grouped moments', () => {
        const footerStart = modalSource.indexOf('data-detection-media-footer');
        const pickerStart = modalSource.indexOf('data-detection-inline-frame-picker', footerStart);
        expect(pickerStart).toBeGreaterThan(footerStart);
        const picker = modalSource.slice(pickerStart, pickerStart + 1400);
        expect(picker).toContain('<FrameStrip');
        expect(picker).toContain('moments={frameMoments}');
        expect(picker).toContain('current={activeMoment}');
        expect(picker).toContain('onuse={(moment) => { void handleUseMoment(moment); }}');
        expect(modalSource).toContain('groupCandidatesIntoMoments(');
        expect(modalSource).toContain('asRecordedAvailable: originalFrigateSnapshotAvailable');
    });

    it('has no Best crop / Full frame switch; the photograph is the crop', () => {
        expect(modalSource).not.toContain('data-detection-media-toggle');
        expect(modalSource).not.toContain('detection.media_stored');
        expect(modalSource).not.toContain('detection.media_full_frame');
        expect(modalSource).not.toContain("mediaView = 'full'");
    });

    it('peeks at the whole scene on hover or focus and pins it on click', () => {
        expect(modalSource).toContain('data-detection-whole-scene-peek');
        // A pointer crossing the photograph on its way to Play or Close is not a request.
        expect(modalSource).toContain('const PEEK_INTENT_MS = 250;');
        expect(modalSource).toContain('onmouseenter={peekWholeSceneAfterIntent}');
        expect(modalSource).toContain('onfocus={peekWholeScene}');
        expect(modalSource).toContain('onmouseleave={unpeekWholeScene}');
        expect(modalSource).toContain('onblur={unpeekWholeScene}');
        expect(modalSource).toContain('toggleWholeScenePin()');
        expect(modalSource).toContain('aria-pressed={wholeScenePinned}');
        // The peek only exists when the same moment has an uncropped frame to show, so never
        // over Frigate's own snapshot, whose "matching" frame would be another moment's.
        expect(modalSource).toContain('findMatchingFullFrameCandidate');
        expect(modalSource).toContain("currentSnapshotSource !== 'frigate_snapshot'\n        && !!(fullFrameSnapshotCandidate");
        expect(modalSource).toContain('{#if canPeekWholeScene}');
    });

    it('outlines the crop on the whole scene from a measurement, never a guess', () => {
        expect(modalSource).toContain('wholeSceneOutline(');
        expect(modalSource).toContain('element.naturalWidth');
        expect(modalSource).toContain('onload={measureWholeScene}');
        expect(modalSource).toContain('data-detection-whole-scene-outline');
        expect(modalSource).toContain('{#if showingWholeScene && wholeSceneOutlineBox}');
    });

    it('offers the whole-scene rescue only while pinned, and Escape unpins before it closes', () => {
        expect(modalSource).toContain('{#if wholeScenePinned && showingWholeScene}');
        expect(modalSource).toContain('detection.whole_scene_use');
        expect(modalSource).toContain('detection.whole_scene_back');
        expect(modalSource).toContain('useWholeSceneAsPhotograph()');
        expect(modalSource).toMatch(/if \(e\.key !== 'Escape'\) return;[\s\S]{0,200}?if \(wholeScenePinned\) \{[\s\S]{0,120}?resetMediaView\(\);[\s\S]{0,60}?return;/);
    });

    it('uses a frame straight from the pop-out, with no separate save step', () => {
        expect(modalSource).toContain('async function handleUseMoment(moment: FrameMoment)');
        expect(modalSource).toContain("await handleApplySnapshot('revert_original');");
        expect(modalSource).toContain("await handleApplySnapshot('candidate', candidate.candidate_id);");
        expect(modalSource).not.toContain('pendingSnapshotMode');
        expect(modalSource).not.toContain('handleSaveSnapshotSelection');
    });

    it('names the three identification actions by their effect, confirm first', () => {
        const start = modalSource.indexOf('data-detection-identification-actions');
        expect(start).toBeGreaterThan(-1);
        const actions = modalSource.slice(start, modalSource.indexOf('<!-- Bottom Actions -->', start));
        const confirm = actions.indexOf('actions.confirm_species');
        const pick = actions.indexOf('actions.pick_species');
        const score = actions.indexOf('detection.score_again');
        expect(confirm).toBeGreaterThan(-1);
        expect(pick).toBeGreaterThan(confirm);
        expect(score).toBeGreaterThan(pick);
        expect(actions).toContain('class="btn btn-primary min-h-11 flex-1 px-4 text-sm"');
        expect(actions).toContain('class="btn btn-secondary min-h-11 flex-1 px-4 text-sm"');
        expect(actions).toContain('class="btn btn-ghost min-h-11 px-4 text-sm"');
    });
});
