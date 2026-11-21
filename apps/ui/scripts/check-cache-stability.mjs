// Cache stability of the production bundle: build twice with the same metadata, the second time
// with one harmless line added to the About page, and fail unless only About's own files and the
// entry (which holds the page loaders) are renamed. Every other file keeps its name, so a browser
// keeps it cached across a release that changed one page.
//   npm run check:cache
import { readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build } from 'vite';

const PAGE = 'src/lib/pages/About.svelte';
const CHANGED_PAGE = /^About-/;
const ENTRY = /^index-/;
const out = (name) => join(tmpdir(), `yawamf-cache-check-${process.pid}-${name}`);

process.env.APP_BRANCH = 'cache-check';
process.env.GIT_HASH = 'cachecheck';

async function assetsOf(outDir) {
    await build({ logLevel: 'error', build: { outDir, emptyOutDir: true } });
    return readdirSync(join(outDir, 'assets')).filter((file) => /\.(js|css)$/.test(file));
}

const original = readFileSync(PAGE, 'utf8');
let before;
let after;
try {
    before = await assetsOf(out('before'));
    writeFileSync(PAGE, `${original}\n<span hidden data-cache-check></span>\n`);
    after = await assetsOf(out('after'));
} finally {
    writeFileSync(PAGE, original);
    rmSync(out('before'), { recursive: true, force: true });
    rmSync(out('after'), { recursive: true, force: true });
}

const kept = new Set(before);
const renamed = after.filter((file) => !kept.has(file));
const unexpected = renamed.filter((file) => !CHANGED_PAGE.test(file) && !ENTRY.test(file));
console.log(`${renamed.length} of ${after.length} files renamed: ${renamed.join(', ') || 'none'}`);
if (!renamed.some((file) => CHANGED_PAGE.test(file))) {
    console.error('The About page changed but its chunk kept its name: the check did not change what it meant to.');
    process.exit(1);
}
if (unexpected.length > 0) {
    console.error(`A change to one page renamed files it does not touch, so browsers would fetch them again: ${unexpected.join(', ')}`);
    process.exit(1);
}
