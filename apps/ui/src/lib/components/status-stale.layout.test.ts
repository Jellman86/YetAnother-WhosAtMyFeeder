import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import connectionStatusSource from './ConnectionStatus.svelte?raw';
import healthSource from '../pages/Errors.svelte?raw';

describe('an out-of-date status says so', () => {
    it('passes the time of the last status to the sidebar only once it is out of date', () => {
        expect(appSource).toContain('staleSince={systemStatusStore.stale ? systemStatusStore.receivedAt : null}');
    });

    it('words how old the rows are instead of letting them pass for current', () => {
        expect(connectionStatusSource).toContain("$_('status.stale_since'");
        expect(connectionStatusSource).toContain('data-status-stale');
    });

    it('keeps Health current while it is open, following the pushed health revision', () => {
        expect(healthSource).toContain('followRevisions(refreshWorkspace, systemStatusStore.snapshot?.health_revision ?? null)');
        expect(healthSource).toContain('follower.observe(snapshot.health_revision)');
        // The opening read goes through the follower too, so a failed one is retried, and stops on unmount.
        expect(healthSource).toContain('follower.start();');
        expect(healthSource).toContain('follower.stop();');
        expect(healthSource).toMatch(/async function refreshWorkspace\(\): Promise<boolean>/);
    });
});
