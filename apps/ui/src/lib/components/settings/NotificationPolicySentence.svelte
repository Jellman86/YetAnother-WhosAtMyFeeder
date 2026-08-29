<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import type { NotificationSpeciesFilterMode } from '../../api/settings';
    import {
        enabledChannelNames,
        formatChannelList,
        presetSentenceKey,
        speciesSummaryKey,
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
        onChannelToggle,
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
        onChannelToggle: (id: PolicyChannel['id'], enabled: boolean) => void;
    } = $props();

    type Slot = 'what' | 'confidence' | 'channels';
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

    function jumpToSpeciesFilter() {
        openSlot = null;
        const section = document.getElementById(speciesSectionId);
        section?.scrollIntoView({ block: 'start', behavior: 'smooth' });
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
        'inline-flex items-baseline gap-1.5 rounded-xl border border-amber-400/70 bg-amber-50/70 px-3 py-1 font-black text-amber-700 transition-colors hover:bg-amber-100/80 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-500 dark:border-amber-500/50 dark:bg-amber-900/20 dark:text-amber-300 dark:hover:bg-amber-900/40';
    const popoverClass =
        'absolute left-0 top-full z-20 mt-2 w-72 rounded-2xl border border-slate-200 bg-white p-3 text-left shadow-xl dark:border-slate-700 dark:bg-slate-900';
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
                class="block w-full rounded-xl px-3 py-2 text-left transition-colors hover:bg-amber-50 dark:hover:bg-slate-800 {mode === preset ? 'bg-amber-100/70 dark:bg-amber-900/30' : ''}"
            >
                <span class="block text-sm font-black text-slate-900 dark:text-white">{$_(presetSentenceKey(preset))}</span>
                <span class="mt-0.5 block text-xs font-bold text-slate-500">{$_(`settings.notifications.mode_${preset}_desc`)}</span>
            </button>
            {#if preset === 'final' && mode === 'final'}
                <div class="flex items-center gap-2 px-3 pb-2 pt-1">
                    <label for="policy-video-fallback" class="text-xs font-bold text-slate-500">{$_('settings.notifications.video_fallback_timeout')}</label>
                    <input
                        id="policy-video-fallback"
                        type="number"
                        min="0"
                        step="5"
                        value={videoFallbackTimeout}
                        oninput={(event) => onVideoFallbackChange(Number(event.currentTarget.value))}
                        class="w-20 rounded-xl border border-slate-200 bg-white px-2 py-1.5 text-xs font-bold text-slate-900 dark:border-slate-700 dark:bg-slate-900/50 dark:text-white"
                    />
                    <span class="text-xs font-bold text-slate-500">{$_('settings.notifications.video_fallback_seconds')}</span>
                </div>
            {/if}
        {/each}
        {#if mode === 'custom'}
            <p class="mt-1 border-t border-slate-200 px-3 pt-2 text-xs font-bold text-slate-400 dark:border-slate-700">{$_('settings.notifications.sentence.custom_hint')}</p>
        {/if}
    </div>
{/snippet}

<div bind:this={container} class="relative">
    <div class="flex flex-wrap items-center gap-x-2 gap-y-2.5 text-lg font-bold text-slate-700 dark:text-slate-200">
        {#if mode === 'silent'}
            <span>{$_('settings.notifications.sentence.silent_lead')}</span>
            <span class="relative inline-block">
                <button
                    type="button"
                    class={chipClass}
                    aria-haspopup="dialog"
                    aria-expanded={openSlot === 'what'}
                    aria-label={$_('settings.notifications.mode_title')}
                    onclick={(event) => toggleSlot('what', event.currentTarget)}
                >
                    {whatLabel}
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
                    aria-label={$_('settings.notifications.mode_title')}
                    onclick={(event) => toggleSlot('what', event.currentTarget)}
                >
                    {whatLabel}
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
                    aria-label={$_('settings.notifications.min_confidence_label', { values: { value: confidencePercent } })}
                    onclick={(event) => toggleSlot('confidence', event.currentTarget)}
                >
                    {$_(
                        audioOnly
                            ? 'settings.notifications.sentence.confidence_chip_audio'
                            : 'settings.notifications.sentence.confidence_chip',
                        { values: { value: confidencePercent } }
                    )}
                    {@render chevron()}
                </button>
                {#if openSlot === 'confidence'}
                    <div class="{popoverClass} {alignRight ? 'left-auto right-0' : ''}" role="dialog" aria-label={$_('settings.notifications.min_confidence')}>
                        <div class="mb-2 flex items-center justify-between">
                            <label for="policy-confidence-slider" class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('settings.notifications.min_confidence')}</label>
                            <output for="policy-confidence-slider" class="rounded-lg bg-amber-500 px-2 py-0.5 text-xs font-black text-white">{confidencePercent}%</output>
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
                            class="h-2 w-full cursor-pointer appearance-none rounded-lg bg-slate-200 accent-amber-500 dark:bg-slate-700"
                        />
                        <div class="mt-1.5 flex justify-between">
                            <span class="text-xs font-bold uppercase tracking-tighter text-slate-400">{$_('settings.notifications.notify_all')}</span>
                            <span class="text-xs font-bold uppercase tracking-tighter text-slate-400">{$_('settings.notifications.high_confidence_only')}</span>
                        </div>
                        <label class="mt-2 flex cursor-pointer items-start gap-2 border-t border-slate-200 pt-2.5 dark:border-slate-700">
                            <input
                                type="checkbox"
                                checked={audioOnly}
                                onchange={(event) => onAudioOnlyChange(event.currentTarget.checked)}
                                class="mt-0.5 h-4 w-4 rounded border-slate-300 accent-amber-500 dark:border-slate-600"
                            />
                            <span>
                                <span class="block text-xs font-black text-slate-900 dark:text-white">{$_('settings.notifications.audio_only')}</span>
                                <span class="block text-xs font-bold leading-tight text-slate-500">{$_('settings.notifications.audio_only_desc')}</span>
                            </span>
                        </label>
                    </div>
                {/if}
            </span>
            <span>{$_('settings.notifications.sentence.species_join')}</span>
            <button
                type="button"
                class={chipClass}
                aria-label={$_('settings.notifications.sentence.species_jump', { values: { summary: speciesLabel } })}
                onclick={jumpToSpeciesFilter}
            >
                {speciesLabel}
            </button>
            <span>{$_('settings.notifications.sentence.channels_join')}</span>
            <span class="relative inline-block">
                <button
                    type="button"
                    class="{chipClass} {channelNames.length === 0 ? 'border-dashed' : ''}"
                    aria-haspopup="dialog"
                    aria-expanded={openSlot === 'channels'}
                    aria-label="{$_('settings.notifications.sentence.destinations')}: {channelsLabel}"
                    onclick={(event) => toggleSlot('channels', event.currentTarget)}
                >
                    {channelsLabel}
                    {@render chevron()}
                </button>
                {#if openSlot === 'channels'}
                    <div class="{popoverClass} {alignRight ? 'left-auto right-0' : ''}" role="dialog" aria-label={$_('settings.notifications.sentence.destinations')}>
                        <p class="mb-1 text-xs font-black uppercase tracking-widest text-slate-500">{$_('settings.notifications.sentence.destinations')}</p>
                        <p class="mb-2 text-xs font-bold text-slate-400">{$_('settings.notifications.sentence.channels_hint')}</p>
                        {#each channels as channel (channel.id)}
                            <label class="flex cursor-pointer items-center justify-between gap-3 rounded-xl px-2 py-2 hover:bg-slate-50 dark:hover:bg-slate-800">
                                <span class="flex items-center gap-2">
                                    <input
                                        type="checkbox"
                                        checked={channel.enabled}
                                        onchange={(event) => onChannelToggle(channel.id, event.currentTarget.checked)}
                                        class="h-4 w-4 rounded border-slate-300 accent-amber-500 dark:border-slate-600"
                                    />
                                    <span class="text-sm font-black text-slate-900 dark:text-white">{channel.label}</span>
                                </span>
                                {#if !channel.configured}
                                    <span class="text-xs font-bold text-slate-400">{$_('settings.notifications.sentence.channel_needs_setup')}</span>
                                {/if}
                            </label>
                        {/each}
                    </div>
                {/if}
            </span>
        {/if}
    </div>
</div>
