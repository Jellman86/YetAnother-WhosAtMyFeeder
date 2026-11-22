<script lang="ts">
    import { tick } from 'svelte';
    import { settingsScrollBehaviour } from '../../settings/scroll-behaviour';
    import { useDisclosure } from '../../settings/disclosures.svelte';
    import { settingsMoreId } from '../../settings/settings-more';
    import { _, locale } from 'svelte-i18n';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import type { NotificationSpeciesFilterMode } from '../../api/settings';
    import {
        enabledChannelNames,
        formatChannelList,
        presetSentenceKey,
        speciesSummaryKey,
        NOTIFICATION_CHANNELS_SECTION_ID,
        NOTIFICATION_CUSTOM_RULES_ID,
        type NotifyMode,
        type PolicyChannel,
    } from '../../settings/notification-policy';

    let {
        mode,
        onModeChange,
        minConfidence,
        onMinConfidenceChange,
        videoFallbackTimeout,
        onVideoFallbackChange,
        audioOnly,
        onAudioOnlyChange,
        speciesMode,
        speciesCount,
        speciesSectionId,
        channels,
        channelsSectionId,
    }: {
        mode: NotifyMode;
        onModeChange: (mode: NotifyMode) => void;
        minConfidence: number;
        onMinConfidenceChange: (value: number) => void;
        videoFallbackTimeout: number;
        onVideoFallbackChange: (value: number) => void;
        audioOnly: boolean;
        onAudioOnlyChange: (value: boolean) => void;
        speciesMode: NotificationSpeciesFilterMode;
        speciesCount: number;
        speciesSectionId: string;
        channels: PolicyChannel[];
        /** The channel cards, the one place a channel is switched on. */
        channelsSectionId: string;
    } = $props();

    type Slot = 'what' | 'confidence';
    let openSlot = $state<Slot | null>(null);
    let alignRight = $state(false);
    let container = $state<HTMLElement | null>(null);

    const presets: NotifyMode[] = ['standard', 'final', 'realtime', 'silent'];
    const POPOVER_WIDTH_PX = 304;

    const confidencePercent = $derived(Math.round(minConfidence * 100));
    const whatLabel = $derived($_(presetSentenceKey(mode)));
    const speciesLabel = $derived(
        $_(speciesSummaryKey(speciesMode, speciesCount), { values: { count: speciesCount } })
    );
    const channelNames = $derived(enabledChannelNames(channels));
    const channelsLabel = $derived(
        channelNames.length > 0
            ? formatChannelList(channelNames, $locale ?? 'en')
            : $_('settings.notifications.sentence.channels_none')
    );

    function toggleSlot(slot: Slot, chip: EventTarget & HTMLElement) {
        if (openSlot === slot) {
            openSlot = null;
            return;
        }
        alignRight = chip.getBoundingClientRect().left + POPOVER_WIDTH_PX > window.innerWidth - 16;
        openSlot = slot;
    }

    function choosePreset(preset: NotifyMode) {
        onModeChange(preset);
        if (preset !== 'final') openSlot = null;
    }

    // Custom rules are the switches under the sentence: the menu opens them and moves focus there.
    const customRules = useDisclosure(() => ({ id: NOTIFICATION_CUSTOM_RULES_ID }));
    async function openCustomRules(): Promise<void> {
        openSlot = null;
        // Custom rules is a choice like the others: the switches below take effect only once it is made.
        if (mode !== 'custom') onModeChange('custom');
        customRules.open = true;
        await tick();
        const first = document.querySelector<HTMLElement>(`#${NOTIFICATION_CUSTOM_RULES_ID}-content button[role="switch"]`);
        first?.scrollIntoView({ block: 'center', behavior: settingsScrollBehaviour() });
        first?.focus({ preventScroll: true });
    }

    // Species and channels are each set in one place; their words here are links to it. The species
    // filter is under Notifications' More options, which opens first, then the link waits for it to be drawn.
    const more = useDisclosure(() => ({ id: settingsMoreId('notifications') }));
    const FIELD_WAIT_FRAMES = 60;
    async function jumpTo(sectionId: string): Promise<void> {
        openSlot = null;
        if (sectionId !== NOTIFICATION_CHANNELS_SECTION_ID) more.open = true;
        for (let frame = 0; frame < FIELD_WAIT_FRAMES; frame += 1) {
            await tick();
            const section = document.getElementById(sectionId);
            if (section) {
                section.scrollIntoView({ block: 'start', behavior: settingsScrollBehaviour() });
                return;
            }
            await new Promise((resolve) => requestAnimationFrame(resolve));
        }
    }

    // Popovers close on outside pointer press or Escape; document listeners are
    // the one DOM concern Svelte state can't express, hence the $effect.
    $effect(() => {
        if (!openSlot) return;
        const onPointerDown = (event: PointerEvent) => {
            if (container && event.target instanceof Node && !container.contains(event.target)) {
                openSlot = null;
            }
        };
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') openSlot = null;
        };
        document.addEventListener('pointerdown', onPointerDown, true);
        document.addEventListener('keydown', onKeyDown, true);
        return () => {
            document.removeEventListener('pointerdown', onPointerDown, true);
            document.removeEventListener('keydown', onKeyDown, true);
        };
    });

    const chipClass =
        'focus-ring inline-flex min-h-11 items-center gap-1.5 rounded-lg bg-slate-100 px-3 font-semibold text-slate-900 transition-colors hover:bg-slate-200 dark:bg-slate-800 dark:text-white dark:hover:bg-slate-700';
    const linkClass =
        'focus-ring min-h-11 rounded-sm font-semibold text-brand-700 underline underline-offset-4 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200';
    const popoverClass =
        'absolute left-0 top-full z-20 mt-2 w-72 rounded-2xl border border-line-soft bg-surface p-3 text-left shadow-xl';

    // A chip shows only its value; the hidden words after it say which setting it opens, so the
    // name still starts with what is on screen (WCAG 2.5.3). The space is added here because a
    // translation may not start with one and markup would trim it.
    const chipContext = (setting: string): string =>
        ` ${$_('settings.notifications.sentence.chip_context', { values: { setting }, default: '({setting})' })}`;
