<script lang="ts">
    import { _ } from 'svelte-i18n';
    import StatusChip from '../../ui/StatusChip.svelte';
    import StateBlock from '../../ui/StateBlock.svelte';
    import type { Tone } from '../../ui/tone';
    import { systemStatusStore, verdictFor } from '../../../stores/system_status.svelte';
    import type { SubsystemKey, SubsystemVerdict } from '../../../api/status';
    import { toAppPath } from '../../../app/url-base';
    import { SETTINGS_SECTION_PARTS, settingsPartPath, type SettingsPart, type SettingsSection } from '../../../settings/settings-route';

    interface Props {
        section: SettingsSection;
        onOpenPart: (part: SettingsPart) => void;
        onOpenHealth?: () => void;
    }

    let { section, onOpenPart, onOpenHealth }: Props = $props();

    /** What each section depends on, as the live status measures it. Display depends on nothing. */
    const STATUS_KEYS: Readonly<Record<SettingsSection, readonly SubsystemKey[]>> = {
        cameras: ['frigate', 'mqtt', 'audio'],
        identification: ['classifier', 'finder'],
        alerts: ['notifications'],
        sharing: [],
        storage: ['storage'],
        display: []
    };

    const STATE_TONE: Readonly<Record<SubsystemVerdict['state'], Tone>> = {
        ok: 'ok',
        degraded: 'attention',
        error: 'fail',
        off: 'neutral',
        unknown: 'neutral'
    };

    const keys = $derived(STATUS_KEYS[section]);
    const snapshot = $derived(systemStatusStore.snapshot);
    const verdicts = $derived(keys.map((key) => ({ key, verdict: verdictFor(snapshot, key) })));
    const parts = $derived(SETTINGS_SECTION_PARTS[section]);

    function stateLabel(state: SubsystemVerdict['state']): string {
        return $_(`settings.status.state.${state}`);
    }

    function openPart(event: MouseEvent, part: SettingsPart): void {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        onOpenPart(part);
    }
</script>

<!-- What this section depends on, measured, then where its settings are. First on a phone; a column
     of its own beside the settings when the page has room. -->
<section class="space-y-3 text-sm" aria-labelledby="settings-section-status-title" data-settings-section-status>
    <h2 id="settings-section-status-title" class="text-sm font-semibold text-strong">
        {$_('settings.status.title', { default: 'Status' })}
    </h2>
    {#if keys.length === 0}
        <p class="text-muted" data-section-status-note>
            {section === 'sharing'
                ? $_('settings.status.sharing_note', { default: 'Each service below says whether it is on. Sign-in and guest access are set here too.' })
                : $_('settings.status.display_note', { default: 'Nothing here depends on another service. Theme, text size and language change at once on this device.' })}
        </p>
    {:else if !snapshot}
        <StateBlock state="not-measured" variant="inline" cause={$_('settings.status.not_read', { default: 'Not measured yet: the status has not been read.' })} />
    {:else}
        <ul class="flex flex-wrap gap-2" aria-label={$_('settings.status.title', { default: 'Status' })}>
            {#each verdicts as { key, verdict } (key)}
                <li>
                    <StatusChip
                        tone={STATE_TONE[verdict?.state ?? 'unknown']}
                        label={$_('settings.status.chip', {
                            values: { name: $_(`settings.status.subsystem.${key}`), state: stateLabel(verdict?.state ?? 'unknown') },
                            default: '{name}: {state}'
                        })}
                        title={verdict?.cause}
                    />
                </li>
            {/each}
        </ul>
        {#if systemStatusStore.stale}
            <StateBlock state="stale" variant="inline" cause={$_('settings.status.stale', { default: 'This reading is out of date: no newer one has arrived.' })} />
        {/if}
    {/if}
    {#if onOpenHealth && keys.length > 0}
        <button type="button" class="focus-ring min-h-6 rounded-sm text-left font-semibold text-accent-ink underline decoration-1 underline-offset-2" onclick={onOpenHealth}>
            {$_('settings.status.open_health', { default: 'Details in Health' })}
        </button>
    {/if}

    {#if parts.length > 1}
        <nav aria-labelledby="settings-section-parts-title" class="space-y-1 border-t border-line-soft pt-3" data-settings-section-parts>
            <h2 id="settings-section-parts-title" class="text-sm font-semibold text-strong">
                {$_('settings.status.in_this_section', { default: 'In this section' })}
            </h2>
            <ul class="space-y-0.5">
                {#each parts as part (part)}
                    <li>
                        <a
                            href={toAppPath(settingsPartPath(part))}
                            class="focus-ring inline-flex min-h-6 items-center rounded-sm text-accent-ink underline decoration-1 underline-offset-2"
                            onclick={(event) => openPart(event, part)}
                        >{$_(`settings.tabs.${part}`)}</a>
                    </li>
                {/each}
            </ul>
        </nav>
    {/if}
</section>
