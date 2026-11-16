import { describe, expect, expectTypeOf, it } from 'vitest';
import statusLineSource from '../IdentificationStatusLine.svelte?raw';
import modelsSource from './ModelSettings.svelte?raw';
import modelStepSource from '../setup/ModelStep.svelte?raw';
import instanceSource from '../InstanceSummary.svelte?raw';
import type { ClassifierStatus } from '../../api/classifier';

// What names the birds right now is one sentence, built from the classifier's own report, and the
// three places that state it (Models, the setup wizard and About) all render the same component.
describe('one sentence of what names birds right now', () => {
    it('is the same component on Models, in the setup wizard and on About', () => {
        expect(modelsSource).toContain('<IdentificationStatusLine {classifierStatus} />');
        expect(modelStepSource).toContain('<IdentificationStatusLine classifierStatus={status} context="wizard" />');
        expect(instanceSource).toContain('<IdentificationStatusLine classifierStatus={classifier} context="about" />');
        // The old four-column strip of raw runtime facts is gone.
        expect(modelsSource).not.toContain('DetectionStatusBand');
    });

    it('the API type carries the states the sentence words', () => {
        expectTypeOf<NonNullable<ClassifierStatus['worker_in_process_fallback']>['active']>().toEqualTypeOf<boolean>();
        expectTypeOf<ClassifierStatus['runtime_source']>().toEqualTypeOf<
            'worker' | 'planned' | 'in_process' | 'in_process_fallback' | 'default' | null | undefined
        >();
    });

    it('says what needs a person in words and an icon, never by colour alone', () => {
        for (const kind of ["'missing'", "'failed'", "'unavailable'"]) expect(statusLineSource).toContain(`status.kind === ${kind}`);
        expect(statusLineSource).toContain("(status.kind === 'running' && status.fallback !== null)");
        // The runtime's raw error can name paths, so About (which guests may see) never shows it.
        expect(statusLineSource).toContain("context !== 'about'");
        const attention = statusLineSource.slice(statusLineSource.indexOf('needsAttention ?'));
        expect(attention).toContain('text-attention-800');
        expect(statusLineSource).toMatch(/\{#if needsAttention\}\s*<svg/);
        expect(statusLineSource).toContain('role="status"');
    });

    it('never calls a planned device one that has run', () => {
        expect(statusLineSource).toContain("settings.models.status_planned'");
        expect(statusLineSource).toContain('It loads with the first detection.');
    });

    it('points to the runtime report only when there is something in it to check', () => {
        expect(modelsSource).toContain('{#if healthIssueCount > 0}');
        expect(modelsSource).toContain('onclick={openRuntimeReport}');
        expect(modelsSource).toContain("settings.models.status_report_link'");
    });
});
