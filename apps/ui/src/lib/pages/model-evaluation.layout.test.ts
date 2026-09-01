import { describe, expect, it } from 'vitest';
import source from './ModelEvaluation.svelte?raw';
import dashboard from './Dashboard.svelte?raw';

/**
 * Model Evaluation is an owner journey that never received the shared visual
 * language. It was the only page in the app on Tailwind's `gray` ramp while every
 * other page uses `slate`, styled its controls as raw utility classes rather than
 * the kit in app.css, and had no control meeting the touch-target floor.
 */
/** Each `<button>`'s own class attribute, found without relying on the tag's end. */
function buttonClasses(component: string): string[] {
    return component
        .split('<button')
        .slice(1)
        .map((tail) => tail.match(/class="([^"]*)"/)?.[1] ?? '');
}

describe('model evaluation speaks the same visual language as the rest of the app', () => {
    it('uses the palette every other page uses', () => {
        // Dashboard is the reference: slate for neutrals, brand for accent.
        expect(dashboard).not.toMatch(/\bgray-\d/);
        expect(source).not.toMatch(/\bgray-\d/);
        expect(source).not.toMatch(/\bblue-\d/);
    });

    it('uses the shared control kit rather than hand-rolled utilities', () => {
        // CLAUDE.md §5: the kit in app.css is the source of truth for controls.
        // Matching to the tag's closing `>` is unreliable here because an inline
        // `onclick={() => ...}` puts a `>` inside the tag, so read each button's
        // own class attribute instead.
        expect(buttonClasses(source).length).toBe(4);
        for (const cls of buttonClasses(source)) {
            expect(cls, `unstyled button: ${cls.slice(0, 60)}`).toMatch(/\bbtn\b/);
        }
    });

    it('keeps every control at the repository touch-target minimum', () => {
        for (const cls of buttonClasses(source)) {
            expect(cls, `button below the touch floor: ${cls.slice(0, 60)}`).toContain('min-h-11');
        }
    });

    it('names a destructive action by its effect rather than by colour alone', () => {
        // Deleting a run cannot be undone. The word carries the meaning; the colour
        // only reinforces it, which is what WCAG 2.2 AA asks for.
        expect(source).toMatch(/>\s*Delete\s*</);
        // Confirmed, and the confirmation says what leaves rather than just asking.
        expect(source).toContain('Artifacts will be removed');
        // Cannot delete the run that is currently producing results.
        expect(source).toContain('disabled={row.run_id === active?.run_id}');
    });

    it('is still the page that has no translations, and says so where it is tracked', () => {
        // Deliberately not fixed here: this page is entirely hardcoded English, which
        // is its own piece of work and not the visual pass. Recorded on the roadmap
        // rather than left for the next reader to rediscover.
        expect(source).not.toContain("from 'svelte-i18n'");
    });
});
