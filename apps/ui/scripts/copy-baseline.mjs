// The copy lint's baseline may only fall. Used by src/lib/i18n/copy-lint.test.ts when it rewrites
// the baseline, and by CI to compare a branch's committed baseline with its base's:
//   node scripts/copy-baseline.mjs check-against <git-ref>
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** Every count in `next` above `allowed`, as "rule scope: before -> after". A scope `allowed` omits allows none. */
export function raisedCounts(allowed, next) {
    const raised = [];
    for (const [rule, scopes] of Object.entries(next)) {
        for (const [scope, count] of Object.entries(scopes)) {
            const limit = allowed[rule]?.[scope] ?? 0;
            if (count > limit) raised.push(`${rule} ${scope}: ${limit} -> ${count}`);
        }
    }
    return raised;
}

/** Every count in `next` below `allowed`: copy that was fixed without lowering the baseline with it. */
export function loweredCounts(allowed, next) {
    const lowered = [];
    for (const [rule, scopes] of Object.entries(allowed)) {
        for (const [scope, limit] of Object.entries(scopes)) {
            const count = next[rule]?.[scope] ?? 0;
            if (count < limit) lowered.push(`${rule} ${scope}: ${limit} -> ${count}`);
        }
    }
    return lowered;
}

/**
 * The baseline after a copy pass: the measured counts, provided none is above the current
 * baseline. A rise is refused, never written, so the updater cannot absorb new debt.
 */
export function lowerBaseline(baseline, measured) {
    const raised = raisedCounts(baseline, measured);
    return raised.length > 0 ? { next: null, raised } : { next: measured, raised: [] };
}

/** Sum per rule, for the one-line summary a reviewer reads. */
export function ruleTotals(counts) {
    return Object.fromEntries(
        Object.entries(counts).map(([rule, scopes]) => [rule, Object.values(scopes).reduce((sum, count) => sum + count, 0)])
    );
}

function main([command, ref]) {
    if (command !== 'check-against' || !ref) {
        console.error('usage: node scripts/copy-baseline.mjs check-against <git-ref>');
        process.exit(2);
    }
    const path = 'apps/ui/src/lib/i18n/copy-lint.baseline.json';
    const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
    let base;
    try {
        base = JSON.parse(execFileSync('git', ['show', `${ref}:${path}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }));
    } catch {
        console.log(`[copy] ${ref} has no baseline yet; this change introduces it.`);
        return;
    }
    const head = JSON.parse(readFileSync(`${root}/${path}`, 'utf8'));
    const raised = raisedCounts(base, head);
    if (raised.length > 0) {
        console.error(`[copy] the baseline allows more than ${ref} did:\n  ${raised.join('\n  ')}\nReword the copy (docs/standards/glossary.md) instead of raising the baseline.`);
        process.exit(1);
    }
    console.log(`[copy] the baseline allows no more than ${ref}.`);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) main(process.argv.slice(2));
