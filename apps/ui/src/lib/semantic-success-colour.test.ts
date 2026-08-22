import { describe, expect, it } from 'vitest';
import tailwindConfigSource from '../../tailwind.config.js?raw';
import diagnosticDialogSource from './components/DiagnosticDialog.svelte?raw';
import connectionStepSource from './components/setup/ConnectionStep.svelte?raw';
import modelStepSource from './components/setup/ModelStep.svelte?raw';
import reviewStepSource from './components/setup/ReviewStep.svelte?raw';
import cameraThumbnailSource from './components/setup/CameraThumbnail.svelte?raw';

/**
 * `layout-patterns.md` §1.3 reserves amber for "this needs a person" and gives
 * green to "confirmed or healthy". The secondary accent cannot carry success:
 * it is a brand colour, and the shipped bluetit theme sets it to amber, which
 * made "passed" and "warning" the same colour inside a single ternary.
 *
 * Success is therefore a semantic ramp of its own, defined once and never
 * re-themed. These tests fail if success starts tracking the brand again.
 */
describe('success is a semantic colour, not the brand accent', () => {
    it('exposes success as its own colour scale, not an alias of the brand accent', () => {
        expect(tailwindConfigSource).toContain('success: {');
        for (const shade of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]) {
            expect(tailwindConfigSource).toContain(`${shade}: 'rgb(var(--success-${shade}) / <alpha-value>)'`);
        }
    });

    it('keeps passed and warning visually distinct in the shared diagnostic dialog', () => {
        expect(diagnosticDialogSource).toContain("stage.state === 'passed' ? 'bg-success-600");
        expect(diagnosticDialogSource).toContain("stage.state === 'warning' ? 'bg-amber-500");
        expect(diagnosticDialogSource).not.toMatch(/stage\.state === 'passed' \? 'bg-accent-/);
    });

    it('paints a successful diagnostic result green rather than amber', () => {
        expect(diagnosticDialogSource).toMatch(/result\.ok \? 'border-success-/);
        expect(diagnosticDialogSource).not.toMatch(/result\.ok \? 'border-accent-/);
    });

    it('paints successful setup checks green', () => {
        expect(connectionStepSource).toMatch(/result\?\.ok \? 'bg-success-/);
        expect(connectionStepSource).not.toMatch(/result\?\.ok \? 'bg-accent-/);
        expect(modelStepSource).toMatch(/rowOk\(m\) \? 'bg-success-/);
        expect(modelStepSource).not.toMatch(/rowOk\(m\) \? 'bg-accent-/);
        expect(reviewStepSource).toMatch(/ok: 'bg-success-/);
        expect(cameraThumbnailSource).toMatch(/frameState === 'ok' \? 'bg-success-/);
    });
});
