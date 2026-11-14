import { afterEach, describe, expect, it } from 'vitest';
import { SECRET_FIELDS, draftFromForm, unsavedDraft } from './unsaved-draft';

const saved = { mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_password: '***REDACTED***', cameras: ['patio'], llm_api_key: '***REDACTED***' };

describe('the draft kept when Settings is left by Back or Forward', () => {
    afterEach(() => unsavedDraft.clear());

    it('keeps only the non-secret values that differ from the saved copy, by field', () => {
        const draft = draftFromForm(
            { mqtt_server: 'broker.lan', mqtt_port: 1883, mqtt_password: 'hunter2', cameras: ['patio'], llm_api_key: '' },
            saved,
            ['mqtt_server', 'mqtt_password']
        );
        expect(draft).toEqual({ values: { mqtt_server: 'broker.lan' }, editedSecrets: ['mqtt_password'] });
    });

    it('never holds a secret value, only the fact that a secret was edited', () => {
        const payload = Object.fromEntries(SECRET_FIELDS.map((field) => [field, `secret-${field}`]));
        const draft = draftFromForm({ ...payload, mqtt_server: 'broker.lan' }, saved, [...SECRET_FIELDS]);
        expect(JSON.stringify(draft)).not.toContain('secret-');
        expect(draft?.editedSecrets).toEqual([...SECRET_FIELDS]);
    });

    it('is nothing to keep when nothing differs', () => {
        expect(draftFromForm({ mqtt_server: 'mqtt', mqtt_port: 1883 }, saved, [])).toBeNull();
    });

    it('is handed back once, then gone, and lives only in memory', () => {
        unsavedDraft.keep({ values: { mqtt_server: 'broker.lan' }, editedSecrets: [] });
        expect(unsavedDraft.take()).toEqual({ values: { mqtt_server: 'broker.lan' }, editedSecrets: [] });
        expect(unsavedDraft.take()).toBeNull();
        expect(typeof localStorage === 'undefined' || localStorage.length === 0).toBe(true);
        expect(typeof sessionStorage === 'undefined' || sessionStorage.length === 0).toBe(true);
    });
});
