import { describe, expect, it } from 'vitest';
import pipelineSource from './InstancePipeline.svelte?raw';
import instanceSource from './InstanceSummary.svelte?raw';
import privacySummarySource from './PrivacySummary.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import en from '../i18n/locales/en.json';

describe('About surface polish', () => {
    it('lists every browser-side network call the sighting map makes', () => {
        // The panel promises "nothing leaves your network except the calls listed
        // below", and the eBird map fetches OpenStreetMap tiles from each
        // viewer's browser, so both rows must be in the list.
        expect(privacySummarySource).toContain("key: 'ebird'");
        expect(privacySummarySource).toContain("key: 'osm'");
        expect(en.about.outbound.osm_desc.toLowerCase()).toContain('browser');
    });
    it('sweeps a pulse along the pipeline in the direction data travels', () => {
        // Svelte scopes @keyframes, so a name referenced from a class resolves to nothing
        // without this prefix. The animation silently does nothing if it is dropped.
        expect(pipelineSource).toContain('@keyframes -global-pipeline-flow');
        expect(pipelineSource).toContain('@keyframes -global-pipeline-edge');
        // The stagger is what makes the sweep read as a direction rather than a blink.
        expect(pipelineSource).toContain('--flow-index: {index}');
        expect(pipelineSource).toContain('calc(var(--flow-index, 0) * var(--flow-stagger))');
        expect(pipelineSource).toContain('--flow-duration: 9s');
        expect(pipelineSource).toContain('prefers-reduced-motion');
    });

    it('peaks the sheen where it is centred, so the first step is not skipped', () => {
        // Ramping opacity earlier left step one fading up while its gradient was still off
        // the left edge, which read as the flow starting at the second card.
        expect(pipelineSource).toContain('13% { opacity: 1; transform: translateX(0%); }');
    });

    it('never prints the same unknown twice, and marks unprobed steps as unchecked', () => {
        expect(pipelineSource).toContain('detail: noReading, state: unknown');
        expect(pipelineSource).not.toContain('detail: unknown, state: unknown');
        // MQTT and the database have no health endpoint; saying so beats a blank chip.
        expect(pipelineSource.match(/state: notChecked/g)?.length).toBe(2);
    });

    it('keeps the availability footprint without calling a failed request empty history', () => {
        expect(instanceSource).toContain("type UptimeLoadState = 'loading' | 'ready' | 'error'");
        expect(instanceSource).toContain("uptimeLoadState = 'ready'");
        expect(instanceSource).toContain("uptimeLoadState = 'error'");
        expect(instanceSource).toContain("uptimeLoadState === 'loading'");
        expect(instanceSource).toContain("uptimeLoadState === 'error'");
        expect(instanceSource).toContain('about.instance.history_unavailable');
        expect(instanceSource).toContain('about.instance.history_loading');
        expect(instanceSource).toContain('about.instance.availability');
        // A 24 bar strip with no scale leaves the reader guessing which end is now.
        expect(instanceSource).toContain('about.instance.window_start');
        expect(instanceSource).toContain('about.instance.window_now');
    });

    it('keeps uptime and issue-report content inside the instance card on narrow screens', () => {
        // A long model id used to establish the mobile grid's intrinsic width. That widened the
        // whole card, carrying both the report row and the 24-hour strip past the viewport.
        expect(instanceSource).toContain('class="grid min-w-0 gap-6');
        expect(instanceSource).toContain('data-instance-uptime class="min-w-0"');
        expect(instanceSource).toContain('class="mt-2 flex w-full min-w-0 max-w-full gap-[2px]"');
        expect(instanceSource).toContain('class="min-w-0" data-instance-report');
        expect(instanceSource).toContain('flex min-w-0 flex-col items-stretch gap-2');
        expect(instanceSource).toContain('whitespace-normal break-all');
        expect(instanceSource).toContain('w-full sm:w-auto');
    });

    it('spends motion on the pipeline rather than decorative hover effects', () => {
        expect(instanceSource).not.toContain('hover:scale-y-125');
        expect(aboutSource).not.toContain('group-hover:-translate-y-px');
        expect(aboutSource).not.toContain('group-hover:translate-x-px');
    });

    it('sizes the external link arrow in the icon, not the display font', () => {
        expect(aboutSource).not.toContain('↗');
        expect(aboutSource).toContain('h-2.5 w-2.5 shrink-0 text-slate-400');
    });

    it('speaks in the first person and drops the title case', () => {
        expect(en.about.project_desc_1.startsWith('I started this')).toBe(true);
        expect(en.about.how_it_works).toBe('How it works');
        expect(en.about.links.issues).toBe('Report an issue');
        // House rule: no em dashes in any copy on these surfaces.
        for (const value of JSON.stringify(en.about).match(/"[^"]*"/g) ?? []) {
            expect(value).not.toContain('—');
        }
    });
});
