import type { PolicyChannel } from './notification-policy';

export type GardenChannel = PolicyChannel['id'];

/** The server's delivery order, so the page names channels as an alert would reach them. */
const ORDER: readonly GardenChannel[] = ['discord', 'telegram', 'pushover', 'email'];

/**
 * Where a Garden alert goes with the settings on the page: the bird channels that are switched
 * on and configured, or exactly the channels the owner chose (a chosen channel without
 * credentials is still attempted, and fails, so it is reported rather than hidden).
 */
export function gardenDeliveryChannels(
    useBirdChannels: boolean,
    selected: readonly GardenChannel[],
    birdChannels: readonly PolicyChannel[]
): GardenChannel[] {
    if (useBirdChannels) {
        const ready = new Set(birdChannels.filter((channel) => channel.enabled && channel.configured).map((channel) => channel.id));
        return ORDER.filter((channel) => ready.has(channel));
    }
    return [...new Set(selected)].filter((channel) => ORDER.includes(channel));
}

/** Chosen channels that cannot send yet because their credentials are missing. */
export function gardenChannelsMissingCredentials(
    selected: readonly GardenChannel[],
    birdChannels: readonly PolicyChannel[]
): GardenChannel[] {
    const configured = new Set(birdChannels.filter((channel) => channel.configured).map((channel) => channel.id));
    return gardenDeliveryChannels(false, selected, birdChannels).filter((channel) => !configured.has(channel));
}
