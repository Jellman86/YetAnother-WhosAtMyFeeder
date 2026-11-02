<script lang="ts">
    /**
     * A Garden capture's thumbnail, opening on hover or keyboard focus to the larger photograph
     * with its name, score, state, time and camera, as a bird's does (`DetectionPreview`). Both
     * share the hover pop-out contract (`HoverPopout`, `HoverPopoutPanel`).
     *
     * The photograph is the saved crop, else the snapshot, from the addresses the server listed
     * for this reader. A visitor is listed none for a photo the owner does not share, so there is
     * nothing to preview and the thumbnail stays a plain frame without a pop-out.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenPhotoPreview from './GardenPhotoPreview.svelte';
    import HoverPopoutPanel from './HoverPopoutPanel.svelte';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenCapturePhoto } from '../utils/garden-photo';
    import { gardenEntryText, gardenEntryView, gardenRowDetail } from '../utils/garden-explorer';
    import { HoverPopout } from '../utils/hover-popout.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { SCORE_TEXT, scoreBand } from '../utils/score-tone';

    interface Props {
        capture: GardenCapture;
        /** Activating the thumbnail opens the record, as the bird thumbnail does. */
        onopen: () => void;
        /** A saved crop fills the thumbnail as a bird's does; a capture list letterboxes it. */
        fill?: boolean;
    }

    let { capture, onopen, fill = false }: Props = $props();

    // The panel's image box, so a snapshot is framed on the animal at the shape it is shown in.
    const PANEL_ASPECT = 240 / 128;

    const popout = new HoverPopout();
    let failed = $state.raw<ReadonlySet<string>>(new Set());
    const listed = $derived(Boolean(capture.crop_url || capture.snapshot_url));
    const photo = $derived(gardenCapturePhoto(capture, failed, withAuthParams));

    const view = $derived(gardenEntryView(capture));
    const text = $derived(
        gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback }), authStore.hasOwnerAccess ? 'owner' : 'visitor')
    );
    const scientific = $derived(gardenRowDetail(capture, view).scientific);
    const score = $derived(view.score === null ? null : Math.round(view.score * 100));

    // A failed crop falls back to the snapshot; a failed snapshot to a placeholder of the same size.
    function markFailed(src: string): void {
        failed = new Set([...failed, src]);
    }
</script>

{#snippet placeholder(size: string, icon: string)}
    <span class="flex {size} items-center justify-center bg-slate-100 text-slate-300 dark:bg-slate-800 dark:text-slate-600" aria-hidden="true">
        <svg class={icon} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
    </span>
{/snippet}

{#snippet thumbnail()}
    <!-- The bird preview's size and frame, so the photo column reads as one. -->
    <span class="block h-9 w-9 overflow-hidden rounded-lg border-2 border-white bg-slate-100 dark:border-slate-900 dark:bg-slate-800">
        {#if photo}
            <GardenPhotoPreview {capture} src={photo.src} cropped={photo.cropped} {fill} aspect={1} onerror={() => markFailed(photo.src)} />
        {:else if listed}
            {@render placeholder('h-full w-full', 'h-4 w-4')}
        {/if}
    </span>
{/snippet}

{#if listed}
    <div
        bind:this={popout.root}
        class="relative flex items-center"
        data-garden-capture-preview={capture.id}
        onpointerenter={(event) => popout.pointerEnter(event)}
        onmouseleave={() => popout.hide()}
        onfocusin={(event) => popout.focusIn(event)}
        onfocusout={popout.focusOut}
        onkeydown={popout.keydown}
        role="presentation"
    >
        <button type="button" bind:this={popout.triggers[0]} class="grid min-h-11 min-w-11 place-items-center rounded-lg focus-ring" onclick={onopen}>
            <span class="sr-only">
                {$_('dashboard.field_log.preview_trigger', { values: { species: text.title }, default: 'Preview {species}' })}
            </span>
            {@render thumbnail()}
        </button>

        {#if popout.openIndex === 0}
            <HoverPopoutPanel {popout} data-garden-capture-preview-panel={photo ? (photo.cropped ? 'crop' : 'snapshot') : 'unavailable'}>
                <div class="h-32 w-full bg-slate-100 dark:bg-slate-800">
                    {#if photo}
                        <GardenPhotoPreview
                            {capture}
                            src={photo.src}
                            cropped={photo.cropped}
                            aspect={PANEL_ASPECT}
                            alt={$_('dashboard.field_log.preview_alt', { values: { species: text.title, camera: capture.camera }, default: '{species} on {camera}' })}
                            onerror={() => markFailed(photo.src)}
                        />
                    {:else}
                        {@render placeholder('h-full w-full', 'h-8 w-8')}
                    {/if}
                </div>
                <div class="space-y-1 p-3">
                    <div class="flex items-baseline justify-between gap-2">
                        <p class="truncate font-display text-sm font-bold text-slate-950 dark:text-white">{text.title}</p>
                        {#if score !== null}
                            <span class="shrink-0 text-xs font-bold tabular-nums {SCORE_TEXT[scoreBand(view.score)]}">{score}%</span>
                        {/if}
                    </div>
                    {#if scientific && scientific !== text.title}
                        <p class="truncate text-2xs italic text-slate-500 dark:text-slate-400">{scientific}</p>
                    {/if}
                    <p class="text-2xs font-medium {view.review ? 'text-attention-800 dark:text-attention-300' : 'text-slate-600 dark:text-slate-300'}" data-garden-capture-preview-state>
                        {text.state}
                    </p>
                    <p class="text-2xs text-slate-500 dark:text-slate-400">
                        {formatTime(capture.observed_at)} &middot; {capture.camera}
                    </p>
                </div>
            </HoverPopoutPanel>
        {/if}
    </div>
{:else}
    <span class="grid min-h-11 min-w-11 place-items-center" aria-hidden="true" data-garden-capture-preview-unlisted>
        {@render thumbnail()}
    </span>
{/if}
