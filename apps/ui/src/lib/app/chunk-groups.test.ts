import { describe, expect, it } from 'vitest';
import { sharedChunkFor, type ModuleGraph } from './chunk-groups';

/** A module graph as the bundler reports it: who imports each module, statically or lazily. */
function graph(modules: Record<string, { importers?: string[]; dynamicImporters?: string[] }>): ModuleGraph {
    return {
        getModuleInfo: (id) => {
            const module = modules[id];
            return module ? { importers: module.importers ?? [], dynamicImporters: module.dynamicImporters ?? [] } : null;
        }
    };
}

const SRC = '/app/src';

describe('sharedChunkFor gathers the code views share', () => {
    const dashboard = `${SRC}/lib/pages/Dashboard.svelte`;
    const species = `${SRC}/lib/pages/Species.svelte`;
    const settings = `${SRC}/lib/pages/Settings.svelte`;
    const connection = `${SRC}/lib/components/settings/ConnectionSettings.svelte`;
    const detection = `${SRC}/lib/components/settings/DetectionSettings.svelte`;
    const app = `${SRC}/App.svelte`;
    const modules = graph({
        [dashboard]: { dynamicImporters: [app] },
        [species]: { dynamicImporters: [app] },
        [settings]: { dynamicImporters: [app] },
        [connection]: { dynamicImporters: [settings] },
        [detection]: { dynamicImporters: [settings] },
        [`${SRC}/lib/components/DayPanel.svelte`]: { importers: [dashboard] },
        [`${SRC}/lib/components/DayPanelRow.svelte`]: { importers: [`${SRC}/lib/components/DayPanel.svelte`] },
        [`${SRC}/lib/components/SpeciesCard.svelte`]: { importers: [dashboard, species] },
        [`${SRC}/lib/components/settings/SettingRow.svelte`]: { importers: [connection, detection] },
        [`${SRC}/lib/components/settings/HostField.svelte`]: { importers: [connection] },
        [`${SRC}/lib/components/Cycle.svelte`]: { importers: [`${SRC}/lib/components/CycleBack.svelte`] },
        [`${SRC}/lib/components/CycleBack.svelte`]: { importers: [`${SRC}/lib/components/Cycle.svelte`, species] }
    });

    it('leaves a lazily loaded entry to the bundler, so it stays its own chunk', () => {
        expect(sharedChunkFor(dashboard, modules)).toBeNull();
        expect(sharedChunkFor(connection, modules)).toBeNull();
    });

    it('leaves code only one view reaches, however deep, to the bundler, which keeps it in that view', () => {
        expect(sharedChunkFor(`${SRC}/lib/components/DayPanelRow.svelte`, modules)).toBeNull();
        expect(sharedChunkFor(`${SRC}/lib/components/settings/HostField.svelte`, modules)).toBeNull();
    });

    it('a module several Settings tabs share goes with the Settings page', () => {
        expect(sharedChunkFor(`${SRC}/lib/components/settings/SettingRow.svelte`, modules)).toBe('settings');
    });

    it('code only the setup wizard uses, wherever it opens from, goes with the wizard', () => {
        const wizard = graph({
            [`${SRC}/lib/pages/FirstRunWizard.svelte`]: { dynamicImporters: [app] },
            [`${SRC}/lib/components/setup/WizardShell.svelte`]: { dynamicImporters: [app] },
            [`${SRC}/lib/components/setup/ModelStep.svelte`]: {
                importers: [`${SRC}/lib/pages/FirstRunWizard.svelte`, `${SRC}/lib/components/setup/WizardShell.svelte`]
            }
        });
        expect(sharedChunkFor(`${SRC}/lib/components/setup/ModelStep.svelte`, wizard)).toBe('setup');
    });

    it('code only dialogs use goes with the dialogs, loaded when one opens', () => {
        const dialogs = graph({
            [`${SRC}/lib/components/DetectionModal.svelte`]: { dynamicImporters: [dashboard] },
            [`${SRC}/lib/components/SpeciesDetailModal.svelte`]: { dynamicImporters: [species] },
            [`${SRC}/lib/components/TaxonCard.svelte`]: {
                importers: [`${SRC}/lib/components/DetectionModal.svelte`, `${SRC}/lib/components/SpeciesDetailModal.svelte`]
            }
        });
        expect(sharedChunkFor(`${SRC}/lib/components/TaxonCard.svelte`, dialogs)).toBe('dialogs');
    });

    it('code a page and a dialog share goes into the shared chunk', () => {
        const mixed = graph({
            [dashboard]: { dynamicImporters: [app] },
            [`${SRC}/lib/components/DetectionModal.svelte`]: { dynamicImporters: [dashboard] },
            [`${SRC}/lib/components/FrameStrip.svelte`]: { importers: [`${SRC}/lib/components/DetectionModal.svelte`, dashboard] }
        });
        expect(sharedChunkFor(`${SRC}/lib/components/FrameStrip.svelte`, mixed)).toBe('shared');
    });

    it('a module views share goes into the one shared chunk', () => {
        expect(sharedChunkFor(`${SRC}/lib/components/SpeciesCard.svelte`, modules)).toBe('shared');
    });

    it('an import cycle ends, and is placed by the views outside it', () => {
        expect(sharedChunkFor(`${SRC}/lib/components/Cycle.svelte`, modules)).toBeNull();
        const shared = graph({
            [dashboard]: { dynamicImporters: [app] },
            [species]: { dynamicImporters: [app] },
            [`${SRC}/lib/a.ts`]: { importers: [`${SRC}/lib/b.ts`, dashboard] },
            [`${SRC}/lib/b.ts`]: { importers: [`${SRC}/lib/a.ts`, species] }
        });
        expect(sharedChunkFor(`${SRC}/lib/a.ts`, shared)).toBe('shared');
    });

    it('walks a graph whose import paths multiply without following every path', () => {
        // 40 layers of two modules, each importing both modules of the layer above: 2^40 paths.
        const layers: Record<string, { importers?: string[]; dynamicImporters?: string[] }> = {
            [dashboard]: { dynamicImporters: [app] }
        };
        let above = [dashboard];
        for (let layer = 0; layer < 40; layer += 1) {
            const pair = [`${SRC}/lib/deep/a${layer}.ts`, `${SRC}/lib/deep/b${layer}.ts`];
            for (const id of pair) layers[id] = { importers: above };
            above = pair;
        }
        const started = Date.now();
        layers[species] = { dynamicImporters: [app] };
        layers[`${SRC}/lib/deep/a0.ts`] = { importers: [dashboard, species] };
        expect(sharedChunkFor(above[0], graph(layers))).toBe('shared');
        expect(Date.now() - started).toBeLessThan(1_000);
    });

    it('an unknown module is left to the bundler', () => {
        expect(sharedChunkFor('/app/src/lib/unknown.ts', graph({}))).toBeNull();
    });
});
