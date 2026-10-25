<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { fetchGardenNotifications, type GardenNotificationChannel, type GardenNotificationStatus } from '../../api/garden';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    let { enabled = $bindable(false), channels = $bindable<GardenNotificationChannel[]>([]) }:
        { enabled?: boolean; channels?: GardenNotificationChannel[] } = $props();
    let status = $state.raw<GardenNotificationStatus | null>(null);
    let loading = $state(false);
    let error = $state<string | null>(null);
    const choices: { id: GardenNotificationChannel; name: string }[] = [
        { id: 'discord', name: 'Discord' }, { id: 'telegram', name: 'Telegram' },
        { id: 'pushover', name: 'Pushover' }, { id: 'email', name: 'Email' }
    ];

    async function refresh(signal?: AbortSignal): Promise<void> {
        loading = true;
        error = null;
        try { status = await fetchGardenNotifications(signal); }
        catch (failure) {
            if (!signal?.aborted) error = failure instanceof Error ? failure.message : $_('common.error');
        } finally { loading = false; }
    }

    $effect(() => {
        if (!enabled) return;
        const controller = new AbortController();
        void refresh(controller.signal);
        return () => controller.abort();
    });

    function toggle(channel: GardenNotificationChannel): void {
        channels = channels.includes(channel) ? channels.filter(value => value !== channel) : [...channels, channel];
    }
</script>

<section class="space-y-3" data-garden-notifications>
    <SettingsRow labelId="garden-notifications" label={$_('settings.beta.garden_notifications')}
        description={$_('settings.beta.garden_notifications_help')}>
        <SettingsToggle checked={enabled} labelledBy="garden-notifications" srLabel={$_('settings.beta.garden_notifications')}
            onchange={value => enabled = value} />
    </SettingsRow>
    {#if enabled}
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_notifications_privacy')}</p>
        <div class="flex flex-wrap gap-2" role="group" aria-label={$_('settings.beta.garden_notification_channels')}>
            {#each choices as channel (channel.id)}
                <button type="button" class="btn btn-secondary min-h-11 whitespace-normal" aria-pressed={channels.includes(channel.id)}
                    aria-label={$_('settings.beta.garden_notification_channel', { values: { channel: channel.name } })}
                    onclick={() => toggle(channel.id)}>{channel.name}<span aria-hidden="true">{channels.includes(channel.id) ? '✓' : '+'}</span></button>
            {/each}
        </div>
        {#if channels.length === 0}<p class="text-xs text-amber-800 dark:text-amber-200">{$_('settings.beta.garden_notifications_choose')}</p>{/if}
        {#if status && channels.some(channel => !status?.configured[channel])}
            <p class="text-xs text-amber-800 dark:text-amber-200">{$_('settings.beta.garden_notifications_credentials')}</p>
        {/if}
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('settings.beta.garden_notifications_attempts_help')}</p>
        <div class="space-y-2 text-xs" aria-busy={loading} data-garden-notification-status>
            {#if status}
                <p>{$_('settings.beta.garden_notifications_status', { values: {
                    sent: status.attempts.sent ?? 0, failed: status.attempts.failed ?? 0,
                    unknown: status.attempts.attempted ?? 0, skipped: status.attempts.skipped ?? 0
                } })}</p>
            {/if}
            {#if error}<p role="alert" class="text-red-700 dark:text-red-300">{error}</p>{/if}
            <button type="button" class="btn btn-secondary min-h-11" disabled={loading} onclick={() => void refresh()}>
                {loading ? $_('common.loading') : $_('settings.beta.garden_notifications_refresh')}
            </button>
        </div>
    {/if}
</section>
