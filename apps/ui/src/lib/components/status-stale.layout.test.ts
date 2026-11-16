import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';

describe('an out-of-date status says so', () => {
    it('passes the time of the last status to the sidebar only once it is out of date', () => {
        expect(appSource).toContain('staleSince={systemStatusStore.stale ? systemStatusStore.receivedAt : null}');
    });

    it('words how old the rows are instead of letting them pass for current', () => {
        expect(connectionStatusSource).toContain("$_('status.stale_since'");
        expect(connectionStatusSource).toContain('data-status-stale');
    });
});
