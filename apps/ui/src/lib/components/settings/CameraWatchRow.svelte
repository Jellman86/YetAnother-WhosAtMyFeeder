<script lang="ts">
    /**
     * One Frigate camera and what it is watched for: Off, Birds, Garden animals or Both. The
     * choices underneath belong to the subject that is switched on, so a camera's bird role shows
     * only while it watches for birds and motion photos only while it watches for Garden animals.
     * Which choices are possible is decided by `utils/camera-watch.ts`; this row only words them.
     */
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { CameraRole, CameraWatchBlock, CameraWatchMode, CameraWatchRow } from '../../utils/camera-watch';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    interface Props {
        row: CameraWatchRow;
        gardenEnabled: boolean;
        previewOpen: boolean;
        /** Id of the sentence saying why Preview is unavailable, when it is. */
        previewUnavailableId?: string;
        onmode: (mode: CameraWatchMode) => void;
        onrole: (role: CameraRole) => void;
        onmotion: (collect: boolean) => void;
        onpreview: () => void;
        preview?: Snippet;
    }

    let { row, gardenEnabled, previewOpen, previewUnavailableId, onmode, onrole, onmotion, onpreview, preview }: Props = $props();

    const uid = $props.id();
    const camera = $derived(row.camera);
    const watchesBirds = $derived(row.mode === 'birds' || row.mode === 'both');
    const watchesGarden = $derived(row.mode === 'garden' || row.mode === 'both');

    const modeOptions = $derived.by((): Array<{ value: CameraWatchMode; label: string }> => {
        const off = { value: 'off' as const, label: $_('settings.cameras.mode_off', { default: 'Off' }) };
        const birds = { value: 'birds' as const, label: $_('settings.cameras.mode_birds', { default: 'Birds' }) };
        if (!gardenEnabled) return [off, birds];
        return [
            off,
            birds,
            { value: 'garden', label: $_('settings.cameras.mode_garden', { default: 'Garden animals' }) },
            { value: 'both', label: $_('settings.cameras.mode_both', { default: 'Both' }) }
        ];
    });

    const roleOptions = $derived<Array<{ value: CameraRole; label: string }>>([
        { value: 'feeder', label: $_('settings.cameras.role_feeder', { default: 'Feeder' }) },
        { value: 'nest', label: $_('settings.cameras.role_nest', { default: 'Nest' }) }
    ]);

    function blockText(reason: CameraWatchBlock): string {
        switch (reason) {
            case 'last_bird_camera':
                return $_('settings.cameras.blocked_last_bird_camera', { default: 'At least one camera must watch for birds, so birds stay on for this camera.' });
            case 'camera_list_unread':
                return $_('settings.cameras.blocked_camera_list_unread', { default: 'Every camera watches for birds. Sync cameras from Frigate before turning birds off for one camera.' });
            case 'garden_off':
                return $_('settings.cameras.garden_beta_hint', { default: 'To watch for Garden animals as well, turn on Garden animals in Settings → Beta features.' });
        }
    }

    const blockReasons = $derived([...new Set(Object.values(row.blocked))].map(blockText));
    const roleHelp = $derived(row.role === 'nest'
        ? $_('settings.cameras.role_nest_help', { default: 'Nest box cam: collapses repeat detections of the same species into one per dedupe window so a continuously-present nesting bird does not flood the feed.' })
        : $_('settings.cameras.role_feeder_help', { default: 'Feeder cam: every Frigate event is treated as a fresh visit (default).' }));
</script>

<!-- One compact row per camera: its name, then a select for each choice that belongs to it. A choice
     that cannot be made is a disabled option, with the reason in words under the row. -->
<!-- A camera is a settings row: its name (and preview) on the left, its choices in the control
     column, so every camera's selects line up on one edge. -->
