// The design-token ratchet's baseline may only fall. Used by design-tokens.ratchet.test.ts when it
// rewrites the baseline, and by CI to compare a branch's committed baseline with its base's:
//   node scripts/token-baseline.mjs check-against <git-ref>
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const KINDS = ['palette', 'dark', 'arbitrary'];
const ZERO = { palette: 0, dark: 0, arbitrary: 0 };

/** Every count in `next` that is above `allowed` (a file `allowed` does not list allows nothing). */
export function raisedCounts(allowed, next) {
    const raised = [];
    for (const [file, counts] of Object.entries(next)) {
        const limit = allowed[file] ?? ZERO;
        for (const kind of KINDS) {
            if ((counts[kind] ?? 0) > (limit[kind] ?? 0)) raised.push(`${file}: ${kind} ${limit[kind] ?? 0} -> ${counts[kind]}`);
        }
    }
    return raised;
}

/**
 * The baseline after a migration: the measured counts, provided none is above the current
 * baseline. A rise is refused, never written, so the updater cannot absorb a new raw colour.
 */
export function lowerBaseline(baseline, measured) {
    const raised = raisedCounts(baseline, measured);
    return raised.length > 0 ? { next: null, raised } : { next: measured, raised: [] };
}

function main([command, ref]) {
    if (command !== 'check-against' || !ref) {
        console.error('usage: node scripts/token-baseline.mjs check-against <git-ref>');
        process.exit(2);
    }
    const path = 'apps/ui/src/design-tokens.baseline.json';
    const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
    let base;
    try {
        base = JSON.parse(execFileSync('git', ['show', `${ref}:${path}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }));
    } catch {
        console.log(`[tokens] ${ref} has no baseline yet; this change introduces it.`);
        return;
    }
    const head = JSON.parse(readFileSync(`${root}/${path}`, 'utf8'));
    const raised = raisedCounts(base, head);
    if (raised.length > 0) {
        console.error(`[tokens] the baseline allows more than ${ref} did:\n  ${raised.join('\n  ')}\nUse the semantic tokens instead of raising the baseline.`);
        process.exit(1);
    }
    console.log(`[tokens] the baseline allows no more than ${ref}.`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
