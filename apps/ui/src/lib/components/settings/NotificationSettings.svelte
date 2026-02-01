<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { TestEmailRequest, TestEmailResponse, OAuthAuthorizeResponse } from '../../api';

    function extractErrorMessage(error: any, fallback: string) {
        const message = error?.message || fallback;
        if (typeof message === 'string' && message.trim().startsWith('{')) {
            try {
                const parsed = JSON.parse(message);
                return parsed.detail || parsed.message || fallback;
            } catch {
                return message;
            }
        }
        return message;
    }

    let emailTestError = $state<string | null>(null);
    let emailTestSuccess = $state<string | null>(null);

    // Props
    let {
        // Global filters
        notifyMinConfidence = $bindable(0.7),
        notifyAudioOnly = $bindable(false),
        notifySpeciesWhitelist = $bindable<string[]>([]),
        newSpecies = $bindable(''),
        notifyMode = $bindable<'silent' | 'final' | 'standard' | 'realtime' | 'custom'>('standard'),
        notifyOnInsert = $bindable(true),
        notifyOnUpdate = $bindable(false),
        notifyDelayUntilVideo = $bindable(false),
        notifyVideoFallbackTimeout = $bindable(45),
        notifyCooldownMinutes = $bindable(0),

        // Discord
        discordEnabled = $bindable(false),
        discordWebhook = $bindable(''),
        discordWebhookSaved = $bindable(false),
        discordBotName = $bindable('YA-WAMF Bird Bot'),

        // Pushover
        pushoverEnabled = $bindable(false),
        pushoverUserKey = $bindable(''),
        pushoverUserSaved = $bindable(false),
        pushoverApiToken = $bindable(''),
        pushoverTokenSaved = $bindable(false),
        pushoverPriority = $bindable(0),

        // Telegram
        telegramEnabled = $bindable(false),
        telegramBotToken = $bindable(''),
        telegramTokenSaved = $bindable(false),
        telegramChatId = $bindable(''),
        telegramChatIdSaved = $bindable(false),

        // Email
        emailEnabled = $bindable(false),
        emailUseOAuth = $bindable(true),
        emailConnectedEmail = $bindable<string | null>(null),
        emailOAuthProvider = $bindable<string | null>(null),
        emailOnlyOnEnd = $bindable(false),
        emailSmtpHost = $bindable(''),
        emailSmtpPort = $bindable(587),
        emailSmtpUseTls = $bindable(true),
        emailSmtpUsername = $bindable(''),
        emailSmtpPassword = $bindable(''),
        emailSmtpPasswordSaved = $bindable(false),
        emailFromEmail = $bindable(''),
        emailToEmail = $bindable(''),
        emailIncludeSnapshot = $bindable(true),
        emailDashboardUrl = $bindable(''),

        // Testing state
        testingNotification = $bindable<Record<string, boolean>>({}),

        // Functions
        addSpeciesToWhitelist,
        removeSpeciesFromWhitelist,
        sendTestDiscord,
        sendTestPushover,
        sendTestTelegram,
        sendTestEmail,
        initiateGmailOAuth,
        initiateOutlookOAuth,
        disconnectEmailOAuth
    }: {
        notifyMinConfidence: number;
        notifyAudioOnly: boolean;
        notifySpeciesWhitelist: string[];
        newSpecies: string;
        notifyMode: 'silent' | 'final' | 'standard' | 'realtime' | 'custom';
        notifyOnInsert: boolean;
        notifyOnUpdate: boolean;
        notifyDelayUntilVideo: boolean;
        notifyVideoFallbackTimeout: number;
        notifyCooldownMinutes: number;
        discordEnabled: boolean;
        discordWebhook: string;
        discordWebhookSaved: boolean;
        discordBotName: string;
        pushoverEnabled: boolean;
        pushoverUserKey: string;
        pushoverUserSaved: boolean;
        pushoverApiToken: string;
        pushoverTokenSaved: boolean;
        pushoverPriority: number;
        telegramEnabled: boolean;
        telegramBotToken: string;
        telegramTokenSaved: boolean;
        telegramChatId: string;
        telegramChatIdSaved: boolean;
        emailEnabled: boolean;
        emailUseOAuth: boolean;
        emailConnectedEmail: string | null;
        emailOAuthProvider: string | null;
        emailOnlyOnEnd: boolean;
        emailSmtpHost: string;
        emailSmtpPort: number;
        emailSmtpUseTls: boolean;
        emailSmtpUsername: string;
        emailSmtpPassword: string;
        emailSmtpPasswordSaved: boolean;
        emailFromEmail: string;
        emailToEmail: string;
        emailIncludeSnapshot: boolean;
        emailDashboardUrl: string;
        testingNotification: Record<string, boolean>;
        addSpeciesToWhitelist: () => void;
        removeSpeciesFromWhitelist: (species: string) => void;
        sendTestDiscord: () => Promise<void>;
        sendTestPushover: () => Promise<void>;
        sendTestTelegram: () => Promise<void>;
        sendTestEmail: (request?: TestEmailRequest) => Promise<TestEmailResponse>;
        initiateGmailOAuth: () => Promise<OAuthAuthorizeResponse>;
        initiateOutlookOAuth: () => Promise<OAuthAuthorizeResponse>;
        disconnectEmailOAuth: (provider: 'gmail' | 'outlook') => Promise<{ message: string }>;
    } = $props();

    let showAdvanced = $state(false);

    const notificationsEnabled = $derived(
        notifyMode === 'custom' ? (notifyOnInsert || notifyOnUpdate) : notifyMode !== 'silent'
    );

    function applyPreset(mode: typeof notifyMode) {
        if (mode === 'silent') {
            notifyOnInsert = false;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'final') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = true;
            return;
        }
        if (mode === 'realtime') {
            notifyOnInsert = true;
            notifyOnUpdate = true;
            notifyDelayUntilVideo = false;
            return;
        }
        if (mode === 'standard') {
            notifyOnInsert = true;
            notifyOnUpdate = false;
            notifyDelayUntilVideo = false;
        }
    }

    function setMode(mode: typeof notifyMode) {
        notifyMode = mode;
        if (mode !== 'custom') {
            showAdvanced = false;
            applyPreset(mode);
        }
    }

    function setCustom(updateFn: () => void) {
        notifyMode = 'custom';
        updateFn();
    }
