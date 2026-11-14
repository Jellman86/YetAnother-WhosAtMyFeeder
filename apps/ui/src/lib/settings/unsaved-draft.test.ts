import { afterEach, describe, expect, it } from 'vitest';
import { SECRET_FIELDS, accessIdentity, draftFromForm, mergeDraft, unsavedDraft, type UnsavedDraft } from './unsaved-draft';

const saved = { mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_password: '***REDACTED***', cameras: ['patio'], llm_api_key: '***REDACTED***' };
const owner = accessIdentity({ authRequired: true, isAuthenticated: true, username: 'owner', hasOwnerAccess: true, token: 'token-1' });

describe('the draft kept when Settings is left by Back or Forward', () => {
    afterEach(() => unsavedDraft.clear());

    it('keeps only the non-secret values that differ from the saved copy, with the saved value each began from', () => {
        const draft = draftFromForm(
            { mqtt_server: 'broker.lan', mqtt_port: 1883, mqtt_password: 'hunter2', cameras: ['patio'], llm_api_key: '' },
            saved,
            ['mqtt_server', 'mqtt_password'],
            owner
        );
        expect(draft).toEqual({
            identity: owner,
            values: { mqtt_server: 'broker.lan' },
            baselines: { mqtt_server: 'mqtt' },
            editedSecrets: ['mqtt_password']
        });
    });

    it('never holds a secret value, only the fact that a secret was edited', () => {
        const payload = Object.fromEntries(SECRET_FIELDS.map((field) => [field, `secret-${field}`]));
        const draft = draftFromForm({ ...payload, mqtt_server: 'broker.lan' }, saved, [...SECRET_FIELDS], owner);
        expect(JSON.stringify(draft)).not.toContain('secret-');
        expect(draft?.editedSecrets).toEqual([...SECRET_FIELDS]);
    });

    it('is nothing to keep when nothing differs, or when nobody with owner access is signed in', () => {
        expect(draftFromForm({ mqtt_server: 'mqtt', mqtt_port: 1883 }, saved, [], owner)).toBeNull();
        expect(draftFromForm({ mqtt_server: 'broker.lan' }, saved, ['mqtt_server'], null)).toBeNull();
    });

    it('is handed back once, then gone, and lives only in memory', () => {
        unsavedDraft.keep(draftFromForm({ mqtt_server: 'broker.lan' }, saved, ['mqtt_server'], owner));
        expect(unsavedDraft.pendingFor(owner)).toBe(true);
        expect(unsavedDraft.take(owner)?.values).toEqual({ mqtt_server: 'broker.lan' });
        expect(unsavedDraft.take(owner)).toBeNull();
        expect(typeof localStorage === 'undefined' || localStorage.length === 0).toBe(true);
        expect(typeof sessionStorage === 'undefined' || sessionStorage.length === 0).toBe(true);
    });
});

describe('whose draft it is', () => {
    afterEach(() => unsavedDraft.clear());

    it('belongs to one signed-in session: another session, a guest or a signed-out page gets nothing and drops it', () => {
        const nextLogin = accessIdentity({ authRequired: true, isAuthenticated: true, username: 'owner', hasOwnerAccess: true, token: 'token-2' });
        expect(nextLogin).not.toBe(owner);
        expect(accessIdentity({ authRequired: true, isAuthenticated: false, username: null, hasOwnerAccess: false, token: null })).toBeNull();
        unsavedDraft.keep(draftFromForm({ mqtt_server: 'broker.lan' }, saved, ['mqtt_server'], owner));
        expect(unsavedDraft.take(nextLogin)).toBeNull();
        // It is gone even for the session that kept it: it was dropped, not set aside.
        expect(unsavedDraft.take(owner)).toBeNull();
    });

    it('is not kept at all when captured with no owner session, as while signing out', () => {
        unsavedDraft.keep(draftFromForm({ mqtt_server: 'broker.lan' }, saved, ['mqtt_server'], owner));
        unsavedDraft.keep(draftFromForm({ mqtt_server: 'other' }, saved, ['mqtt_server'], null));
        expect(unsavedDraft.take(owner)).toBeNull();
    });
});

describe('putting a draft back over a fresh read', () => {
    const draft: UnsavedDraft = { identity: 'open', values: { mqtt_server: 'broker.lan', mqtt_port: 1884 }, baselines: { mqtt_server: 'mqtt', mqtt_port: 1883 }, editedSecrets: [] };

    it('restores every drafted value whose saved value has not changed since', () => {
        expect(mergeDraft(draft, { mqtt_server: 'mqtt', mqtt_port: 1883 })).toEqual({ restore: { mqtt_server: 'broker.lan', mqtt_port: 1884 }, conflicts: [] });
    });

    it('keeps a change made elsewhere to a field the draft did not touch', () => {
        const merged = mergeDraft(draft, { mqtt_server: 'mqtt', mqtt_port: 1883, frigate_url: 'http://elsewhere:5000' });
        expect(merged.restore).toEqual({ mqtt_server: 'broker.lan', mqtt_port: 1884 });
        expect(merged.conflicts).toEqual([]);
    });

    it('does not apply a drafted value whose saved value changed elsewhere: that is a conflict', () => {
        const merged = mergeDraft(draft, { mqtt_server: 'mqtt.elsewhere', mqtt_port: 1883 });
        expect(merged.restore).toEqual({ mqtt_port: 1884 });
        expect(merged.conflicts).toEqual([{ field: 'mqtt_server', mine: 'broker.lan', saved: 'mqtt.elsewhere' }]);
    });
});
