import { describe, expect, it } from 'vitest';
import { gardenChannelsMissingCredentials, gardenDeliveryChannels } from './garden-notifications';
import type { PolicyChannel } from './notification-policy';

const channel = (id: PolicyChannel['id'], enabled: boolean, configured: boolean): PolicyChannel => ({ id, label: id, enabled, configured });

const birds: PolicyChannel[] = [
    channel('discord', true, false),
    channel('pushover', false, true),
    channel('telegram', true, true),
    channel('email', true, true)
];

describe('Garden alert channels', () => {
    it('follow the bird channels that are switched on and configured, in delivery order', () => {
        expect(gardenDeliveryChannels(true, ['pushover'], birds)).toEqual(['telegram', 'email']);
    });

    it('send nowhere when no bird channel is on and configured', () => {
        expect(gardenDeliveryChannels(true, [], [channel('telegram', false, true), channel('discord', true, false)])).toEqual([]);
    });

    it('keep an explicit choice as chosen, whatever the bird switches say', () => {
        expect(gardenDeliveryChannels(false, ['pushover', 'discord', 'pushover'], birds)).toEqual(['pushover', 'discord']);
        expect(gardenDeliveryChannels(false, [], birds)).toEqual([]);
    });

    it('name chosen channels that still need credentials', () => {
        expect(gardenChannelsMissingCredentials(['discord', 'telegram'], birds)).toEqual(['discord']);
        expect(gardenChannelsMissingCredentials(['telegram'], birds)).toEqual([]);
    });
});
