import { describe, expect, it } from 'vitest';
import { chunksImportingAnEntry, viewScriptCounts, type OutputChunks } from './bundle-shape';

const chunks: OutputChunks = {
    'entry.js': { isEntry: true, imports: ['shell.js'], dynamicImports: ['dashboard.js', 'settings.js', 'locale-en.js'] },
    'shell.js': { isEntry: false, imports: ['runtime.js'], dynamicImports: ['chart.js'] },
    'runtime.js': { isEntry: false, imports: [], dynamicImports: [] },
    'shared.js': { isEntry: false, imports: ['shell.js'], dynamicImports: [] },
    'dashboard.js': { isEntry: false, imports: ['shared.js', 'shell.js'], dynamicImports: ['dialog.js'] },
    'dialog.js': { isEntry: false, imports: ['shared.js'], dynamicImports: [] },
    'settings.js': { isEntry: false, imports: ['shared.js'], dynamicImports: ['tab.js'] },
    'tab.js': { isEntry: false, imports: ['settings-common.js'], dynamicImports: [] },
    'settings-common.js': { isEntry: false, imports: ['shared.js'], dynamicImports: [] },
    'chart.js': { isEntry: false, imports: [], dynamicImports: [] },
    'locale-en.js': { isEntry: false, imports: [], dynamicImports: [] }
};

const count = (view: string): number | undefined => viewScriptCounts(chunks).find((entry) => entry.view === view)?.scripts;

describe('viewScriptCounts', () => {
    it('counts the scripts a view needs before it can draw: the entry and its imports, then the view and its imports', () => {
        // entry, shell, runtime, then dashboard and shared.
        expect(count('dashboard.js')).toBe(5);
    });

    it('counts a view opened from another lazily loaded view with the chain that opens it', () => {
        // entry, shell, runtime; settings and shared; the tab and its own common chunk.
        expect(count('tab.js')).toBe(7);
        expect(count('dialog.js')).toBe(6);
    });

    it('counts every lazily loaded chunk, libraries and locales included', () => {
        expect(count('chart.js')).toBe(4);
        expect(viewScriptCounts(chunks).map((entry) => entry.view).sort()).toEqual(
            ['chart.js', 'dashboard.js', 'dialog.js', 'locale-en.js', 'settings.js', 'tab.js']
        );
    });

    it('ends on an import cycle between lazily loaded chunks', () => {
        const cyclic: OutputChunks = {
            'entry.js': { isEntry: true, imports: [], dynamicImports: ['a.js'] },
            'a.js': { isEntry: false, imports: [], dynamicImports: ['b.js'] },
            'b.js': { isEntry: false, imports: [], dynamicImports: ['a.js'] }
        };
        expect(viewScriptCounts(cyclic).find((entry) => entry.view === 'b.js')?.scripts).toBe(3);
    });
});

describe('chunksImportingAnEntry', () => {
    it('finds none when every chunk imports only the shared code below the entry', () => {
        expect(chunksImportingAnEntry(chunks)).toEqual([]);
    });

    it('finds a chunk that imports the chunk the entry\'s code went into, when the entry chunk is only a stub', () => {
        // How the deadlock first appeared: the entry module was grouped into `shell`, leaving the
        // entry chunk a stub that imports it, and the locale imported `shell`.
        const merged: OutputChunks = {
            'index.js': { isEntry: true, imports: ['shell.js'], dynamicImports: ['locale-en.js'] },
            'shell.js': { isEntry: false, holdsEntryCode: true, imports: [], dynamicImports: [] },
            'locale-en.js': { isEntry: false, imports: ['shell.js'], dynamicImports: [] }
        };
        expect(chunksImportingAnEntry(merged)).toEqual(['locale-en.js imports shell.js']);
    });

    it("finds a chunk that imports the entry back, which deadlocks while the entry awaits it", () => {
        // The entry awaits its locale at the top level; a locale that imports the entry waits on it in turn.
        const deadlocked: OutputChunks = {
            'shell.js': { isEntry: true, imports: [], dynamicImports: ['locale-en.js'] },
            'locale-en.js': { isEntry: false, imports: ['shell.js'], dynamicImports: [] }
        };
        expect(chunksImportingAnEntry(deadlocked)).toEqual(['locale-en.js imports shell.js']);
    });
});