</script>

{#snippet chevron()}
    <svg class="h-2.5 w-2.5 self-center" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
{/snippet}

{#snippet presetMenu()}
    <div class="{popoverClass} {alignRight ? 'left-auto right-0' : ''}" role="dialog" aria-label={$_('settings.notifications.mode_title')}>
        {#each presets as preset (preset)}
            <button
                type="button"
                onclick={() => choosePreset(preset)}
                class="block w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-surface-raised {mode === preset ? 'bg-brand-50 dark:bg-brand-950/60' : ''}"
            >
                <span class="block text-sm font-semibold text-slate-900 dark:text-white">{$_(presetSentenceKey(preset))}</span>
                <span class="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">{$_(`settings.notifications.mode_${preset}_desc`)}</span>
            </button>
            {#if preset === 'final' && mode === 'final'}
                <div class="flex items-center gap-2 px-3 pb-2 pt-1">
                    <label for="policy-video-fallback" class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.video_fallback_timeout')}</label>
                    <input
                        id="policy-video-fallback"
                        type="number"
                        min="0"
                        step="5"
                        value={videoFallbackTimeout}
                        oninput={(event) => onVideoFallbackChange(Number(event.currentTarget.value))}
                        class="input-base w-24"
                    />
                    <span class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.notifications.video_fallback_seconds')}</span>
                </div>
            {/if}
        {/each}
        <!-- Custom rules is the fifth choice: its triggers are switches under the sentence, and this goes to them. -->
        <button
            type="button"
            onclick={() => void openCustomRules()}
            class="mt-1 block w-full rounded-xl border-t border-line-soft px-3 py-2 text-left transition-colors hover:bg-surface-raised {mode === 'custom' ? 'bg-brand-50 dark:bg-brand-950/60' : ''}"
            data-policy-custom-rules
        >
            <span class="block text-sm font-semibold text-strong">{$_('settings.notifications.sentence.custom_open', { default: 'Custom rules' })}</span>
            <span class="mt-0.5 block text-xs text-muted">{$_('settings.notifications.sentence.custom_hint', { default: 'Your own triggers, set with the switches under this sentence. At most one alert per visit.' })}</span>
        </button>
    </div>
{/snippet}

<div bind:this={container} class="relative">
    <div class="flex flex-wrap items-center gap-x-2 gap-y-2 text-base text-slate-700 dark:text-slate-200">
        {#if mode === 'silent'}
            <span>{$_('settings.notifications.sentence.silent_lead')}</span>
            <span class="relative inline-block">
                <button
                    type="button"
                    class={chipClass}
                    aria-haspopup="dialog"
                    aria-expanded={openSlot === 'what'}
                    onclick={(event) => toggleSlot('what', event.currentTarget)}
                >
                    {whatLabel}<span class="sr-only">{chipContext($_('settings.notifications.mode_title'))}</span>
                    {@render chevron()}
                </button>
                {#if openSlot === 'what'}
                    {@render presetMenu()}
                {/if}
            </span>
            <span>{$_('settings.notifications.sentence.silent_tail')}</span>
        {:else}
            <span>{$_('settings.notifications.sentence.lead')}</span>
            <span class="relative inline-block">
                <button
                    type="button"
                    class={chipClass}
                    aria-haspopup="dialog"
                    aria-expanded={openSlot === 'what'}
                    onclick={(event) => toggleSlot('what', event.currentTarget)}
                >
                    {whatLabel}<span class="sr-only">{chipContext($_('settings.notifications.mode_title'))}</span>
                    {@render chevron()}
                </button>
                {#if openSlot === 'what'}
                    {@render presetMenu()}
                {/if}
            </span>
            <span>{$_('settings.notifications.sentence.confidence_join')}</span>
            <span class="relative inline-block">
                <button
                    type="button"
                    class={chipClass}
                    aria-haspopup="dialog"
                    aria-expanded={openSlot === 'confidence'}
                    onclick={(event) => toggleSlot('confidence', event.currentTarget)}
                >
                    {$_(
                        audioOnly
                            ? 'settings.notifications.sentence.confidence_chip_audio'
                            : 'settings.notifications.sentence.confidence_chip',
                        { values: { value: confidencePercent } }
                    )}<span class="sr-only">{chipContext($_('settings.notifications.min_confidence'))}</span>
                    {@render chevron()}
                </button>
                {#if openSlot === 'confidence'}
                    <div class="{popoverClass} {alignRight ? 'left-auto right-0' : ''}" role="dialog" aria-label={$_('settings.notifications.min_confidence')}>
                        <div class="mb-2 flex items-center justify-between">
                            <label for="policy-confidence-slider" class="text-sm font-semibold text-slate-700 dark:text-slate-200">{$_('settings.notifications.min_confidence')}</label>
                            <output for="policy-confidence-slider" class="rounded-lg bg-brand-700 px-2 py-0.5 text-xs font-semibold text-white">{confidencePercent}%</output>
                        </div>
                        <input
                            id="policy-confidence-slider"
                            type="range"
                            min="0"
                            max="1"
                            step="0.05"
                            value={minConfidence}
                            oninput={(event) => onMinConfidenceChange(Number(event.currentTarget.value))}
                            aria-valuemin="0"
                            aria-valuemax="100"
                            aria-valuenow={confidencePercent}
                            aria-valuetext="{confidencePercent} percent"
                            aria-label={$_('settings.notifications.min_confidence_label', { values: { value: confidencePercent } })}
                            class="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-brand-600 dark:bg-slate-700"
                        />
                        <div class="mt-0.5 flex justify-between gap-x-4 text-xs font-medium text-slate-600 dark:text-slate-300">
                            <span>{$_('settings.notifications.notify_all')}</span>
                            <span class="text-right">{$_('settings.notifications.high_confidence_only')}</span>
                        </div>
                        <div class="mt-2 flex items-start justify-between gap-3 border-t border-line-soft pt-2.5">
                            <span class="min-w-0">
                                <span id="policy-audio-only-label" class="block text-sm font-semibold text-slate-900 dark:text-white">{$_('settings.notifications.audio_only')}</span>
                                <span class="block text-xs leading-snug text-slate-600 dark:text-slate-400">{$_('settings.notifications.audio_only_desc')}</span>
                            </span>
                            <SettingsToggle
                                checked={audioOnly}
                                labelledBy="policy-audio-only-label"
                                srLabel={$_('settings.notifications.audio_only')}
                                onchange={onAudioOnlyChange}
                            />
                        </div>
                    </div>
                {/if}
            </span>
            <span>{$_('settings.notifications.sentence.species_join')}</span>
            <button
                type="button"
                class={linkClass}
                aria-label={$_('settings.notifications.sentence.species_jump', { values: { summary: speciesLabel } })}
                onclick={() => void jumpTo(speciesSectionId)}
                data-policy-species-link
            >
                {speciesLabel}
            </button>
            <span>{$_('settings.notifications.sentence.channels_join')}</span>
            <button
                type="button"
                class={linkClass}
                aria-label={$_('settings.notifications.sentence.channels_jump', { values: { channels: channelsLabel }, default: 'Channels: {channels}. Go to the channels' })}
                onclick={() => void jumpTo(channelsSectionId)}
                data-policy-channels-link
            >
                {channelsLabel}
            </button>
        {/if}
    </div>
</div>
