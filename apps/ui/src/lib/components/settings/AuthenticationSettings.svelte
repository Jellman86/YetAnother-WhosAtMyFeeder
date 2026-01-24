<script lang="ts">
    import { _ } from 'svelte-i18n';

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
        publicAccessHistoricalDays = $bindable(7),
        publicAccessRateLimitPerMinute = $bindable(30),
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
        publicAccessHistoricalDays: number;
        publicAccessRateLimitPerMinute: number;
        addTrustedProxyHost: () => void;
        removeTrustedProxyHost: (host: string) => void;
        acceptTrustedProxySuggestions: () => void;
    } = $props();
</script>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                <span class="text-xl">🔐</span>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.auth.title')}</h3>
                <p class="text-xs text-slate-500">{$_('settings.auth.desc')}</p>
            </div>
        </div>

        <div class="space-y-6">
            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                <div id="auth-enabled-label">
                    <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.auth.enable')}</span>
                    <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.auth.enable_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={authEnabled}
                    aria-labelledby="auth-enabled-label"
                    onclick={() => authEnabled = !authEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            authEnabled = !authEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {authEnabled ? 'bg-emerald-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.auth.enable')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {authEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div>
                <label for="auth-username" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.auth.username')}</label>
                <input
                    id="auth-username"
                    type="text"
                    bind:value={authUsername}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                />
            </div>

            <div class="grid grid-cols-1 gap-3">
                <div>
                    <label for="auth-password" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.auth.password')}</label>
                    <input
                        id="auth-password"
                        type="password"
                        bind:value={authPassword}
                        placeholder={authHasPassword ? $_('settings.auth.password_placeholder') : $_('settings.auth.password_new')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    />
                </div>
                <div>
                    <label for="auth-password-confirm" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.auth.password_confirm')}</label>
                    <input
                        id="auth-password-confirm"
                        type="password"
                        bind:value={authPasswordConfirm}
                        placeholder={$_('settings.auth.password_confirm_placeholder')}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                    />
                </div>
            </div>

            <div>
                <label for="auth-expiry" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.auth.session_expiry')}</label>
                <input
                    id="auth-expiry"
                    type="number"
                    min="1"
                    max="720"
                    bind:value={authSessionExpiryHours}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-emerald-500 outline-none"
                />
            </div>

            <div class="rounded-2xl border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-[11px] font-bold text-amber-900 dark:border-amber-500/40 dark:bg-amber-900/20 dark:text-amber-200">
                {$_('settings.auth.proxy_trust_note', { default: 'Proxy headers are trusted from all hosts by default. If you run behind a reverse proxy, set trusted proxy hosts to prevent spoofed client IPs.' })}
            </div>

            <div class="pt-2">
                <label for="trusted-proxy-hosts" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.auth.trusted_proxies')}</label>
                <p class="text-[11px] text-slate-500 dark:text-slate-400 mb-3">
                    {$_('settings.auth.trusted_proxies_desc', { default: 'Add your reverse proxy container names or IPs (e.g., nginx-rp, cloudflare-tunnel, 172.19.0.10). Docker DNS names work when services share a network.' })}
                </p>
                <div class="flex gap-2 mb-4">
                    <input
                        id="trusted-proxy-hosts"
                        bind:value={newTrustedProxyHost}
                        onkeydown={(e) => e.key === 'Enter' && addTrustedProxyHost()}
                        placeholder={$_('settings.auth.trusted_proxies_placeholder', { default: 'Add proxy host or IP' })}
                        aria-label={$_('settings.auth.trusted_proxies')}
                        class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
                    />
                    <button
                        onclick={addTrustedProxyHost}
                        disabled={!newTrustedProxyHost.trim()}
                        aria-label={$_('settings.auth.trusted_proxies_add', { default: 'Add trusted proxy host' })}
                        class="px-6 py-3 bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-black uppercase tracking-widest rounded-2xl transition-all disabled:opacity-50"
                    >
                        {$_('common.add')}
                    </button>
                </div>
                <div class="flex flex-wrap gap-2">
                    {#each trustedProxyHosts as host}
                        <span class="group flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold {trustedProxyHostsSuggested ? 'border border-dashed border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-900/40 text-slate-500 dark:text-slate-400' : 'bg-white dark:bg-slate-800 border border-emerald-200 dark:border-emerald-700/50 text-slate-700 dark:text-slate-300'}">
                            {host}
                            {#if trustedProxyHostsSuggested}
                                <span class="px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest bg-slate-200 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                    {$_('settings.auth.trusted_proxies_suggested_label', { default: 'Suggested' })}
                                </span>
                            {:else}
                                <button
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
                    <div class="mt-3 flex flex-col gap-2 rounded-2xl border border-dashed border-slate-300 dark:border-slate-700 px-3 py-2 text-[11px] text-slate-500 dark:text-slate-400">
                        <span>{$_('settings.auth.trusted_proxies_suggested_note', { default: 'These are suggestions only. Save will keep the default (trust all) unless you accept or edit them.' })}</span>
                        <button
                            onclick={acceptTrustedProxySuggestions}
                            class="self-start px-3 py-1.5 rounded-xl bg-emerald-500 text-white text-[10px] font-black uppercase tracking-widest"
                        >
                            {$_('settings.auth.trusted_proxies_use_suggestions', { default: 'Use suggestions' })}
                        </button>
                    </div>
                {/if}
            </div>
        </div>
    </section>

    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center gap-3 mb-6">
            <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                <span class="text-xl">🌐</span>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.public_access.title')}</h3>
                <p class="text-xs text-slate-500">{$_('settings.public_access.desc')}</p>
            </div>
        </div>

        <div class="space-y-6">
            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                <div id="public-enabled-label">
                    <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.public_access.enable')}</span>
                    <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.public_access.enable_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={publicAccessEnabled}
                    aria-labelledby="public-enabled-label"
                    onclick={() => publicAccessEnabled = !publicAccessEnabled}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            publicAccessEnabled = !publicAccessEnabled;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {publicAccessEnabled ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.public_access.enable')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {publicAccessEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50 flex items-center justify-between">
                <div id="public-camera-label">
                    <span class="block text-sm font-bold text-slate-900 dark:text-white">{$_('settings.public_access.show_camera_names')}</span>
                    <span class="block text-[10px] text-slate-500 font-medium">{$_('settings.public_access.show_camera_names_desc')}</span>
                </div>
                <button
                    role="switch"
                    aria-checked={publicAccessShowCameraNames}
                    aria-labelledby="public-camera-label"
                    onclick={() => publicAccessShowCameraNames = !publicAccessShowCameraNames}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            publicAccessShowCameraNames = !publicAccessShowCameraNames;
                        }
                    }}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {publicAccessShowCameraNames ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.public_access.show_camera_names')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {publicAccessShowCameraNames ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>

            <div class="grid grid-cols-2 gap-4">
                <div>
                    <label for="public-days" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.public_access.history_days')}</label>
                    <input
                        id="public-days"
                        type="number"
                        min="0"
                        max="365"
                        bind:value={publicAccessHistoricalDays}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                    />
                </div>
                <div>
                    <label for="public-rate" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.public_access.rate_limit')}</label>
                    <input
                        id="public-rate"
                        type="number"
                        min="1"
                        max="100"
                        bind:value={publicAccessRateLimitPerMinute}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-indigo-500 outline-none"
                    />
                </div>
            </div>
        </div>
    </section>
</div>
