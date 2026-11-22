<script lang="ts">
    import type { ComponentProps } from 'svelte';
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type AuthenticationSettingsView from '../AuthenticationSettings.svelte';
    import type TelemetrySettingsView from '../TelemetrySettings.svelte';
    import { authStore } from '../../../stores/auth.svelte';
    import { loadAuthenticationSettings, loadTelemetrySettings } from './part-loaders';

    // Access & privacy: who can open this install (sign-in and guest access), then what leaves it
    // (telemetry). All of it is on the first screen, so the section has no More options.
    type Props = ComponentProps<typeof AuthenticationSettingsView> & ComponentProps<typeof TelemetrySettingsView>;

    let {
        authEnabled = $bindable(),
        authUsername = $bindable(),
        authHasPassword = $bindable(),
        authPassword = $bindable(),
        authPasswordConfirm = $bindable(),
        authSessionExpiryHours = $bindable(),
        trustedProxyHosts = $bindable(),
        trustedProxyHostsSuggested = $bindable(),
        newTrustedProxyHost = $bindable(),
        publicAccessEnabled = $bindable(),
        publicAccessShowCameraNames = $bindable(),
        publicAccessShowAiConversation = $bindable(),
        publicAccessAllowClipDownloads = $bindable(),
        publicAccessShowAudio = $bindable(),
        publicAccessShowSnapshots = $bindable(),
        publicAccessShowClips = $bindable(),
        publicAccessLocationPrecision = $bindable(),
        publicAccessHistoricalDaysMode = $bindable(),
        publicAccessHistoricalDays = $bindable(),
        publicAccessMediaDaysMode = $bindable(),
        publicAccessMediaHistoricalDays = $bindable(),
        publicAccessRateLimitPerMinute = $bindable(),
        publicAccessExternalBaseUrl = $bindable(),
        retentionDays,
        addTrustedProxyHost,
        removeTrustedProxyHost,
        acceptTrustedProxySuggestions,
        telemetryEnabled = $bindable(),
        telemetryHealthEnabled = $bindable(),
        telemetryInstallationId,
        telemetryPlatform,
        telemetryPayloadPreview,
        versionInfo
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="access">
    <div class="space-y-8" data-settings-part="security">
        {#if authStore.httpsWarning}
            <div class="flex items-start gap-3 rounded-2xl border border-status-attention-line bg-status-attention-soft px-4 py-3 text-sm text-status-attention" data-https-warning>
                <svg xmlns="http://www.w3.org/2000/svg" class="mt-0.5 h-5 w-5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <p>
                    <strong class="font-semibold">{$_('settings.security.https_warning_title', { default: 'Passwords travel unencrypted.' })}</strong>
                    {$_('settings.security.https_warning', { default: 'Sign-in is on, but this page is served over HTTP, so passwords and sessions can be read on the network. Serve YA-WAMF over HTTPS, for example behind your reverse proxy.' })}
                </p>
            </div>
        {/if}
        <LazyRoute loader={loadAuthenticationSettings} label={$_('settings.tabs.security')}>
        {#snippet content(AuthenticationSettings)}
        <AuthenticationSettings
            bind:authEnabled
            bind:authUsername
            bind:authHasPassword
            bind:authPassword
            bind:authPasswordConfirm
            bind:authSessionExpiryHours
            bind:trustedProxyHosts
            bind:trustedProxyHostsSuggested
            bind:newTrustedProxyHost
            bind:publicAccessEnabled
            bind:publicAccessShowCameraNames
            bind:publicAccessShowAiConversation
            bind:publicAccessAllowClipDownloads
            bind:publicAccessShowAudio
            bind:publicAccessShowSnapshots
            bind:publicAccessShowClips
            bind:publicAccessLocationPrecision
            bind:publicAccessHistoricalDaysMode
            bind:publicAccessHistoricalDays
            bind:publicAccessMediaDaysMode
            bind:publicAccessMediaHistoricalDays
            bind:publicAccessRateLimitPerMinute
            bind:publicAccessExternalBaseUrl
            {retentionDays}
            {addTrustedProxyHost}
            {removeTrustedProxyHost}
            {acceptTrustedProxySuggestions}
        />
        {/snippet}
        </LazyRoute>
    </div>

    <!-- What leaves this install: kept with who can reach it. -->
    <div class="space-y-8" data-settings-part="telemetry" data-settings-telemetry>
        <LazyRoute loader={loadTelemetrySettings} label={$_('settings.telemetry.title')}>
        {#snippet content(TelemetrySettings)}
        <TelemetrySettings
            bind:telemetryEnabled
            bind:telemetryHealthEnabled
            {telemetryInstallationId}
            {telemetryPlatform}
            {telemetryPayloadPreview}
            {versionInfo}
        />
        {/snippet}
        </LazyRoute>
    </div>
</div>
