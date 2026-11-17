import { describe, expect, it } from 'vitest';
import { analyseSettings } from './settings-reachability.analysis';

const HOST = 'pages/Host.svelte';

function host(markup: string, script = ''): string {
    return `<script lang="ts">
    import Part from '../parts/Part.svelte';
    let port = $state(1883);
    let theme = $state('light');
    ${script}
    function buildSettingsPayload() {
        return {
            mqtt_port: port,
            // A comment, with a comma, between entries.
            theme_name: theme
        };
    }
</script>
{#if activeSection === 'cameras'}
    ${markup}
{/if}`;
}

const PART = `<script lang="ts">
    import Field from './Field.svelte';
    let {
        /** The port, documented. */
        port = $bindable(1883),
        onTheme
    }: { port: number; onTheme: (theme: string) => void } = $props();
</script>
<Field bind:port />
<button type="button" onclick={() => onTheme('dark')}>Dark</button>`;

const FIELD = `<script lang="ts">
    let { port = $bindable(1883) }: { port: number } = $props();
    let draft = $state(port);
    function commit() {
        port = draft;
    }
</script>
<input id="port-field" bind:value={draft} onchange={commit} />`;

function analyse(hostMarkup: string, hostScript = '', field = FIELD): ReturnType<typeof analyseSettings> {
    return analyseSettings({ [HOST]: host(hostMarkup, hostScript), 'parts/Part.svelte': PART, 'parts/Field.svelte': field }, HOST);
}

describe('the Settings reachability analysis', () => {
    it('follows a descendant control through its local copy and two-way bindings to the saved field', () => {
        const map = analyse('<Part bind:port onTheme={(next) => (theme = next)} />');
        expect(map.controls.find((control) => control.id === 'port-field')).toEqual({ file: 'parts/Field.svelte', id: 'port-field', areas: ['cameras'], entries: ['mqtt_port'] });
        expect(map.ids['port-field']).toEqual(['cameras']);
    });

    it('follows a callback to the host state it changes', () => {
        const map = analyse('<Part bind:port onTheme={(next) => (theme = next)} />');
        expect(map.controls.find((control) => control.file === 'parts/Part.svelte')?.entries).toEqual(['theme_name']);
    });

    it('loses the field when one step passes a two-way value one way', () => {
        const map = analyse('<Part port={port} onTheme={(next) => (theme = next)} />');
        expect(map.controls.find((control) => control.id === 'port-field')?.entries).toEqual([]);
    });

    it('loses the control when it is no longer rendered', () => {
        const map = analyse('<Part bind:port onTheme={(next) => (theme = next)} />', '', FIELD.replace(/<input[^>]*\/>/, ''));
        expect(map.controls.find((control) => control.id === 'port-field')).toBeUndefined();
        expect(map.ids['port-field']).toBeUndefined();
    });

    it('does not count a reload of every setting as an edit', () => {
        const reload = `function reload() { ${Array.from({ length: 25 }, (_, index) => `v${index} = 1;`).join(' ')} port = 1; theme = 'x'; }`;
        const map = analyse('<Part bind:port onTheme={() => reload()} />', reload);
        expect(map.controls.find((control) => control.file === 'parts/Part.svelte')?.entries).toEqual([]);
    });
});