</script>

<div class="space-y-6">
    <!-- Global Notification Filters -->
    <section class="bg-gradient-to-br from-amber-50/50 to-orange-50/50 dark:from-slate-800/30 dark:to-amber-900/10 rounded-3xl border border-amber-200/50 dark:border-amber-700/30 p-8 shadow-sm backdrop-blur-md">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 dark:text-amber-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.notifications.global_filters')}</h3>
        </div>

        <div class="space-y-6">
            <!-- Delivery Policy -->
            <div class="p-4 rounded-2xl bg-white/60 dark:bg-slate-800/40 border border-amber-200/30 dark:border-amber-700/20">
                <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-500 mb-4">{$_('settings.notifications.delivery_policy')}</h4>
                {#if !notificationsEnabled}
                    <div class="mb-4 rounded-2xl border border-amber-300/60 bg-amber-100/70 px-4 py-3 text-[11px] font-bold text-amber-900 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200">
                        {$_('settings.notifications.enable_notify_hint', { default: 'Notifications are currently off. Enable "Notify on new detections" or "Notify on updates" to send any alerts.' })}
                    </div>
                {/if}
                <div class="mb-4 rounded-2xl border border-slate-200/70 bg-white/70 px-4 py-3 text-[11px] font-bold text-slate-600 dark:border-slate-700/60 dark:bg-slate-900/40 dark:text-slate-300">
                    {$_('settings.notifications.confirmation_policy')}
                </div>
                <div class="space-y-4">
                    <div>
                        <p class="text-[11px] font-black uppercase tracking-[0.2em] text-slate-500">{$_('settings.notifications.mode_title')}</p>
                        <p class="text-xs text-slate-500 mt-1">{$_('settings.notifications.mode_desc')}</p>
                    </div>
                    <div class="grid gap-3 md:grid-cols-2">
                        <button
                            type="button"
                            onclick={() => setMode('final')}
                            class="rounded-2xl border px-4 py-3 text-left transition-all duration-200 {notifyMode === 'final' ? 'border-amber-400 bg-amber-50/80 shadow-sm' : 'border-slate-200/70 bg-white/70 hover:border-amber-200 dark:border-slate-700/60 dark:bg-slate-900/40'}"
                        >
                            <p class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.mode_final')}</p>
                            <p class="text-[10px] font-bold text-slate-500 mt-1">{$_('settings.notifications.mode_final_desc')}</p>
                        </button>
                        <button
                            type="button"
                            onclick={() => setMode('standard')}
                            class="rounded-2xl border px-4 py-3 text-left transition-all duration-200 {notifyMode === 'standard' ? 'border-amber-400 bg-amber-50/80 shadow-sm' : 'border-slate-200/70 bg-white/70 hover:border-amber-200 dark:border-slate-700/60 dark:bg-slate-900/40'}"
                        >
                            <p class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.mode_standard')}</p>
                            <p class="text-[10px] font-bold text-slate-500 mt-1">{$_('settings.notifications.mode_standard_desc')}</p>
                        </button>
                        <button
                            type="button"
                            onclick={() => setMode('realtime')}
                            class="rounded-2xl border px-4 py-3 text-left transition-all duration-200 {notifyMode === 'realtime' ? 'border-amber-400 bg-amber-50/80 shadow-sm' : 'border-slate-200/70 bg-white/70 hover:border-amber-200 dark:border-slate-700/60 dark:bg-slate-900/40'}"
                        >
                            <p class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.mode_realtime')}</p>
                            <p class="text-[10px] font-bold text-slate-500 mt-1">{$_('settings.notifications.mode_realtime_desc')}</p>
                        </button>
                        <button
                            type="button"
                            onclick={() => setMode('silent')}
                            class="rounded-2xl border px-4 py-3 text-left transition-all duration-200 {notifyMode === 'silent' ? 'border-amber-400 bg-amber-50/80 shadow-sm' : 'border-slate-200/70 bg-white/70 hover:border-amber-200 dark:border-slate-700/60 dark:bg-slate-900/40'}"
                        >
                            <p class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.mode_silent')}</p>
                            <p class="text-[10px] font-bold text-slate-500 mt-1">{$_('settings.notifications.mode_silent_desc')}</p>
                        </button>
                    </div>

                    <div class="flex items-center justify-between gap-4">
                        <div>
                            <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.advanced_title')}</span>
                            <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.advanced_desc')}</span>
                        </div>
                        <button
                            type="button"
                            onclick={() => {
                                showAdvanced = !showAdvanced;
                                if (showAdvanced) notifyMode = 'custom';
                            }}
                            class="px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border {showAdvanced ? 'border-amber-400 text-amber-700 bg-amber-50' : 'border-slate-200 text-slate-500 bg-white/70 dark:border-slate-700 dark:text-slate-300 dark:bg-slate-900/40'}"
                        >
                            {showAdvanced ? $_('settings.notifications.advanced_on') : $_('settings.notifications.advanced_off')}
                        </button>
                    </div>

                    {#if showAdvanced}
                        <div class="space-y-4 border-t border-dashed border-slate-200/70 pt-4">
                            <div class="flex items-center justify-between gap-4">
                                <div id="notify-insert-label">
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.notify_on_insert')}</span>
                                    <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.notify_on_insert_desc')}</span>
                                </div>
                                <button
                                    role="switch"
                                    aria-checked={notifyOnInsert}
                                    aria-labelledby="notify-insert-label"
                                    onclick={() => setCustom(() => notifyOnInsert = !notifyOnInsert)}
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            setCustom(() => notifyOnInsert = !notifyOnInsert);
                                        }
                                    }}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {notifyOnInsert ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="sr-only">{$_('settings.notifications.notify_on_insert')}</span>
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {notifyOnInsert ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>

                            <div class="flex items-center justify-between gap-4">
                                <div id="notify-update-label">
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.notify_on_update')}</span>
                                    <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.notify_on_update_desc')}</span>
                                </div>
                                <button
                                    role="switch"
                                    aria-checked={notifyOnUpdate}
                                    aria-labelledby="notify-update-label"
                                    onclick={() => setCustom(() => notifyOnUpdate = !notifyOnUpdate)}
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            setCustom(() => notifyOnUpdate = !notifyOnUpdate);
                                        }
                                    }}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {notifyOnUpdate ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="sr-only">{$_('settings.notifications.notify_on_update')}</span>
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {notifyOnUpdate ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>

                            <div class="flex items-center justify-between gap-4 {notificationsEnabled ? '' : 'opacity-50'}">
                                <div id="notify-delay-label">
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.delay_until_video')}</span>
                                    <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.delay_until_video_desc')}</span>
                                </div>
                                <button
                                    role="switch"
                                    aria-checked={notifyDelayUntilVideo}
                                    aria-disabled={!notificationsEnabled}
                                    aria-labelledby="notify-delay-label"
                                    onclick={() => {
                                        if (!notificationsEnabled) return;
                                        setCustom(() => notifyDelayUntilVideo = !notifyDelayUntilVideo);
                                    }}
                                    onkeydown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            if (!notificationsEnabled) return;
                                            setCustom(() => notifyDelayUntilVideo = !notifyDelayUntilVideo);
                                        }
                                    }}
                                    class="relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {notificationsEnabled ? 'cursor-pointer' : 'cursor-not-allowed'} {notifyDelayUntilVideo && notificationsEnabled ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-600'}"
                                >
                                    <span class="sr-only">{$_('settings.notifications.delay_until_video')}</span>
                                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {notifyDelayUntilVideo ? 'translate-x-5' : 'translate-x-0'}"></span>
                                </button>
                            </div>

                            <div class="flex items-center justify-between gap-4">
                                <div>
                                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.video_fallback_timeout')}</span>
                                    <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.video_fallback_timeout_desc')}</span>
                                </div>
                                <div class="flex items-center gap-2">
                                    <input
                                        type="number"
                                        min="0"
                                        step="5"
                                        bind:value={notifyVideoFallbackTimeout}
                                        disabled={!notifyDelayUntilVideo || !notificationsEnabled}
                                        class="w-24 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs disabled:opacity-50"
                                        aria-label={$_('settings.notifications.video_fallback_timeout')}
                                    />
                                    <span class="text-[10px] font-bold text-slate-500">{$_('settings.notifications.video_fallback_seconds')}</span>
                                </div>
                            </div>

                    <div class="flex items-center justify-between gap-4">
                        <div>
                            <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.cooldown')}</span>
                            <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.cooldown_desc')}</span>
                        </div>
                        <div class="flex items-center gap-2">
                            <input
                                type="number"
                                min="0"
                                step="1"
                                bind:value={notifyCooldownMinutes}
                                class="w-24 px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs"
                                aria-label={$_('settings.notifications.cooldown')}
                            />
                            <span class="text-[10px] font-bold text-slate-500">{$_('settings.notifications.cooldown_unit')}</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Minimum Confidence -->
            <div>
                <div class="flex justify-between mb-4">
                    <label for="notify-confidence-slider" class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.min_confidence')}</label>
                    <output for="notify-confidence-slider" class="px-2 py-1 bg-amber-500 text-white text-[10px] font-black rounded-lg">{(notifyMinConfidence * 100).toFixed(0)}%</output>
                </div>
                <input
                    id="notify-confidence-slider"
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    bind:value={notifyMinConfidence}
                    aria-valuemin="0"
                    aria-valuemax="100"
                    aria-valuenow={Math.round(notifyMinConfidence * 100)}
                    aria-valuetext="{(notifyMinConfidence * 100).toFixed(0)} percent"
                    aria-label="Notification minimum confidence: {(notifyMinConfidence * 100).toFixed(0)}%"
                    class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500"
                />
                <div class="flex justify-between mt-2">
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.notifications.notify_all')}</span>
                    <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.notifications.high_confidence_only')}</span>
                </div>
            </div>

            <!-- Audio Only Toggle -->
            <div class="p-4 rounded-2xl bg-white/60 dark:bg-slate-800/40 border border-amber-200/30 dark:border-amber-700/20 flex items-center justify-between gap-4">
                <div id="audio-only-label">
                    <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.notifications.audio_only')}</span>
                    <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.notifications.audio_only_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={notifyAudioOnly}
                    aria-labelledby="audio-only-label"
                    onclick={() => notifyAudioOnly = !notifyAudioOnly}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            notifyAudioOnly = !notifyAudioOnly;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {notifyAudioOnly ? 'bg-amber-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.notifications.audio_only')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {notifyAudioOnly ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <!-- Species Whitelist -->
            <div class="pt-4 border-t border-amber-200/50 dark:border-amber-700/30">
                <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-500 mb-4">{$_('settings.notifications.species_whitelist')}</h4>
                <div class="flex gap-2 mb-4">
                    <input
                        bind:value={newSpecies}
                        onkeydown={(e) => e.key === 'Enter' && addSpeciesToWhitelist()}
                        placeholder={$_('settings.notifications.species_placeholder')}
                        aria-label="New species for whitelist"
                        class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                    <button
                        onclick={addSpeciesToWhitelist}
                        disabled={!newSpecies.trim()}
                        aria-label="Add species to whitelist"
                        class="px-6 py-3 bg-amber-500 hover:bg-amber-600 text-white text-xs font-black uppercase tracking-widest rounded-2xl transition-all disabled:opacity-50"
                    >
                        {$_('common.add')}
                    </button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each notifySpeciesWhitelist as species}
                        <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-amber-200 dark:border-amber-700/50 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                            {species}
                            <button
                                onclick={() => removeSpeciesFromWhitelist(species)}
                                aria-label="Remove {species} from whitelist"
                                class="text-slate-400 hover:text-red-500 transition-colors"
                            >
                                ✕
                            </button>
                        </span>
                    {/each}
                    {#if notifySpeciesWhitelist.length === 0}
                        <p class="text-xs font-bold text-slate-400 italic">{$_('settings.notifications.no_species_filter')}</p>
                    {/if}
                </div>
            </div>
        </div>
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Discord -->
        <section class="card-base rounded-3xl p-8 backdrop-blur-md">
            <div class="flex items-center justify-between mb-6">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                        <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M20.317 4.37a19.791 19.791 0 00-4.885-1.515.074.074 0 00-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 00-5.487 0 12.64 12.64 0 00-.617-1.25.077.077 0 00-.079-.037A19.736 19.736 0 003.677 4.37a.07.07 0 00-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 00.031.057 19.9 19.9 0 005.993 3.03.078.078 0 00.084-.028 14.09 14.09 0 001.226-1.994.076.076 0 00-.041-.106 13.107 13.107 0 01-1.872-.892.077.077 0 01-.008-.128 10.2 10.2 0 00.372-.292.074.074 0 01.077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 01.078.01c.12.098.246.198.373.292a.077.077 0 01-.006.127 12.299 12.299 0 01-1.873.892.077.077 0 00-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 00.084.028 19.839 19.839 0 006.002-3.03.077.077 0 00.032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 00-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
                        </svg>
                    </div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.discord.title')}</h3>
                </div>
                <button
                    role="switch"
                    aria-checked={discordEnabled}
                    onclick={() => discordEnabled = !discordEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            discordEnabled = !discordEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {discordEnabled ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.discord.title')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {discordEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="space-y-4">
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label for="discord-webhook" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.discord.webhook_url')}</label>
                        {#if discordWebhookSaved}
                            <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                        {/if}
                    </div>
                    <input
                        id="discord-webhook"
                        type="url"
                        bind:value={discordWebhook}
                        placeholder={$_('settings.discord.webhook_placeholder')}
                        aria-label="Discord webhook URL"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <label for="discord-botname" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.discord.bot_username')}</label>
                    <input
                        id="discord-botname"
                        type="text"
                        bind:value={discordBotName}
                        placeholder="YA-WAMF Bird Bot"
                        aria-label="Discord bot username"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <button
                    onclick={sendTestDiscord}
                    disabled={testingNotification['discord'] || (!discordWebhook && !discordWebhookSaved)}
                    aria-label="Send test Discord notification"
                    class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
                >
                    {testingNotification['discord'] ? $_('settings.discord.test_sending') : $_('settings.discord.test_notification')}
                </button>
            </div>
        </section>

        <!-- Pushover -->
        <section class="card-base rounded-3xl p-8 backdrop-blur-md">
            <div class="flex items-center justify-between mb-6">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" /></svg>
                    </div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.pushover.title')}</h3>
                </div>
                <button
                    role="switch"
                    aria-checked={pushoverEnabled}
                    onclick={() => pushoverEnabled = !pushoverEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            pushoverEnabled = !pushoverEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {pushoverEnabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.pushover.title')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {pushoverEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="space-y-4">
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label for="pushover-userkey" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.pushover.user_key')}</label>
                        {#if pushoverUserSaved}
                            <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                        {/if}
                    </div>
                    <input
                        id="pushover-userkey"
                        type="text"
                        bind:value={pushoverUserKey}
                        placeholder={$_('settings.pushover.user_key_placeholder')}
                        aria-label="Pushover user key"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label for="pushover-apitoken" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.pushover.api_token')}</label>
                        {#if pushoverTokenSaved}
                            <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                        {/if}
                    </div>
                    <input
                        id="pushover-apitoken"
                        type="text"
                        bind:value={pushoverApiToken}
                        placeholder={$_('settings.pushover.api_token_placeholder')}
                        aria-label="Pushover API token"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <label for="pushover-priority" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.pushover.priority')}</label>
                    <select
                        id="pushover-priority"
                        bind:value={pushoverPriority}
                        aria-label="Pushover priority"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    >
                        <option value={-2}>{$_('settings.pushover.priority_lowest')}</option>
                        <option value={-1}>{$_('settings.pushover.priority_low')}</option>
                        <option value={0}>{$_('settings.pushover.priority_normal')}</option>
                        <option value={1}>{$_('settings.pushover.priority_high')}</option>
                        <option value={2}>{$_('settings.pushover.priority_emergency')}</option>
                    </select>
                </div>
                <button
                    onclick={sendTestPushover}
                    disabled={testingNotification['pushover'] || (!pushoverUserKey && !pushoverUserSaved) || (!pushoverApiToken && !pushoverTokenSaved)}
                    aria-label="Send test Pushover notification"
                    class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-blue-500 hover:bg-blue-600 text-white transition-all shadow-lg shadow-blue-500/20 disabled:opacity-50"
                >
                    {testingNotification['pushover'] ? $_('settings.pushover.test_sending') : $_('settings.pushover.test_notification')}
                </button>
            </div>
        </section>

        <!-- Telegram -->
        <section class="card-base rounded-3xl p-8 backdrop-blur-md">
            <div class="flex items-center justify-between mb-6">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl bg-sky-500/10 flex items-center justify-center text-sky-600 dark:text-sky-400">
                        <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 0C5.373 0 0 5.373 0 12s5.373 12 12 12 12-5.373 12-12S18.627 0 12 0zm5.562 8.161c-.18 1.897-.962 6.502-1.359 8.627-.168.9-.5 1.201-.82 1.23-.697.064-1.226-.461-1.901-.903-1.056-.693-1.653-1.124-2.678-1.8-1.185-.781-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.831-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                        </svg>
                    </div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.telegram.title')}</h3>
                </div>
                <button
                    role="switch"
                    aria-checked={telegramEnabled}
                    onclick={() => telegramEnabled = !telegramEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            telegramEnabled = !telegramEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {telegramEnabled ? 'bg-sky-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.telegram.title')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {telegramEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="space-y-4">
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label for="telegram-bottoken" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.telegram.bot_token')}</label>
                        {#if telegramTokenSaved}
                            <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                        {/if}
                    </div>
                    <input
                        id="telegram-bottoken"
                        type="password"
                        bind:value={telegramBotToken}
                        placeholder={$_('settings.telegram.bot_token_placeholder')}
                        aria-label="Telegram bot token"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label for="telegram-chatid" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.telegram.chat_id')}</label>
                        {#if telegramChatIdSaved}
                            <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                        {/if}
                    </div>
                    <input
                        id="telegram-chatid"
                        type="text"
                        bind:value={telegramChatId}
                        placeholder={$_('settings.telegram.chat_id_placeholder')}
                        aria-label="Telegram chat ID"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                </div>
                <button
                    onclick={sendTestTelegram}
                    disabled={testingNotification['telegram'] || (!telegramBotToken && !telegramTokenSaved) || (!telegramChatId && !telegramChatIdSaved)}
                    aria-label="Send test Telegram notification"
                    class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-sky-500 hover:bg-sky-600 text-white transition-all shadow-lg shadow-sky-500/20 disabled:opacity-50"
                >
                    {testingNotification['telegram'] ? $_('settings.telegram.test_sending') : $_('settings.telegram.test_notification')}
                </button>
            </div>
        </section>

        <!-- Email -->
        <section class="card-base rounded-3xl p-8 backdrop-blur-md">
            <div class="flex items-center justify-between mb-6">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                        <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                    </div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.email.title')}</h3>
                </div>
                <button
                    role="switch"
                    aria-checked={emailEnabled}
                    onclick={() => emailEnabled = !emailEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            emailEnabled = !emailEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {emailEnabled ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.email.title')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {emailEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="space-y-4">
                <!-- Auth Mode Selector -->
                <div>
                    <div id="email-auth-mode-label" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.auth_mode')}</div>
                    <div class="flex gap-2" role="group" aria-labelledby="email-auth-mode-label">
                        <button
                            onclick={() => emailUseOAuth = true}
                            aria-label="Use OAuth authentication"
                            aria-pressed={emailUseOAuth}
                            class="flex-1 px-4 py-2 rounded-xl text-sm font-bold transition-all {emailUseOAuth ? 'bg-indigo-500 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}"
                        >
                            {$_('settings.email.oauth')}
                        </button>
                        <button
                            onclick={() => emailUseOAuth = false}
                            aria-label="Use SMTP authentication"
                            aria-pressed={!emailUseOAuth}
                            class="flex-1 px-4 py-2 rounded-xl text-sm font-bold transition-all {!emailUseOAuth ? 'bg-indigo-500 text-white' : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'}"
                        >
                            {$_('settings.email.smtp')}
                        </button>
                    </div>
                </div>

                {#if emailUseOAuth}
                    <!-- OAuth Section -->
                    <div class="p-4 bg-slate-50 dark:bg-slate-900/50 rounded-2xl space-y-3">
                        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.email.oauth_desc')}</p>
                        <div class="flex gap-2">
                            <button
                                onclick={async () => {
                                    try {
                                        const response = await initiateGmailOAuth();
                                        window.open(response.authorization_url, '_blank', 'width=600,height=700');
                                    } catch (error) {
                                        console.error('Gmail OAuth error:', error);
                                    }
                                }}
                                aria-label="Connect Gmail account"
                                class="flex-1 px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 text-sm font-bold transition-all"
                            >
                                {$_('settings.email.connect_gmail')}
                            </button>
                            <button
                                onclick={async () => {
                                    try {
                                        const response = await initiateOutlookOAuth();
                                        window.open(response.authorization_url, '_blank', 'width=600,height=700');
                                    } catch (error) {
                                        console.error('Outlook OAuth error:', error);
                                    }
                                }}
                                aria-label="Connect Outlook account"
                                class="flex-1 px-4 py-2 rounded-xl bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 text-sm font-bold transition-all"
                            >
                                {$_('settings.email.connect_outlook')}
                            </button>
                        </div>
                        {#if emailConnectedEmail}
                            <div class="flex items-center justify-between p-3 bg-green-50 dark:bg-green-900/20 rounded-xl">
                                <span class="text-sm text-green-700 dark:text-green-300">{$_('settings.email.connected', { values: { email: emailConnectedEmail } })}</span>
                                <button
                                    onclick={async () => {
                                        try {
                                            await disconnectEmailOAuth((emailOAuthProvider as 'gmail' | 'outlook') || 'gmail');
                                            emailConnectedEmail = null;
                                            emailOAuthProvider = null;
                                        } catch (error) {
                                            console.error('Disconnect error:', error);
                                        }
                                    }}
                                    aria-label="Disconnect email account"
                                    class="text-xs text-red-600 dark:text-red-400 hover:underline"
                                >
                                    {$_('settings.email.disconnect')}
                                </button>
                            </div>
                        {/if}
                    </div>
                {:else}
                    <!-- SMTP Section -->
                    <div class="space-y-3">
                        <div>
                            <label for="smtp-host" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.smtp_host')}</label>
                            <input
                                id="smtp-host"
                                type="text"
                                bind:value={emailSmtpHost}
                                placeholder={$_('settings.email.smtp_host_placeholder')}
                                aria-label="SMTP host"
                                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                            />
                        </div>
                        <div class="grid grid-cols-2 gap-3">
                            <div>
                                <label for="smtp-port" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.smtp_port')}</label>
                                <input
                                    id="smtp-port"
                                    type="number"
                                    bind:value={emailSmtpPort}
                                    aria-label="SMTP port"
                                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                                />
                            </div>
                            <div class="flex items-end">
                                <label for="smtp-tls" class="flex items-center gap-2 px-4 py-3">
                                    <input
                                        id="smtp-tls"
                                        type="checkbox"
                                        bind:checked={emailSmtpUseTls}
                                        class="rounded"
                                    />
                                    <span class="text-sm font-bold text-slate-700 dark:text-slate-300">{$_('settings.email.smtp_use_tls')}</span>
                                </label>
                            </div>
                        </div>
                        <div>
                            <label for="smtp-username" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.smtp_username')}</label>
                            <input
                                id="smtp-username"
                                type="text"
                                bind:value={emailSmtpUsername}
                                aria-label="SMTP username"
                                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                            />
                        </div>
                        <div>
                            <div class="flex items-center justify-between mb-2">
                                <label for="smtp-password" class="text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.email.smtp_password')}</label>
                                {#if emailSmtpPasswordSaved}
                                    <span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[9px] font-black uppercase tracking-widest">{$_('common.saved')}</span>
                                {/if}
                            </div>
                            <input
                                id="smtp-password"
                                type="password"
                                bind:value={emailSmtpPassword}
                                aria-label="SMTP password"
                                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                            />
                        </div>
                    </div>
                {/if}

                <!-- Common Email Settings -->
                <div class="pt-4 border-t border-slate-200 dark:border-slate-700 space-y-3">
                    <div>
                        <label for="email-from" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.from_email')}</label>
                        <input
                            id="email-from"
                            type="email"
                            bind:value={emailFromEmail}
                            placeholder={$_('settings.email.from_email_placeholder')}
                            aria-label="From email address"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                    <div>
                        <label for="email-to" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.to_email')}</label>
                        <input
                            id="email-to"
                            type="email"
                            bind:value={emailToEmail}
                            placeholder={$_('settings.email.to_email_placeholder')}
                            aria-label="To email address"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                    </div>
                    <div>
                        <label for="email-include-snapshot" class="flex items-center gap-2 px-4 py-3 bg-slate-50 dark:bg-slate-900/50 rounded-2xl cursor-pointer">
                            <input
                                id="email-include-snapshot"
                                type="checkbox"
                                bind:checked={emailIncludeSnapshot}
                                class="rounded"
                            />
                            <span class="text-sm font-bold text-slate-700 dark:text-slate-300">{$_('settings.email.include_snapshot')}</span>
                        </label>
                    </div>
                    <div>
                        <label for="email-only-on-end" class="flex items-center gap-2 px-4 py-3 bg-slate-50 dark:bg-slate-900/50 rounded-2xl cursor-pointer">
                            <input
                                id="email-only-on-end"
                                type="checkbox"
                                bind:checked={emailOnlyOnEnd}
                                class="rounded"
                            />
                            <span class="text-sm font-bold text-slate-700 dark:text-slate-300">{$_('settings.email.only_on_end')}</span>
                        </label>
                        <p class="mt-1 text-xs text-slate-500">{$_('settings.email.only_on_end_desc')}</p>
                    </div>
                    <div>
                        <label for="email-dashboard-url" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.email.dashboard_url')}</label>
                        <input
                            id="email-dashboard-url"
                            type="url"
                            bind:value={emailDashboardUrl}
                            placeholder={$_('settings.email.dashboard_url_placeholder')}
                            aria-label="Dashboard URL for email links"
                            aria-describedby="dashboard-url-hint"
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                        />
                        <p id="dashboard-url-hint" class="mt-1 text-xs text-slate-500">{$_('settings.email.dashboard_url_desc')}</p>
                    </div>
                </div>

                <button
                    onclick={async () => {
                        try {
                            emailTestError = null;
                            emailTestSuccess = null;
                            testingNotification['email'] = true;
                            const result = await sendTestEmail();
                            emailTestSuccess = result.message || 'Test email sent';
                        } catch (e: any) {
                            emailTestError = extractErrorMessage(e, 'Failed to send test email');
                        } finally {
                            testingNotification['email'] = false;
                        }
                    }}
                    disabled={testingNotification['email'] || !emailToEmail}
                    aria-label="Send test email notification"
                    class="w-full px-4 py-3 text-xs font-black uppercase tracking-widest rounded-2xl bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/20 disabled:opacity-50"
                >
                    {testingNotification['email'] ? $_('settings.email.test_email_sending') : $_('settings.email.test_email')}
                </button>
                {#if emailTestError}
                    <p class="mt-2 text-xs font-semibold text-rose-600">{emailTestError}</p>
                {:else if emailTestSuccess}
                    <p class="mt-2 text-xs font-semibold text-emerald-600">{emailTestSuccess}</p>
                {/if}
            </div>
        </section>
    </div>
</div>
