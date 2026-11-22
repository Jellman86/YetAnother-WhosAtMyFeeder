export type NotifyMode = 'silent' | 'final' | 'standard' | 'realtime' | 'custom';

/** The id of the Channels card, which the delivery sentence's channel words link to. */
export const NOTIFICATION_CHANNELS_SECTION_ID = 'notification-channels';
/** The disclosure under the delivery sentence that holds the custom-rule switches. */
export const NOTIFICATION_CUSTOM_RULES_ID = 'notifications-custom-rules';

export interface PolicyChannel {
    id: 'discord' | 'pushover' | 'telegram' | 'email';
    label: string;
    enabled: boolean;
    configured: boolean;
}

export function presetSentenceKey(mode: NotifyMode): string {
    return `settings.notifications.sentence.what_${mode}`;
}

export function speciesSummaryKey(
    mode: 'none' | 'blacklist' | 'whitelist',
    count: number
): string {
    if (mode === 'blacklist' && count > 0) {
        return 'settings.notifications.sentence.species_all_but';
    }
    if (mode === 'whitelist' && count > 0) {
        return 'settings.notifications.sentence.species_only';
    }
    return 'settings.notifications.sentence.species_any';
}

export function enabledChannelNames(channels: PolicyChannel[]): string[] {
    return channels.filter((channel) => channel.enabled).map((channel) => channel.label);
}

export function formatChannelList(names: string[], locale: string): string {
    if (names.length === 0) return '';
    try {
        return new Intl.ListFormat(locale, { style: 'long', type: 'conjunction' }).format(names);
    } catch {
        return names.join(', ');
    }
}

/** What a page holds for each channel, saved or still a draft. */
export interface ChannelDraft {
    discord: { enabled: boolean; webhook: string; webhookSaved: boolean };
    pushover: { enabled: boolean; user: string; userSaved: boolean; token: string; tokenSaved: boolean };
    telegram: { enabled: boolean; token: string; tokenSaved: boolean; chatId: string; chatIdSaved: boolean };
    email: { enabled: boolean; useOAuth: boolean; connectedEmail: string | null; smtpHost: string; toEmail: string };
}

/**
 * Each channel, switched on or not and whether it has what it needs to send. Notifications and
 * Garden alerts read the same list, so the two can never describe a channel differently.
 */
export function policyChannels(draft: ChannelDraft, label: (id: PolicyChannel['id']) => string): PolicyChannel[] {
    return [
        { id: 'discord', label: label('discord'), enabled: draft.discord.enabled, configured: Boolean(draft.discord.webhook || draft.discord.webhookSaved) },
        {
            id: 'pushover',
            label: label('pushover'),
            enabled: draft.pushover.enabled,
            configured: Boolean(draft.pushover.user || draft.pushover.userSaved) && Boolean(draft.pushover.token || draft.pushover.tokenSaved)
        },
        {
            id: 'telegram',
            label: label('telegram'),
            enabled: draft.telegram.enabled,
            configured: Boolean(draft.telegram.token || draft.telegram.tokenSaved) && Boolean(draft.telegram.chatId || draft.telegram.chatIdSaved)
        },
        {
            id: 'email',
            label: label('email'),
            enabled: draft.email.enabled,
            configured: draft.email.useOAuth ? Boolean(draft.email.connectedEmail) : Boolean(draft.email.smtpHost && draft.email.toEmail)
        }
    ];
}
