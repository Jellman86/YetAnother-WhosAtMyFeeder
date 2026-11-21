<script lang="ts">
    import { _ } from 'svelte-i18n';
    import StatusChip from '../../ui/StatusChip.svelte';
    import StateBlock from '../../ui/StateBlock.svelte';
    import type { Tone } from '../../ui/tone';
    import { systemStatusStore, verdictFor } from '../../../stores/system_status.svelte';
    import type { SubsystemKey, SubsystemVerdict } from '../../../api/status';
    import { toAppPath } from '../../../app/url-base';
    import { showsCause, statusCauseKey, statusStateKey } from '../../../settings/status-words';
    import { isTestedSubsystem, sessionTests, type ShownTestResult, type TestedSubsystem } from '../../../settings/session-tests.svelte';
    import { formatTime } from '../../../utils/datetime';
    import { SETTINGS_SECTION_PARTS, settingsPartPath, type SettingsPart, type SettingsSection } from '../../../settings/settings-route';

    interface Props {
        section: SettingsSection;
        /** Before the settings on a phone, or in its own column after them on a wide page. */
        placement: 'top' | 'side';
        onOpenPart: (part: SettingsPart) => void;
        /** Goes to a part's test where it is run, for a test the page does not offer from here. */
        onOpenTest?: (key: TestedSubsystem) => void;
        onOpenHealth?: () => void;
    }

    let { section, placement, onOpenPart, onOpenTest, onOpenHealth }: Props = $props();

    // Both placements are in the page, one hidden, so each names its own headings.
    const titleId = $derived(`settings-section-status-title-${placement}`);
    const partsTitleId = $derived(`settings-section-parts-title-${placement}`);

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

    function stateLabel(key: SubsystemKey, verdict: SubsystemVerdict | null): string {
        return $_(statusStateKey(key, verdict));
    }

    // Beside the settings there is room to say what each part is for and to offer its test. Above
    // them on a phone the column stays short: the cause is worded only where something needs a look.
    const detailed = $derived(placement === 'side');

    function causeText(key: SubsystemKey, verdict: SubsystemVerdict | null): string | null {
        if (!verdict || !showsCause(verdict, { detailed, stale: systemStatusStore.stale })) return null;
        const causeKey = statusCauseKey(key, verdict.cause);
        return causeKey ? $_(causeKey) : null;
    }

    /** A part switched off has nothing to test. */
    function testable(key: SubsystemKey, verdict: SubsystemVerdict | null): key is TestedSubsystem {
        return detailed && isTestedSubsystem(key) && verdict?.state !== 'off';
    }

    // A result says when it ran and, when it ran with values not saved yet, that it did: the chip and
    // cause above it describe the saved settings.
    function testResultText(result: ShownTestResult): string {
        const values = { time: formatTime(result.at), subject: result.subject ?? '' };
        const key = `settings.status.test.${result.passed ? 'passed' : 'failed'}${result.subject ? '_subject' : ''}${result.unsaved ? '_unsaved' : ''}`;
        return $_(key, { values });
    }

    // Each part offers its own, so the button's name says whose test it is, after its visible words.
    function testActionLabel(canRun: boolean): string {
        return canRun
            ? $_('settings.status.test.run', { default: 'Run the test' })
            : $_('settings.status.test.go', { default: 'Go to the test' });
    }

    function runOrOpenTest(key: TestedSubsystem): void {
        const run = sessionTests.runners[key];
        if (run) void run();
        else onOpenTest?.(key);
    }

    function openPart(event: MouseEvent, part: SettingsPart): void {
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        onOpenPart(part);
    }
</script>

<!-- What this section depends on, measured, then where its settings are. First on a phone; a column
     of its own beside the settings when the page has room. -->
<section class="space-y-3 text-sm" aria-labelledby={titleId} data-settings-section-status={placement}>
    <h3 id={titleId} class="font-sans text-sm font-semibold text-strong">
        {$_('settings.status.title', { default: 'Status' })}
    </h3>
    {#if keys.length === 0}
        <p class="text-muted" data-section-status-note>
            {section === 'sharing'
                ? $_('settings.status.sharing_note', { default: 'Nothing here depends on a measured connection. Sign-in and guest access are set here; each service under More options says whether it is on.' })
                : $_('settings.status.display_note', { default: 'Nothing here depends on another service. Theme, text size, language and the accessibility choices on this device change at once. Units and the defaults for everyone wait for Save.' })}
        </p>
    {:else if !snapshot}
        <StateBlock state="not-measured" variant="inline" cause={$_('settings.status.not_read', { default: 'Not measured yet: the status has not been read.' })} />
    {:else}
        <ul class={detailed ? 'space-y-4' : 'flex flex-wrap gap-2'} aria-label={$_('settings.status.title', { default: 'Status' })}>
            {#each verdicts as { key, verdict } (key)}
                {@const cause = causeText(key, verdict)}
                <li class={detailed ? 'space-y-1' : ''} data-section-status-item={key}>
                    <StatusChip
                        tone={STATE_TONE[verdict?.state ?? 'unknown']}
                        label={$_('settings.status.chip', {
                            values: { name: $_(`settings.status.subsystem.${key}`), state: stateLabel(key, verdict) },
                            default: '{name}: {state}'
                        })}
                    />
                    {#if detailed}
                        <p class="text-muted" data-section-status-purpose>{$_(`settings.status.purpose.${key}`)}</p>
                    {/if}
                    {#if cause}
                        <p class="text-ink" data-section-status-cause>{cause}</p>
                    {/if}
                    {#if testable(key, verdict)}
                        {@const shown = sessionTests.shown(key)}
                        {@const canRun = Boolean(sessionTests.runners[key])}
                        <p class="text-ink" data-section-status-test={shown ? (shown.unsaved ? 'this-visit-unsaved' : 'this-visit') : 'not-kept'}>
                            {shown ? testResultText(shown) : $_('settings.status.test.not_kept', { default: "Test results aren't kept. Run the test to check now." })}
                        </p>
                        {#if canRun || onOpenTest}
                            <button
                                type="button"
                                class="focus-ring min-h-6 rounded-sm text-left text-accent-ink underline decoration-1 underline-offset-2"
                                onclick={() => runOrOpenTest(key)}
                                aria-label={`${testActionLabel(canRun)}: ${$_(`settings.status.subsystem.${key}`)}`}
                            >
                                {testActionLabel(canRun)}
                            </button>
                        {/if}
                    {/if}
                </li>
            {/each}
        </ul>
        {#if systemStatusStore.stale}
            <StateBlock state="stale" variant="inline" cause={$_('settings.status.stale', { default: 'This reading is out of date: no newer one has arrived.' })} />
        {/if}
    {/if}
    {#if onOpenHealth && keys.length > 0}
        <button type="button" class="focus-ring min-h-6 rounded-sm text-left text-accent-ink underline decoration-1 underline-offset-2" onclick={onOpenHealth}>
            {$_('settings.status.open_health', { default: 'Details in Health' })}
        </button>
    {/if}

    <!-- Above the settings on a phone the parts would push the work down, and the section list
         already leads there, so they are listed only in the column beside them. -->
    {#if placement === 'side' && parts.length > 1}
        <nav aria-labelledby={partsTitleId} class="space-y-1 border-t border-line-soft pt-3" data-settings-section-parts>
            <h3 id={partsTitleId} class="font-sans text-sm font-semibold text-strong">
                {$_('settings.status.in_this_section', { default: 'In this section' })}
            </h3>
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
