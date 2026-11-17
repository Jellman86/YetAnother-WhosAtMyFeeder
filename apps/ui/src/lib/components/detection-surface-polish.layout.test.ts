import { describe, expect, it } from 'vitest';

import detectionCardSource from './DetectionCard.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';
import technicalSource from './RecordTechnicalDetails.svelte?raw';
import audioSource from './record/RecordAudioEvidence.svelte?raw';
import noticeSource from './record/RecordVideoStatusNotice.svelte?raw';
import referenceSource from './record/RecordSpeciesReference.svelte?raw';
import disclosureSource from './ui/Disclosure.svelte?raw';
import dialogHeaderSource from './ui/DialogHeader.svelte?raw';

describe('detection surface polish', () => {
    it('keeps the audio context and edit-name controls at the touch-target floor', () => {
        // Every call heard sits behind the shared disclosure, whose row is a full touch target.
        expect(audioSource).toContain("<Disclosure label={$_('detection.audio_context_all'");
        expect(disclosureSource).toMatch(/<summary class="[^"]*min-h-11/);
        // The note keeps its space from the label, and its dot never ends a line.
        expect(disclosureSource).toContain("{#if note}{' '}<span class=\"font-semibold text-accent-ink\"><Separator />&nbsp;{note}</span>");
        expect(detectionModalSource).toMatch(/commonNameEditorOpen = !commonNameEditorOpen;\s+\}\}\s+aria-expanded=\{commonNameEditorOpen\}\s+class="[^"]*min-h-11/);
    });

    it('keeps event cards quiet and media-led', () => {
        expect(detectionCardSource).toContain('data-detection-card');
        expect(detectionCardSource).toContain('hover:border-accent-line/60');
        expect(detectionCardSource).not.toContain('hover:-translate-y-1.5');
        expect(detectionCardSource).not.toContain('group-hover:rotate-1');
        expect(detectionCardSource).not.toContain('ring-1 ring-slate-200/40');
        expect(detectionCardSource).toContain('btn btn-secondary btn-icon rounded-full');
        expect(detectionCardSource).toContain("let isManualObservation = $derived(detection.observation_source === 'manual_upload')");
        expect(detectionCardSource).not.toContain("manual_observation.uploaded");
    });

    it('preserves the full snapshot and exposes a labelled, responsive dialog', () => {
        expect(detectionModalSource).toContain('data-detection-detail-modal');
        expect(detectionModalSource).toContain('aria-labelledby="detection-modal-title"');
        expect(detectionModalSource).toContain('id="detection-modal-title"');
        expect(detectionModalSource).toContain('data-detection-media-ambient');
        expect(detectionModalSource).toContain('object-contain');
        expect(detectionModalSource).toContain('max-h-dvh');
        expect(detectionModalSource).toContain('data-detection-photograph');
        expect(detectionModalSource).not.toContain('from-black/80 via-black/25');
        expect(detectionModalSource).not.toContain('absolute inset-x-0 bottom-0 z-20 flex flex-col');
        expect(detectionModalSource).toContain("closeData={{ 'data-detection-modal-close': true }}");
        expect(dialogHeaderSource).toContain('<DialogCloseButton');
    });

    it('offers the originating Frigate event to the owner, honestly', () => {
        // The URL comes from the owner-only settings payload, so a guest can
        // never see the address; a retired event gets words instead of a
        // link that lands on an error; and it lives with the technical
        // identifiers behind the disclosure, not on the photograph (#309).
        // The browser-facing URL wins when configured, because frigate_url is
        // often a container address the browser cannot reach.
        expect(detectionModalSource).toContain(
            'settingsStore.settings?.frigate_external_url || settingsStore.settings?.frigate_url'
        );
        expect(detectionModalSource).toContain('/explore?event_id=');
        expect(detectionModalSource).toContain('if (!hasOwnerDetectionActions || isManualObservation) return null;');
        expect(detectionModalSource).toContain('if (missingEventMetadataGone) return null;');
        expect(detectionModalSource).toContain('data-frigate-event-link');
        expect(detectionModalSource).toContain('data-frigate-event-gone');
    });

    it('keeps implementation identity collapsed until it is requested', () => {
        expect(detectionModalSource).toContain('data-detection-technical-identity');
        expect(technicalSource).toContain('<details');
        expect(detectionModalSource).toContain('{detection.frigate_event}');
    });

    it('uses section dividers for supporting context instead of stacked feature cards', () => {
        expect(detectionModalSource).toContain('<RecordAudioEvidence');
        expect(audioSource).toMatch(/data-detection-audio-section[^>]+border-t/);
        // The weather no longer gets a section at all: it is one condensed
        // facts row (#268), pinned by weather-stated-once.layout.test.ts.
        expect(detectionModalSource).not.toContain('data-detection-weather-section');
    });

    it('replaces the old snapshot overlay with one strip of moments (#256)', () => {
        expect(detectionModalSource).toContain('data-detection-inline-frame-picker');
        // Candidates are owner-gated, so a guest gets no strip rather than an empty one.
        expect(detectionModalSource).toContain('authStore.hasOwnerAccess\n            ? groupCandidatesIntoMoments(');
        expect(detectionModalSource).toContain('<FrameStrip');
        expect(detectionModalSource).toContain('fullFrameSnapshotCandidate?.image_url');
        expect(detectionModalSource).not.toContain('snapshotRepairOpen');
        expect(detectionModalSource).not.toContain("default: 'Crop Type'");
        expect(detectionModalSource).not.toContain("default: 'Scored Frames'");
        // Framing variants of one moment are not offered side by side any more.
        expect(detectionModalSource).not.toContain('snapshotOptionStrip');
    });

    it('keeps integration rows to measured states', () => {
        // "no matching call" from a disabled BirdNET would report a measurement never taken.
        expect(detectionModalSource).toContain('{#if birdnetEnabled && !isManualObservation}');
        expect(detectionModalSource).toContain('effectiveAudioConfirmed');
        expect(detectionModalSource).toContain('audioContextLoading');
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
        // Not a crop: shown whole. A crop fills the box only when that cuts away little of it (#481).
        expect(detectionModalSource).toContain("photographIsCrop && photographFit === 'cover' ? 'object-cover' : 'object-contain'");
    });

    it('keeps media controls and snapshot choices in one ordered footer flow', () => {
        const footerStart = detectionModalSource.indexOf('data-detection-media-footer');
        const actionStart = detectionModalSource.indexOf('data-detection-media-actions', footerStart);
        const pickerStart = detectionModalSource.indexOf('data-detection-inline-frame-picker', footerStart);

        expect(footerStart).toBeGreaterThan(-1);
        expect(actionStart).toBeGreaterThan(footerStart);
        expect(pickerStart).toBeGreaterThan(actionStart);
        expect(detectionModalSource).toContain('data-detection-media-actions');
        // The Best crop / Full frame switch is gone (#256); the whole scene is a peek on the photograph.
        expect(detectionModalSource).not.toContain('data-detection-media-toggle');
        expect(detectionModalSource).toContain('data-detection-whole-scene-peek');
        // The rail names the bird; the photograph does not say it a second time.
        expect(detectionModalSource).not.toContain('data-detection-media-title');
        expect(detectionModalSource).toContain('flex flex-wrap items-center gap-2');
        expect(detectionModalSource).toContain('aspect-4/3 min-h-72');
        expect(detectionModalSource).not.toContain("absolute bottom-0 left-0 right-0 p-5 {showInlineFramePicker ? 'pb-28' : ''}");
        expect(detectionModalSource).not.toContain('absolute inset-x-0 bottom-0 z-20 flex flex-col gap-1');
        // Peeking stays non-mutating. Only a named action changes the photograph.
        expect(detectionModalSource).toContain('onfocus={wholeScene.show}');
        expect(detectionModalSource).not.toContain("canShowFullFrame ? 'top-16 left-3' : 'top-4 left-4'");
    });

    // The strip's own overflow fade, dock-item lift and re-measurement moved with it into
    // FrameStrip.svelte and are pinned by frame-strip.layout.test.ts.

    it('labels the name rather than the reference photograph beside it', () => {
        // The eyebrow sat above a row that opens with a circular reference photo, so it read as
        // captioning the picture. The person glyph only restated the words.
        expect(detectionModalSource).not.toContain('M12 3a4 4 0 0 1 4 4v1a4 4 0 0 1-8 0V7a4 4 0 0 1 4-4');
        expect(detectionModalSource).toMatch(
            /detection\.identified_as[\s\S]{0,400}?font-display text-2xl/
        );
    });

    it('lets the species reference sit in the record instead of behind a twisty', () => {
        expect(detectionModalSource).toContain('<RecordSpeciesReference');
        expect(referenceSource).toContain('data-detection-reference');
        expect(referenceSource).not.toMatch(/<details[^>]*>\s*<summary[^>]*>\s*\{\$_\('detection\.reference_disclosure'/);
    });

    it('does not nest a card inside the video notice card', () => {
        // The notice is already tinted and bordered; the disclosure adding its own border and
        // background made a card within a card.
        expect(detectionModalSource).not.toContain("bg-white/75 dark:bg-slate-900/40'");
        // Now a plain row in the rail: no tint, no border, and the disclosure adds none either.
        expect(detectionModalSource).toContain('<RecordVideoStatusNotice');
        expect(noticeSource).not.toMatch(/data-video-status-notice=\{tone\}[^>]*\b(?:border|bg-)/);
        expect(noticeSource).toMatch(/<div class="flex items-start gap-2" role="status" data-video-status-notice=\{tone\}>/);
    });

    it('draws the detection id disclosure as a plain panel in the current theme', () => {
        expect(detectionModalSource).toContain('<RecordTechnicalDetails');
        expect(technicalSource).toContain('class="group card-base"');
        // No window furniture, fake prompt, platform sniffing or period colours.
        expect(technicalSource).not.toMatch(/terminal|navigator|traffic|sigil|bg-\[#|text-\[#/i);
        expect(detectionModalSource).not.toContain('yawamf event show');
        // overflow-hidden on a <details> collapses it to its own borders in Chrome.
        expect(technicalSource).not.toContain('overflow-hidden');
        expect(technicalSource).toContain('focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus');
        expect(technicalSource).toContain('motion-safe:transition-transform group-open:rotate-180');
    });

    it('keeps the record in the order it is read: identity, decisions, context, reference, identifiers', () => {
        // Keyboard order is DOM order, so nothing may be re-ordered in CSS.
        expect(technicalSource).not.toContain('order-last');
        const order = [
            'data-detection-identity',
            'data-detection-identification-actions',
            'data-detection-more-actions-panel',
            'data-detection-facts',
            '<RecordSpeciesReference',
            'data-detection-technical-identity'
        ].map((marker) => detectionModalSource.indexOf(marker));
        expect(order.every((index) => index > 0)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
    });

    it('shortens the species reference to a few lines with a link to the source', () => {
        expect(referenceSource).toContain("summaryUrl ? 'line-clamp-3' : ''");
        expect(referenceSource).toContain('data-detection-reference-link');
    });

    it('keeps the less common record actions behind one control', () => {
        expect(detectionModalSource).toContain('data-detection-more-actions');
        expect(detectionModalSource).toMatch(/aria-expanded=\{moreActionsOpen\}\s+aria-controls="detection-more-actions"/);
        const panel = detectionModalSource.indexOf('data-detection-more-actions-panel');
        for (const marker of ['data-detection-score-again', 'data-detection-hide', 'data-detection-delete', 'detection.common_name_override_edit']) {
            expect(detectionModalSource.indexOf(marker)).toBeGreaterThan(panel);
        }
    });

    it('keeps no strip machinery of its own now the strip is a component', () => {
        expect(detectionModalSource).not.toContain('function watchOverflow');
        expect(detectionModalSource).not.toContain('.snapshot-strip {');
    });

    it('gives the species details button real padding, and leaves the primary action to the identification', () => {
        // It carried no padding class at all, so with its siblings hidden for a guest it
        // collapsed to the height of its own text. As a second primary it competed with Confirm.
        expect(detectionModalSource).not.toContain('flex-1 bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs rounded-xl');
        // Now a text link beside the name it is about, still a full touch target tall.
        expect(detectionModalSource).toMatch(/onclick=\{handleSpeciesInfo\}\s+class="inline-flex min-h-11 items-center gap-1 rounded-sm text-xs font-semibold text-accent-ink underline/);
        expect(detectionModalSource.indexOf('data-detection-species-details')).toBeLessThan(detectionModalSource.indexOf('data-detection-identification-actions'));
        expect(detectionModalSource).not.toContain('btn btn-primary flex-1 px-3 py-2.5 text-xs');
        expect(detectionModalSource.match(/\{\$_\('actions\.species_info'\)\}/g)).toHaveLength(1);
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

    it('keeps record status off the photograph and diagnostics out of the record', () => {
        // The archive state is said in the panel; only the favourite star stays on the image.
        const media = detectionModalSource.slice(detectionModalSource.indexOf('data-detection-media-actions'), detectionModalSource.indexOf('data-detection-details-column'));
        expect(media).not.toContain('archiveLabel');
        expect(detectionModalSource).toContain('data-detection-archive-state={archiveState}');
        // Which device and model ran the video analysis is diagnostics, not record content.
        expect(detectionModalSource).not.toMatch(/video_classification_model_name|completedVideoInferenceBadge/);
    });

    it('never lets the scrolling column squash the More actions list', () => {
        // A box that clips its content has no minimum height as a flex item, so Delete was cut off and could not be clicked.
        expect(detectionModalSource).toContain('class="card-base shrink-0 divide-y divide-line-soft overflow-hidden" data-detection-more-actions-panel');
    });

    it('lets the delete row be named by the words on it', () => {
        // A label that differs from the visible text fails speech input (label in name).
        const marker = detectionModalSource.indexOf('data-detection-delete');
        const row = detectionModalSource.slice(detectionModalSource.lastIndexOf('<button', marker), detectionModalSource.indexOf('</button>', marker));
        expect(row).not.toContain('aria-label');
        expect(row).toContain("{$_('actions.delete_detection')}");
    });

    it('uses the width it is given: a side column from 1280px, no band under a phone photograph, side by side when held sideways', () => {
        // The identification and the reference are two columns from 1280px, identification first in reading order.
        const primary = detectionModalSource.indexOf('data-detection-primary-column');
        const secondary = detectionModalSource.indexOf('data-detection-secondary-column');
        expect(primary).toBeGreaterThan(detectionModalSource.indexOf('data-detection-details-column'));
        expect(secondary).toBeGreaterThan(primary);
        expect(detectionModalSource.indexOf('<TaxonomyLineage')).toBeGreaterThan(secondary);
        expect(detectionModalSource.indexOf('data-detection-identity')).toBeLessThan(secondary);
        expect(detectionModalSource).toContain('xl:col-span-3 xl:grid xl:grid-cols-2 xl:items-start');
        expect(detectionModalSource).toContain('sm:rounded-2xl xl:max-w-7xl');
        // On a phone the star and play buttons sit on the photograph's lower edge.
        expect(detectionModalSource).toContain('max-sm:absolute max-sm:inset-x-4 max-sm:bottom-full max-sm:z-30 max-sm:mb-3" data-detection-media-actions');
        // Held sideways, photograph and identification stand side by side.
        expect(detectionModalSource).toContain('sm:short:grid sm:short:grid-cols-2 sm:short:overflow-hidden');
    });
});

