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

    // min-w-0 lets an option's words wrap inside a narrow column at large text sizes instead of
    // pushing past the row's edge.
    const choiceClass = 'relative flex min-h-11 min-w-0 items-center justify-center gap-1.5 rounded-md px-2 py-1 text-center text-xs font-semibold transition-colors';

    function stateClass(checked: boolean, blocked: boolean): string {
        if (checked) return 'bg-brand-700 text-white';
        if (blocked) return 'cursor-not-allowed text-slate-500 line-through decoration-slate-400 dark:text-slate-400';
        return 'cursor-pointer text-slate-700 hover:bg-surface-raised dark:text-slate-200';
    }
</script>

<li
    class="space-y-3 break-words rounded-xl border p-3 {row.presence === 'missing' ? 'border-attention-500/50 bg-attention-500/10' : 'border-line-soft bg-surface-raised/40'}"
    data-camera-watch={camera}
>
    <div class="flex flex-wrap items-start justify-between gap-2">
        <div class="min-w-0 flex-1 basis-24 pt-2">
            <p class="break-all text-sm font-bold text-slate-900 dark:text-white">{camera}</p>
            {#if row.presence === 'missing'}
                <p class="mt-1 flex items-center gap-1.5 text-xs font-semibold text-attention-800 dark:text-attention-200" data-camera-missing>
                    <span class="h-2 w-2 shrink-0 rounded-full bg-attention-500" aria-hidden="true"></span>
                    {$_('settings.cameras.not_found', { default: 'Not found in Frigate' })}
                </p>
                <p class="mt-0.5 text-xs text-slate-700 dark:text-slate-300">
                    {$_('settings.cameras.not_found_help', { default: 'Frigate does not list this camera now. Its choices are kept until you change them; choose Off to remove it.' })}
                </p>
            {/if}
        </div>
        {#if row.presence !== 'missing'}
            <button
                type="button"
                class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-slate-500 transition hover:bg-white hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-brand-300"
                aria-label={$_('settings.cameras.preview', { default: 'Preview {camera}', values: { camera } })}
                aria-expanded={previewOpen}
                aria-describedby={previewUnavailableId}
                disabled={!!previewUnavailableId}
                onclick={onpreview}
            >
                <svg class="h-4 w-4 transition-transform {previewOpen ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
        {/if}
    </div>

    <div class="space-y-1.5">
        <p class="eyebrow" aria-hidden="true">{$_('settings.cameras.watch_for_label', { default: 'Watch for' })}</p>
        <div
            role="radiogroup"
            aria-label={$_('settings.cameras.watch_for', { default: '{camera}: watch for', values: { camera } })}
            aria-describedby={blockReasons.length > 0 ? `${uid}-reason` : undefined}
            class="grid grid-cols-2 gap-1 rounded-lg border border-line bg-surface p-1 {gardenEnabled ? 'sm:grid-cols-4' : ''}"
        >
            {#each modeOptions as option (option.value)}
                {@const checked = row.mode === option.value}
                {@const blocked = !!row.blocked[option.value]}
                <label class="{choiceClass} {stateClass(checked, blocked)} focus-within:ring-2 focus-within:ring-brand-500 focus-within:ring-offset-1 dark:focus-within:ring-offset-slate-900">
                    <input
                        class="sr-only"
                        type="radio"
                        name="{uid}-mode"
                        value={option.value}
                        {checked}
                        disabled={blocked}
                        onchange={() => onmode(option.value)}
                    />
                    {#if checked}
                        <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 7" /></svg>
                    {/if}
                    <span class="min-w-0 break-words">{option.label}</span>
                </label>
            {/each}
        </div>
        {#if blockReasons.length > 0}
            <div id="{uid}-reason" class="space-y-0.5 text-xs text-slate-700 dark:text-slate-300" data-camera-watch-reason>
                {#each blockReasons as reason (reason)}
                    <p>{reason}</p>
                {/each}
            </div>
        {/if}
    </div>

    {#if watchesBirds}
        <div class="space-y-1.5 border-t border-line-soft pt-3" data-camera-role>
            <p class="eyebrow" aria-hidden="true">{$_('settings.cameras.role_label', { default: 'Role' })}</p>
            <div
                role="radiogroup"
                aria-label={$_('settings.cameras.role_group', { default: '{camera}: bird role', values: { camera } })}
                aria-describedby="{uid}-role-help"
                class="grid grid-cols-2 gap-1 rounded-lg border border-line bg-surface p-1"
            >
                {#each roleOptions as option (option.value)}
                    {@const checked = row.role === option.value}
                    <label class="{choiceClass} {stateClass(checked, false)} focus-within:ring-2 focus-within:ring-brand-500 focus-within:ring-offset-1 dark:focus-within:ring-offset-slate-900">
                        <input
                            class="sr-only"
                            type="radio"
                            name="{uid}-role"
                            value={option.value}
                            {checked}
                            onchange={() => onrole(option.value)}
                        />
                        {#if checked}
                            <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 4 4L19 7" /></svg>
                        {/if}
                        <span class="min-w-0 break-words">{option.label}</span>
                    </label>
                {/each}
            </div>
            <p id="{uid}-role-help" class="text-xs text-slate-600 dark:text-slate-400">{roleHelp}</p>
        </div>
    {/if}

    {#if watchesGarden}
        <div class="space-y-1 border-t border-line-soft pt-3" data-camera-motion>
            <label class="flex min-h-11 cursor-pointer items-center gap-3 rounded-md px-1 focus-within:ring-2 focus-within:ring-brand-500">
                <input
                    type="checkbox"
                    class="h-5 w-5 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    checked={row.collectsMotion}
                    aria-label={$_('settings.beta.garden_motion_toggle', { default: 'Collect motion review photos on {camera}', values: { camera } })}
                    aria-describedby="{uid}-motion-help"
                    onchange={(event) => onmotion(event.currentTarget.checked)}
                />
                <span class="min-w-0 break-words text-sm font-semibold text-slate-900 dark:text-white">{$_('garden.motion_toggle', { default: 'Collect motion review photos' })}</span>
            </label>
            <p id="{uid}-motion-help" class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.motion_camera_help', { default: 'Optional CPU scans of retained motion footage. Needs the motion detector under Garden models; bird detection keeps its current settings.' })}</p>
        </div>
    {/if}

    {#if previewOpen && preview}
        {@render preview()}
    {/if}
</li>
