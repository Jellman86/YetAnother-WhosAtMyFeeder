export type NotifyMode = 'silent' | 'final' | 'standard' | 'realtime' | 'custom';

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
