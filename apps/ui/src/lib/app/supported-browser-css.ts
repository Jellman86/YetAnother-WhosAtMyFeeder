/**
 * Tailwind 4 writes every colour that carries an opacity twice: a plain fallback, then the real
 * `color-mix()` value inside `@supports (color: color-mix(in lab, red, red))`. It also ships a
 * block that sets the initial value of each `--tw-*` property for browsers without `@property`.
 * Every browser the app supports (Chrome and Edge 111, Firefox 128, Safari 16.4) has both, so the
 * fallbacks never apply and only cost bytes. Tailwind's Vite plugin has no switch for them.
 *
 * This removes them from a minified stylesheet: each `color-mix()` block is unwrapped, the
 * fallback declarations it overrides are deleted from the rule before it, and the `@property`
 * fallback block is dropped. A later rule with the same selector in the same place always wins
 * over an earlier one, so deleting what it overrides cannot change which value applies.
 */

const COLOR_MIX_SUPPORTS = '@supports (color:color-mix(in lab, red, red))';
const AT_PROPERTY_FALLBACK_SUPPORTS =
    '@supports (((-webkit-hyphens:none)) and (not (margin-trim:block))) or ((-moz-orient:inline) and (not (color:rgb(from red r g b))))';
const RULE_CONTAINERS = /^@(?:layer|media|supports|container)\b/;

interface CssNode {
    prelude: string;
    /** Child rules for a rule container, the raw block text for anything else, null for a statement. */
    body: CssNode[] | string | null;
}

function matchingBrace(css: string, open: number): number {
    let depth = 0;
    let quote = '';
    for (let index = open; index < css.length; index++) {
        const char = css[index];
        if (quote) {
            if (char === '\\') index++;
            else if (char === quote) quote = '';
        } else if (char === '\\') index++;
        else if (char === '"' || char === "'") quote = char;
        else if (char === '{') depth++;
        else if (char === '}' && --depth === 0) return index;
    }
    throw new Error('Unbalanced braces in stylesheet');
}

function parseRules(css: string): CssNode[] {
    const nodes: CssNode[] = [];
    let index = 0;
    while (index < css.length) {
        let cursor = index;
        let quote = '';
        let parens = 0;
        for (; cursor < css.length; cursor++) {
            const char = css[cursor];
            if (quote) {
                if (char === '\\') cursor++;
                else if (char === quote) quote = '';
            } else if (char === '\\') cursor++;
            else if (char === '"' || char === "'") quote = char;
            else if (char === '(') parens++;
            else if (char === ')') parens--;
            else if (parens === 0 && (char === '{' || char === ';')) break;
        }
        if (cursor >= css.length) {
            nodes.push({ prelude: css.slice(index), body: null });
            break;
        }
        const prelude = css.slice(index, cursor);
        if (css[cursor] === ';') {
            nodes.push({ prelude: `${prelude};`, body: null });
            index = cursor + 1;
            continue;
        }
        const close = matchingBrace(css, cursor);
        const block = css.slice(cursor + 1, close);
        nodes.push({ prelude, body: RULE_CONTAINERS.test(prelude) ? parseRules(block) : block });
        index = close + 1;
    }
    return nodes;
}

function serialise(nodes: CssNode[]): string {
    return nodes
        .map(node => {
            if (node.body === null) return node.prelude;
            return `${node.prelude}{${typeof node.body === 'string' ? node.body : serialise(node.body)}}`;
        })
        .join('');
}

function splitDeclarations(block: string): string[] {
    const declarations: string[] = [];
    let start = 0;
    let quote = '';
    let parens = 0;
    for (let index = 0; index < block.length; index++) {
        const char = block[index];
        if (quote) {
            if (char === '\\') index++;
            else if (char === quote) quote = '';
        } else if (char === '\\') index++;
        else if (char === '"' || char === "'") quote = char;
        else if (char === '(') parens++;
        else if (char === ')') parens--;
        else if (char === ';' && parens === 0) {
            declarations.push(block.slice(start, index));
            start = index + 1;
        }
    }
    if (start < block.length) declarations.push(block.slice(start));
    return declarations.filter(declaration => declaration.length > 0);
}

/** A declaration's property and whether it is `!important`: the two things that decide an override. */
function overrideKey(declaration: string): string {
    const property = declaration.slice(0, declaration.indexOf(':')).trim();
    return `${property}${/!important\s*$/.test(declaration) ? '!' : ''}`;
}

function isStyleRule(node: CssNode): node is CssNode & { body: string } {
    return typeof node.body === 'string' && !node.prelude.startsWith('@');
}

function removeOverridden(rules: CssNode[], override: CssNode & { body: string }): void {
    const overridden = new Set(splitDeclarations(override.body).map(overrideKey));
    for (let index = rules.length - 1; index >= 0; index--) {
        const earlier = rules[index];
        if (!isStyleRule(earlier) || earlier.prelude !== override.prelude) continue;
        const kept = splitDeclarations(earlier.body).filter(declaration => !overridden.has(overrideKey(declaration)));
        if (kept.length === 0) rules.splice(index, 1);
        else earlier.body = kept.join(';');
        return;
    }
}

function dropFallbacks(nodes: CssNode[]): CssNode[] {
    const rules: CssNode[] = [];
    for (const node of nodes) {
        if (node.prelude === AT_PROPERTY_FALLBACK_SUPPORTS) continue;
        if (node.prelude === COLOR_MIX_SUPPORTS && Array.isArray(node.body) && node.body.every(isStyleRule)) {
            for (const override of node.body) {
                if (!isStyleRule(override)) continue;
                removeOverridden(rules, override);
                rules.push(override);
            }
            continue;
        }
        rules.push(Array.isArray(node.body) ? { prelude: node.prelude, body: dropFallbacks(node.body) } : node);
    }
    return rules;
}

/** Removes the fallbacks no supported browser reads from a minified Tailwind 4 stylesheet. */
export function dropUnsupportedBrowserFallbacks(css: string): string {
    return serialise(dropFallbacks(parseRules(css)));
}

/** True when a stylesheet still carries a fallback this module exists to remove. */
export function hasUnsupportedBrowserFallbacks(css: string): boolean {
    return /@supports \(color:\s*color-mix\(/.test(css) || css.includes('(not (margin-trim:block))');
}
