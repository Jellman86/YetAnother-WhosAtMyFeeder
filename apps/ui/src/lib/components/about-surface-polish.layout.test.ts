import { describe, expect, it } from 'vitest';
import pipelineSource from './InstancePipeline.svelte?raw';
import instanceSource from './InstanceSummary.svelte?raw';
import privacySummarySource from './PrivacySummary.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';
import enAbout from '../i18n/locales/en/about.json';
import enSubtitle from '../i18n/locales/en/page_subtitle.json';
import portraitSource from './FeederPortrait.svelte?raw';

const en = { about: enAbout };

describe('About surface polish', () => {
    it('describes the page it titles and carries no trivia', () => {
        // The subtitle listed a changelog and contributors the page does not show, and a card of
        // general bird facts closed a page that is otherwise only about this install.
        expect(enSubtitle.about).toBe('What this feeder has recorded, how YA-WAMF works, and what it stores and sends.');
        expect(aboutSource).not.toMatch(/ProjectNotes|did_you_know|bird_facts/);
        // The footer under every page already carries the licence and the copyright line.
        expect(aboutSource).not.toContain('license_notice');
    });

    it('names the latest visit by its caption, so the spoken name starts with the words shown', () => {
        // An aria-label that reworded the caption failed label-in-name (WCAG 2.5.3).
        const button = portraitSource.slice(portraitSource.indexOf('<button'), portraitSource.indexOf('</button>'));
        expect(button).not.toContain('aria-label=');
        expect(button).not.toMatch(/bg-linear-to-t[^>]*aria-hidden/);
        expect(button).toContain("about.portrait.open_this_visit");
    });

    it('gives the quick links and credit links a full touch target', () => {
        expect(aboutSource).toContain('class="group inline-flex min-h-11 items-center gap-1.5 text-brand-700 focus-ring');
        expect(aboutSource).toMatch(/<a href=\{credit\.href\}[^>]*class="inline-flex min-h-11 items-center/);
    });

    it('names the model as the Models tab does, with its runtime as a muted second line', () => {
        // A file id such as mobilenet_v2_birds ran past the card; ids belong in the issue report only.
        expect(pipelineSource).toContain('classifier.effective_model_name');
        expect(pipelineSource).not.toMatch(/effective_model_id|active_model_id|font-mono|break-all/);
        expect(pipelineSource).toContain('data-pipeline-note');
        expect(en.about.pipeline.standby).toBe('Not loaded yet');
    });

    it('draws every step as the same card, with its state as a dot and a word', () => {
        // Three border styles and a three-item legend were more encoding than seven cards can carry.
        expect(pipelineSource).not.toMatch(/kindClass|border-dashed|legend_local|legend_optional|legend_external/);
        expect(pipelineSource).toContain('border border-line-soft p-3');
        expect(pipelineSource).toContain('toneDot(step.tone)');
        expect(pipelineSource).toContain('about.pipeline.legend_note');
    });

    it('makes no promise that the list is everything, and builds it from the features that send', () => {
        // The old line said nothing else leaves the network, over a list without Google Fonts or Wikipedia.
        expect(en.about.pipeline.legend_note).toBe('What leaves your network is listed below.');
        expect(JSON.stringify(en.about)).not.toMatch(/Nothing leaves your network/i);
        expect(privacySummarySource).toContain('outboundRequests(facts)');
        expect(privacySummarySource).not.toContain("on: ebirdEnabled");
        // Who sends each request is said in words, and every entry has a name and what it sends.
        expect(en.about.outbound.from_server).toBe('Sent by this server');
        expect(en.about.outbound.from_browser).toBe('Sent by each viewer’s browser');
        const outbound = en.about.outbound as Record<string, string>;
        for (const key of ['inat', 'wikipedia', 'gbif', 'weather', 'geolocate', 'places', 'ebird', 'birdweather', 'inat_submit', 'llm', 'notify', 'telemetry', 'updates', 'downloads', 'fonts', 'photos', 'osm', 'gbif_tiles']) {
            expect(outbound[key], key).toBeTruthy();
            expect(outbound[`${key}_desc`], key).toMatch(/Sends|sees|see |Fetches|Anonymous|Asks/);
        }
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
        // The database has no health endpoint, and the broker stays unchecked until its
        // measured session is read; saying so beats a blank chip.
        expect(pipelineSource.match(/state: notChecked/g)?.length).toBe(2);
        expect(pipelineSource).toContain('serviceConnectionsStore.connections?.mqtt.state');
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
        // The report line breaks between its parts, never inside a model name.
        expect(instanceSource).not.toContain('break-all');
        expect(instanceSource).toContain('{#each supportParts as part, position (position)}');
        expect(instanceSource).toContain('w-full sm:w-auto');
    });

    it('spends motion on the pipeline rather than decorative hover effects', () => {
        expect(instanceSource).not.toContain('hover:scale-y-125');
        expect(aboutSource).not.toContain('group-hover:-translate-y-px');
        expect(aboutSource).not.toContain('group-hover:translate-x-px');
    });

    it('sizes the external link arrow in the icon, not the display font', () => {
        expect(aboutSource).not.toContain('↗');
        expect(aboutSource).toContain('h-2.5 w-2.5 shrink-0 text-slate-500');
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

    it('never puts an unmeasured running time beside a measured availability', () => {
        // "Running for Unknown" above "100% up" claimed a measurement that was not made.
        expect(instanceSource).not.toMatch(/uptime \?\? \$_\('about\.pipeline\.unknown'/);
        expect(instanceSource).toContain('data-instance-running-unmeasured');
        // The availability figure names its own window, apart from the running time.
        expect(instanceSource).toContain("about.instance.availability_heading");
        expect(instanceSource.indexOf('data-instance-running-for')).toBeLessThan(
            instanceSource.indexOf('about.instance.availability_heading')
        );
        // The start time is read from the probes, never assumed.
        expect(instanceSource).toContain('startedAtFrom(readiness) ?? startedAtFrom(await checkHealth()');
    });

    it('names the runtime and its device rather than a bare runtime token', () => {
        expect(instanceSource).toContain('describeRuntime(classifier)');
        expect(instanceSource).not.toContain('about.instance.acceleration');
    });
});
