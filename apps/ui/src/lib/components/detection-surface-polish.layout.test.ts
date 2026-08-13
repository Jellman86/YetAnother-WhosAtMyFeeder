import { describe, expect, it } from 'vitest';

import detectionCardSource from './DetectionCard.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('detection surface polish', () => {
    it('keeps event cards quiet and media-led', () => {
        expect(detectionCardSource).toContain('data-detection-card');
        expect(detectionCardSource).toContain('hover:border-brand-500/40');
        expect(detectionCardSource).not.toContain('hover:-translate-y-1.5');
        expect(detectionCardSource).not.toContain('group-hover:rotate-1');
        expect(detectionCardSource).not.toContain('ring-1 ring-slate-200/40');
        expect(detectionCardSource).toContain('inline-flex h-11 w-11 items-center justify-center');
        expect(detectionCardSource).toContain("let isManualObservation = $derived(detection.observation_source === 'manual_upload')");
        expect(detectionCardSource).not.toContain("manual_observation.uploaded");
    });

    it('preserves the full snapshot and exposes a labelled, responsive dialog', () => {
        expect(detectionModalSource).toContain('data-detection-detail-modal');
        expect(detectionModalSource).toContain('aria-labelledby="detection-modal-title"');
        expect(detectionModalSource).toContain('id="detection-modal-title"');
        expect(detectionModalSource).toContain('data-detection-media-ambient');
        expect(detectionModalSource).toContain('object-contain');
        expect(detectionModalSource).toContain('max-h-[100dvh]');
        expect(detectionModalSource).toContain('bg-gradient-to-br from-slate-900 via-slate-950 to-brand-950');
        expect(detectionModalSource).toContain('class="absolute top-4 right-4 z-40 inline-flex h-11 w-11');
    });

    it('keeps implementation identity collapsed until it is requested', () => {
        expect(detectionModalSource).toContain('data-detection-technical-identity');
        expect(detectionModalSource).toContain('<details');
        expect(detectionModalSource).toContain('group order-last');
        expect(detectionModalSource).toContain('{detection.frigate_event}');
    });

    it('uses section dividers for supporting context instead of stacked feature cards', () => {
        expect(detectionModalSource).toContain('data-detection-audio-section');
        expect(detectionModalSource).toContain('data-detection-weather-section');
        expect(detectionModalSource).toMatch(/data-detection-audio-section[^>]+border-t/);
        expect(detectionModalSource).toMatch(/data-detection-weather-section[^>]+border-t/);
    });

    it('shows honest snapshot options and keeps integration rows to measured states', () => {
        expect(detectionModalSource).toContain('data-detection-frame-strip');
        // Candidates are owner-gated, so a guest gets no strip rather than an empty one.
        expect(detectionModalSource).toContain('authStore.hasOwnerAccess ? snapshotCandidates.filter');
        // "no matching call" from a disabled BirdNET would report a measurement never taken.
        expect(detectionModalSource).toContain('{#if birdnetEnabled && !isManualObservation}');
        expect(detectionModalSource).toContain('effectiveAudioConfirmed');
        expect(detectionModalSource).toContain('audioContextLoading');
        expect(detectionModalSource).toContain("detection.snapshot_options");
        expect(detectionModalSource).toContain('openSnapshotCandidate(candidate)');
        expect(detectionModalSource).toContain('data-detection-facts');
        expect(detectionModalSource).toContain('data-detection-identity');
    });

    it('names the actions by what they do', () => {
        expect(detectionModalSource).toContain('data-detection-confirm');
        expect(detectionModalSource).toContain("actions.confirm_species");
        expect(detectionModalSource).toContain("actions.pick_species");
        expect(detectionModalSource).toContain('applyManualTagResult(detection, result)');
        // Confirming an already-confirmed or unnamed detection is not offered.
        expect(detectionModalSource).toContain('{#if !detection.manual_tagged && !isUnknownSpecies}');
    });

    it('preserves the complete stored image when a matching full frame is unavailable', () => {
        expect(detectionModalSource).toContain('findMatchingFullFrameCandidate');
        expect(detectionModalSource).toContain("canShowFullFrame ? 'object-cover' : 'object-contain'");
    });

    it('keeps the favorite action and full-frame switch in one non-overlapping flow', () => {
        expect(detectionModalSource).toContain('data-detection-media-actions');
        expect(detectionModalSource).toContain('data-detection-media-toggle');
        expect(detectionModalSource).toContain('flex-col items-start gap-2');
        expect(detectionModalSource).not.toContain("canShowFullFrame ? 'top-16 left-3' : 'top-4 left-4'");
    });

    it('hides the options strip scrollbar and fades only a real overflow', () => {
        // A native bar over the image gradient is ugly and low contrast; masking unconditionally
        // would clip the last thumbnail on a strip that fits.
        expect(detectionModalSource).toContain('.snapshot-strip');
        expect(detectionModalSource).toContain('scrollbar-width: none');
        expect(detectionModalSource).toContain('node.scrollLeft + node.clientWidth < node.scrollWidth - 1');
        expect(detectionModalSource).toContain("node.addEventListener('scroll', update, { passive: true })");
        expect(detectionModalSource).toContain("hasMoreToRight ? '3.5rem' : '0px'");
        expect(detectionModalSource).toContain("'--strip-fade'");
    });

    it('labels the name rather than the reference photograph beside it', () => {
        // The eyebrow sat above a row that opens with a circular reference photo, so it read as
        // captioning the picture. The person glyph only restated the words.
        expect(detectionModalSource).not.toContain('M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V7a4 4 0 0 1 4-4');
        expect(detectionModalSource).toMatch(
            /detection\.identified_as[\s\S]{0,400}?font-display text-2xl/
        );
    });

    it('lets the species reference sit in the record instead of behind a twisty', () => {
        expect(detectionModalSource).toContain('data-detection-reference');
        expect(detectionModalSource).not.toMatch(/<details[^>]*>\s*<summary[^>]*>\s*\{\$_\('detection\.reference_disclosure'/);
    });

    it('does not nest a card inside the video notice card', () => {
        // The notice is already tinted and bordered; the disclosure adding its own border and
        // background made a card within a card.
        expect(detectionModalSource).not.toContain("bg-white/75 dark:bg-slate-900/40'");
        expect(detectionModalSource).toContain('border-t pt-2 {videoStatusNoticeTone.detailsContainer}');
    });

    it('makes the detection id disclosure the terminal chrome itself', () => {
        // The summary is the title bar: clicking the window opens it.
        expect(detectionModalSource).toContain('@keyframes -global-terminal-blink');
        expect(detectionModalSource).toContain('yawamf event show');
        expect(detectionModalSource).toContain('terminal-caret');
        expect(detectionModalSource).toContain('prefers-reduced-motion');
        // overflow-hidden on a <details> collapses it to its own borders in Chrome, so the
        // corners are rounded on the summary rather than clipped by the parent.
        expect(detectionModalSource).not.toMatch(
            /data-detection-technical-identity[\s\S]{0,240}?overflow-hidden/
        );
        expect(detectionModalSource).toContain('group-open:rounded-b-none');
        expect(detectionModalSource).toContain('focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-400');
        expect(detectionModalSource).toContain('font-mono text-xs');
        expect(detectionModalSource).toContain('motion-safe:transition-transform group-open:rotate-180');
    });

    it('borrows the window furniture of the viewer os', () => {
        expect(detectionModalSource).toContain("): 'mac' | 'windows' | 'linux'");
        expect(detectionModalSource).toContain("if (platform.includes('win')) return 'windows'");
        // Android reports Linux in its user agent and is not a desktop window manager.
        expect(detectionModalSource).toContain("!platform.includes('android')");
        // Cosmetic only, so an unrecognised platform still gets a complete window.
        expect(detectionModalSource).toContain("if (typeof navigator === 'undefined') return 'mac'");
        // The insides follow the furniture: DOS black, Ubuntu aubergine, plain dark elsewhere.
        expect(detectionModalSource).toContain("shell: 'bg-[#300a24]'");
        expect(detectionModalSource).toContain("host: 'yawamf@feeder'");
        expect(detectionModalSource).toContain("bg-[#000080]");
    });

    it('re-measures the options strip when the candidate list changes', () => {
        // The container keeps its size when children change, so a resize observer alone would
        // leave the fade describing a strip that is no longer there.
        expect(detectionModalSource).toContain('new MutationObserver(update)');
        expect(detectionModalSource).toContain('{ childList: true }');
    });

    it('gives the species info button real padding', () => {
        // It carried no padding class at all, so with its siblings hidden for a guest it
        // collapsed to the height of its own text.
        expect(detectionModalSource).not.toContain('flex-1 bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs rounded-xl');
        expect(detectionModalSource).toContain('btn btn-primary flex-1 px-3 py-2.5 text-xs');
    });

    it('keeps location-level notable reports out of individual detections', () => {
        expect(detectionModalSource).not.toContain('fetchEbirdNotable');
        expect(detectionModalSource).not.toContain('showEbirdNotable');
        expect(detectionModalSource).not.toContain('detection.ebird_notable_title');
    });

    it('discovers late BirdNET context independently of stored audio hints', () => {
        expect(detectionModalSource).toContain('fetchEventAudioContext');
        expect(detectionModalSource).toContain('controller.abort()');
        expect(detectionModalSource).toContain('for (const audio of audioContext)');
        expect(detectionModalSource).not.toContain('if (!hasAudioContext) return;');
        expect(detectionModalSource).toContain('if (detection.observation_source === \'manual_upload\')');
        expect(detectionModalSource).toContain('audioContext.filter((audio) => audio.matches_visual)');
        expect(detectionModalSource).toContain('!isManualObservation && (effectiveAudioConfirmed');
    });

    it('shows retained upload coordinates without BirdNET context', () => {
        expect(detectionModalSource).toContain('detection.observation_latitude');
        expect(detectionModalSource).toContain('data-manual-observation-location');
    });
});