<li class="space-y-3 py-4 first:pt-0 last:pb-0 wrap-break-word" data-camera-watch={camera}>
    <div class="space-y-2 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0">
        <div class="min-w-0">
            <p class="break-all text-base font-medium text-slate-900 dark:text-white">{camera}</p>
            {#if row.presence === 'missing'}
                <p class="mt-0.5 flex items-center gap-1.5 text-sm text-attention-800 dark:text-attention-200" data-camera-missing>
                    <span class="attention-dot" aria-hidden="true"></span>
                    {$_('settings.cameras.not_found', { default: 'Not found in Frigate' })}
                </p>
                <p class="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
                    {$_('settings.cameras.not_found_help', { default: 'Frigate does not list this camera now. Its choices are kept until you change them; choose Off to remove it.' })}
                </p>
            {:else}
                <!-- A link-styled action, so it never reads as a label; the chevron turns while the preview shows. -->
                <button
                    type="button"
                    class="focus-ring inline-flex min-h-11 max-w-full flex-wrap items-center gap-x-1 rounded-sm text-sm font-medium text-brand-700 underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:text-slate-600 disabled:no-underline dark:text-brand-300 dark:disabled:text-slate-400"
                    aria-expanded={previewOpen}
                    aria-describedby={previewUnavailableId}
                    disabled={!!previewUnavailableId}
                    onclick={onpreview}
                >
                    {previewOpen
                        ? $_('settings.cameras.preview_hide', { default: 'Hide preview' })
                        : $_('settings.cameras.preview_show', { default: 'Preview' })}<span class="sr-only"> {camera}</span>
                    <svg class="h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none {previewOpen ? 'rotate-90' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 6 15 12 9 18" /></svg>
                </button>
            {/if}
        </div>
        <!-- Each choice's word sits beside its select, and above it when enlarged text leaves no room. -->
        <div class="min-w-0 space-y-2">
            <label class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600 dark:text-slate-400">
                <span class="w-24 max-w-full shrink-0" aria-hidden="true">{$_('settings.cameras.watch_for_label', { default: 'Watch for' })}</span>
                <select
                    class="select-base min-h-11 min-w-0 flex-1 basis-40"
                    aria-label={$_('settings.cameras.watch_for', { default: '{camera}: watch for', values: { camera } })}
                    aria-describedby={blockReasons.length > 0 ? `${uid}-reason` : undefined}
                    value={row.mode}
                    onchange={(event) => onmode((event.currentTarget as HTMLSelectElement).value as CameraWatchMode)}
                    data-camera-watch-select
                >
                    {#each modeOptions as option (option.value)}
                        <option value={option.value} disabled={!!row.blocked[option.value]}>{option.label}</option>
                    {/each}
                </select>
            </label>
            {#if watchesBirds}
                <label class="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600 dark:text-slate-400" data-camera-role>
                    <span class="w-24 max-w-full shrink-0" aria-hidden="true">{$_('settings.cameras.role_label', { default: 'Role' })}</span>
                    <select
                        class="select-base min-h-11 min-w-0 flex-1 basis-40"
                        aria-label={$_('settings.cameras.role_group', { default: '{camera}: bird role', values: { camera } })}
                        aria-describedby="{uid}-role-help"
                        value={row.role ?? 'feeder'}
                        onchange={(event) => onrole((event.currentTarget as HTMLSelectElement).value as CameraRole)}
                    >
                        {#each roleOptions as option (option.value)}
                            <option value={option.value}>{option.label}</option>
                        {/each}
                    </select>
                </label>
            {/if}
        </div>
    </div>

    {#if blockReasons.length > 0}
        <div id="{uid}-reason" class="space-y-0.5 text-sm text-slate-600 dark:text-slate-400" data-camera-watch-reason>
            {#each blockReasons as reason (reason)}
                <p>{reason}</p>
            {/each}
        </div>
    {/if}
    {#if watchesBirds}
        <p id="{uid}-role-help" class="text-sm text-slate-600 dark:text-slate-400" class:sr-only={row.role !== 'nest'}>{roleHelp}</p>
    {/if}

    {#if watchesGarden}
        <div class="flex min-h-11 items-center justify-between gap-3" data-camera-motion>
            <div class="min-w-0">
                <!-- The name starts with the words on screen; the camera is added for a screen reader. -->
                <span id="{uid}-motion-label" class="block text-sm font-medium text-slate-900 dark:text-white">{$_('garden.motion_toggle', { default: 'Collect motion review photos' })}<span class="sr-only"> ({camera})</span></span>
                <span id="{uid}-motion-help" class="block text-sm text-slate-600 dark:text-slate-400">{$_('garden.motion_camera_help', { default: 'Optional CPU scans of retained motion footage. Needs the motion detector under Garden models; bird detection keeps its current settings.' })}</span>
            </div>
            <SettingsToggle
                checked={row.collectsMotion}
                labelledBy="{uid}-motion-label"
                describedBy="{uid}-motion-help"
                srLabel={$_('settings.beta.garden_motion_toggle', { default: 'Collect motion review photos on {camera}', values: { camera } })}
                onchange={onmotion}
            />
        </div>
    {/if}

    {#if previewOpen && preview}
        {@render preview()}
    {/if}
</li>
