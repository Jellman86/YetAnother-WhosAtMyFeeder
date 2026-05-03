import { describe, expect, it } from 'vitest';
import dataSettingsSource from './DataSettings.svelte?raw';

describe('DataSettings diagnostics access', () => {
    it('renders a button for opening the error diagnostics workspace', () => {
        expect(dataSettingsSource).toContain('handleOpenDiagnostics');
        expect(dataSettingsSource).toContain('settings.data.open_diagnostics');
        expect(dataSettingsSource).toContain('settings.data.diagnostics_title');
    });
});
