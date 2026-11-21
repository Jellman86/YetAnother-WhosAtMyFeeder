import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import diagnosticDialogSource from './components/DiagnosticDialog.svelte?raw';
import connectionStepSource from './components/setup/ConnectionStep.svelte?raw';
import modelStepSource from './components/setup/ModelStep.svelte?raw';
import reviewStepSource from './components/setup/ReviewStep.svelte?raw';
import cameraThumbnailSource from './components/setup/CameraThumbnail.svelte?raw';

const appCss = readFileSync(new URL('../app.css', import.meta.url), 'utf8');

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
        for (const shade of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]) {
            expect(appCss).toContain(`--color-success-${shade}: rgb(var(--success-${shade}));`);
        }
    });

    it('keeps passed and warning visually distinct in the shared diagnostic dialog', () => {
        expect(diagnosticDialogSource).toContain("if (state === 'passed') return 'ok';");
        expect(diagnosticDialogSource).toContain("if (state === 'warning') return 'attention';");
        expect(diagnosticDialogSource).toContain('TONE_INK[stageTone(stage.state)]');
    });

    it('paints a successful diagnostic result green rather than amber', () => {
        expect(diagnosticDialogSource).toMatch(/result\.ok \? 'border-status-ok-line bg-status-ok-soft'/);
    });

    it('paints successful setup checks green', () => {
        // The ok status tokens, never the accent: green says it worked, the brand says nothing about state.
        expect(connectionStepSource).toMatch(/row\.ok \? 'text-status-ok'/);
        expect(connectionStepSource).toContain("<StatusIcon tone={row.ok ? 'ok' : 'fail'}");
        expect(connectionStepSource).not.toMatch(/row\.ok \? '(?:bg|text)-accent/);
        expect(modelStepSource).toMatch(/rowOk\(m\) \? 'bg-status-ok-soft text-status-ok'/);
        expect(modelStepSource).not.toMatch(/rowOk\(m\) \? 'bg-accent-/);
        expect(reviewStepSource).toMatch(/ok: 'bg-status-ok-soft/);
        expect(cameraThumbnailSource).toMatch(/frameState === 'ok' \? 'bg-status-ok-line'/);
    });
});
