<script lang="ts">
    import { _ } from 'svelte-i18n';
    import SecretSavedBadge from './SecretSavedBadge.svelte';
    import { AUTH_PASSWORD_COMPLEXITY_MESSAGE } from '../../auth-password-policy';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    let {
        authEnabled = $bindable(false),
        authUsername = $bindable('admin'),
        authHasPassword = $bindable(false),
        authPassword = $bindable(''),
        authPasswordConfirm = $bindable(''),
        authSessionExpiryHours = $bindable(168),
        trustedProxyHosts = $bindable<string[]>([]),
        trustedProxyHostsSuggested = $bindable(false),
        newTrustedProxyHost = $bindable(''),
        publicAccessEnabled = $bindable(false),
        publicAccessShowCameraNames = $bindable(true),
        publicAccessShowAiConversation = $bindable(false),
        publicAccessAllowClipDownloads = $bindable(false),
        publicAccessHistoricalDaysMode = $bindable<'retention' | 'custom'>('retention'),
        publicAccessHistoricalDays = $bindable(7),
        publicAccessMediaDaysMode = $bindable<'retention' | 'custom'>('retention'),
        publicAccessMediaHistoricalDays = $bindable(7),
        publicAccessRateLimitPerMinute = $bindable(30),
        publicAccessExternalBaseUrl = $bindable(''),
        retentionDays = 0,
        addTrustedProxyHost,
        removeTrustedProxyHost,
        acceptTrustedProxySuggestions
    }: {
        authEnabled: boolean;
        authUsername: string;
        authHasPassword: boolean;
        authPassword: string;
        authPasswordConfirm: string;
        authSessionExpiryHours: number;
        trustedProxyHosts: string[];
        trustedProxyHostsSuggested: boolean;
        newTrustedProxyHost: string;
        publicAccessEnabled: boolean;
        publicAccessShowCameraNames: boolean;
        publicAccessShowAiConversation: boolean;
        publicAccessAllowClipDownloads: boolean;
        publicAccessHistoricalDaysMode: 'retention' | 'custom';
        publicAccessHistoricalDays: number;
        publicAccessMediaDaysMode: 'retention' | 'custom';
        publicAccessMediaHistoricalDays: number;
        publicAccessRateLimitPerMinute: number;
        publicAccessExternalBaseUrl: string;
        retentionDays?: number;
        addTrustedProxyHost: () => void;
        removeTrustedProxyHost: (host: string) => void;
        acceptTrustedProxySuggestions: () => void;
    } = $props();

    const capPublicDays = (n: number) => Math.max(0, Math.min(365, Math.floor(n)));
    const effectiveRetentionDays = () => {
        const r = Number(retentionDays ?? 0);
        return capPublicDays(r > 0 ? r : 365);
    };

    const effectiveEventsDays = () =>
        publicAccessHistoricalDaysMode === 'retention' ? effectiveRetentionDays() : capPublicDays(publicAccessHistoricalDays);
    const effectiveMediaDays = () =>
        publicAccessMediaDaysMode === 'retention' ? effectiveRetentionDays() : capPublicDays(publicAccessMediaHistoricalDays);

    const daysOptions = [
        { value: 'retention', label: $_('settings.public_access.window_retention', { default: 'Same as retention policy' }) },
        { value: '0', label: $_('settings.public_access.window_live_only', { default: 'Live only (today)' }) },
        { value: '7', label: '7' },
        { value: '30', label: '30' },
        { value: '90', label: '90' },
        { value: '365', label: '365' }
    ];

    function eventsDaysValue() {
        return publicAccessHistoricalDaysMode === 'retention' ? 'retention' : String(publicAccessHistoricalDays);
    }
    function mediaDaysValue() {
        return publicAccessMediaDaysMode === 'retention' ? 'retention' : String(publicAccessMediaHistoricalDays);
    }
    function setEventsDays(v: string) {
        if (v === 'retention') {
            publicAccessHistoricalDaysMode = 'retention';
            return;
        }
        publicAccessHistoricalDaysMode = 'custom';
        publicAccessHistoricalDays = capPublicDays(parseInt(v, 10));
    }
    function setMediaDays(v: string) {
        if (v === 'retention') {
            publicAccessMediaDaysMode = 'retention';
            return;
        }
        publicAccessMediaDaysMode = 'custom';
        publicAccessMediaHistoricalDays = capPublicDays(parseInt(v, 10));
    }
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-stretch">
    <SettingsCard
        icon="🔐"
        title={$_('settings.auth.title')}
        description={$_('settings.auth.desc')}
    >
        <SettingsRow
            labelId="setting-auth-enabled"
            label={$_('settings.auth.enable')}
            description={$_('settings.auth.enable_desc')}
        >
            <SettingsToggle
                checked={authEnabled}
                labelledBy="setting-auth-enabled"
                srLabel={$_('settings.auth.enable')}
                onchange={(v) => (authEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-auth-username"
            label={$_('settings.auth.username')}
            layout="stacked"
        >
            <SettingsInput
                id="auth-username"
                type="text"
                value={authUsername}
                ariaLabel={$_('settings.auth.username')}
                oninput={(v) => (authUsername = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-auth-password"
            label={$_('settings.auth.password')}
            description={AUTH_PASSWORD_COMPLEXITY_MESSAGE}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if authHasPassword}
                    <div class="flex justify-end">
                        <SecretSavedBadge />
                    </div>
                {/if}
                <SettingsInput
                    id="auth-password"
                    type="password"
                    autocomplete="new-password"
                    value={authPassword}
                    placeholder={authHasPassword ? $_('settings.auth.password_placeholder') : $_('settings.auth.password_new')}
                    ariaLabel={$_('settings.auth.password')}
                    oninput={(v) => (authPassword = v)}
                />
            </div>
        </SettingsRow>

        <SettingsRow
            labelId="setting-auth-password-confirm"
            label={$_('settings.auth.password_confirm')}
            layout="stacked"
        >
            <SettingsInput
                id="auth-password-confirm"
                type="password"
                autocomplete="new-password"
                value={authPasswordConfirm}
                placeholder={$_('settings.auth.password_confirm_placeholder')}
                ariaLabel={$_('settings.auth.password_confirm')}
                oninput={(v) => (authPasswordConfirm = v)}
            />
        </SettingsRow>

        <AdvancedSection
            id="auth-session-and-proxy"
            title={$_('settings.auth.advanced_title', { default: 'Session & reverse proxy' })}
        >
            <SettingsRow
                labelId="setting-auth-expiry"
                label={$_('settings.auth.session_expiry')}
                layout="stacked"
            >
                <SettingsInput
                    id="auth-expiry"
                    type="number"
                    min={1}
                    max={720}
                    value={authSessionExpiryHours}
                    ariaLabel={$_('settings.auth.session_expiry')}
                    oninput={(v) => (authSessionExpiryHours = Number(v) || 0)}
                />
            </SettingsRow>

            <div class="rounded-2xl border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-[11px] font-bold text-amber-900 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200">
                {$_('settings.auth.proxy_trust_note', { default: 'Proxy headers are trusted from all hosts by default. If you run behind a reverse proxy, set trusted proxy hosts to prevent spoofed client IPs.' })}
            </div>

            <SettingsRow
                labelId="setting-trusted-proxies"
                label={$_('settings.auth.trusted_proxies')}
                description={$_('settings.auth.trusted_proxies_desc', { default: 'Add your reverse proxy container names or IPs (e.g., nginx-rp, cloudflare-tunnel, 172.19.0.10). Docker DNS names work when services share a network.' })}
                layout="stacked"
            >
                <div class="space-y-3">
                    <div class="flex gap-2">
                        <div class="flex-1">
                            <SettingsInput
                                id="trusted-proxy-hosts"
                                value={newTrustedProxyHost}
                                placeholder={$_('settings.auth.trusted_proxies_placeholder', { default: 'Add proxy host or IP' })}
                                ariaLabel={$_('settings.auth.trusted_proxies')}
                                oninput={(v) => (newTrustedProxyHost = v)}
                                onkeydown={(e) => { if (e.key === 'Enter') addTrustedProxyHost(); }}
                            />
                        </div>
                        <button
                            type="button"
                            onclick={addTrustedProxyHost}
                            disabled={!newTrustedProxyHost.trim()}
                            aria-label={$_('settings.auth.trusted_proxies_add', { default: 'Add trusted proxy host' })}
                            class="px-6 py-3 bg-teal-500 hover:bg-teal-600 text-white text-xs font-black uppercase tracking-widest rounded-2xl transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            {$_('common.add')}
                        </button>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        {#each trustedProxyHosts as host}
                            <span class="group flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold {trustedProxyHostsSuggested ? 'border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-400' : 'bg-white dark:bg-slate-800 border border-teal-200 dark:border-teal-700/50 text-slate-700 dark:text-slate-300'}">
                                {host}
                                {#if trustedProxyHostsSuggested}
                                    <span class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                        {$_('settings.auth.trusted_proxies_suggested_label', { default: 'Suggested' })}
                                    </span>
                                {:else}
                                    <button
                                        type="button"
                                        onclick={() => removeTrustedProxyHost(host)}
                                        aria-label={$_('settings.auth.trusted_proxies_remove', { default: 'Remove trusted proxy host' })}
                                        class="text-slate-400 hover:text-red-500 transition-colors"
                                    >
                                        ✕
                                    </button>
                                {/if}
                            </span>
                        {/each}
                        {#if trustedProxyHosts.length === 0}
                            <p class="text-xs font-bold text-slate-400 italic">{$_('settings.auth.trusted_proxies_empty', { default: 'No trusted proxies configured (all proxies trusted).' })}</p>
                        {/if}
                    </div>
                    {#if trustedProxyHostsSuggested}
                        <div class="flex flex-col gap-2 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 px-3 py-2 text-[11px] text-slate-500 dark:text-slate-400">
                            <span>{$_('settings.auth.trusted_proxies_suggested_note', { default: 'These are suggestions only. Save will keep the default (trust all) unless you accept or edit them.' })}</span>
                            <button
                                type="button"
                                onclick={acceptTrustedProxySuggestions}
                                class="self-start px-3 py-1.5 rounded-xl bg-teal-500 text-white text-[10px] font-black uppercase tracking-widest"
                            >
                                {$_('settings.auth.trusted_proxies_use_suggestions', { default: 'Use suggestions' })}
                            </button>
                        </div>
                    {/if}
                </div>
            </SettingsRow>
        </AdvancedSection>
    </SettingsCard>

    <SettingsCard
        icon="🌐"
        title={$_('settings.public_access.title')}
        description={$_('settings.public_access.desc')}
    >
        <SettingsRow
            labelId="setting-public-enabled"
            label={$_('settings.public_access.enable')}
            description={$_('settings.public_access.enable_desc')}
        >
            <SettingsToggle
                checked={publicAccessEnabled}
                labelledBy="setting-public-enabled"
                srLabel={$_('settings.public_access.enable')}
                onchange={(v) => (publicAccessEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-public-show-cameras"
            label={$_('settings.public_access.show_camera_names')}
            description={$_('settings.public_access.show_camera_names_desc')}
        >
            <SettingsToggle
                checked={publicAccessShowCameraNames}
                labelledBy="setting-public-show-cameras"
                srLabel={$_('settings.public_access.show_camera_names')}
                onchange={(v) => (publicAccessShowCameraNames = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-public-show-ai"
            label={$_('settings.public_access.show_ai_conversation')}
            description={$_('settings.public_access.show_ai_conversation_desc')}
        >
            <SettingsToggle
                checked={publicAccessShowAiConversation}
                labelledBy="setting-public-show-ai"
                srLabel={$_('settings.public_access.show_ai_conversation')}
                onchange={(v) => (publicAccessShowAiConversation = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-public-clip-download"
            label={$_('settings.public_access.allow_clip_downloads')}
            description={$_('settings.public_access.allow_clip_downloads_desc')}
        >
            <SettingsToggle
                checked={publicAccessAllowClipDownloads}
                labelledBy="setting-public-clip-download"
                srLabel={$_('settings.public_access.allow_clip_downloads')}
                onchange={(v) => (publicAccessAllowClipDownloads = v)}
            />
        </SettingsRow>

        <AdvancedSection
            id="public-access-windows"
            title={$_('settings.public_access.advanced_title', { default: 'History windows & rate limits' })}
        >
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <SettingsRow
                    labelId="setting-public-history-days"
                    label={$_('settings.public_access.history_days')}
                    description={$_('settings.public_access.window_effective', { default: 'Effective: {days} days', values: { days: effectiveEventsDays() } })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="public-days-mode"
                        value={eventsDaysValue()}
                        ariaLabel={$_('settings.public_access.history_days')}
                        options={daysOptions}
                        onchange={(v) => setEventsDays(v)}
                    />
                </SettingsRow>

                <SettingsRow
                    labelId="setting-public-media-days"
                    label={$_('settings.public_access.media_days')}
                    description={$_('settings.public_access.window_effective', { default: 'Effective: {days} days', values: { days: effectiveMediaDays() } })}
                    layout="stacked"
                >
                    <SettingsSelect
                        id="public-media-days-mode"
                        value={mediaDaysValue()}
                        ariaLabel={$_('settings.public_access.media_days')}
                        options={daysOptions}
                        onchange={(v) => setMediaDays(v)}
                    />
                </SettingsRow>

                <SettingsRow
                    labelId="setting-public-rate-limit"
                    label={$_('settings.public_access.rate_limit')}
                    layout="stacked"
                >
                    <SettingsInput
                        id="public-rate"
                        type="number"
                        min={1}
                        max={100}
                        value={publicAccessRateLimitPerMinute}
                        ariaLabel={$_('settings.public_access.rate_limit')}
                        oninput={(v) => (publicAccessRateLimitPerMinute = Number(v) || 0)}
                    />
                </SettingsRow>

                <div class="sm:col-span-2">
                    <SettingsRow
                        labelId="setting-public-share-base-url"
                        label={$_('settings.public_access.share_base_url', { default: 'Share Link Base URL (optional)' })}
                        description={$_('settings.public_access.share_base_url_desc', { default: 'If set, new share links use this public base URL instead of the detected request host.' })}
                        layout="stacked"
                    >
                        <SettingsInput
                            id="public-share-base-url"
                            type="url"
                            value={publicAccessExternalBaseUrl}
                            placeholder={$_('settings.public_access.share_base_url_placeholder', { default: 'https://your-public-domain.example' })}
                            ariaLabel={$_('settings.public_access.share_base_url', { default: 'Share Link Base URL' })}
                            oninput={(v) => (publicAccessExternalBaseUrl = v)}
                        />
                    </SettingsRow>
                </div>
            </div>
        </AdvancedSection>
    </SettingsCard>
</div>
