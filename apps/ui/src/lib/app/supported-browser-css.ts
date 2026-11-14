import postcss, { type AtRule, type ChildNode, type Declaration, type Rule } from 'postcss';

/**
 * Tailwind 4 writes every theme-driven colour that carries an opacity twice: a plain fallback,
 * then the real `color-mix()` value inside `@supports (color: color-mix(in lab, red, red))`. It
 * also ships a block that sets the initial value of each `--tw-*` property for browsers without
 * `@property`. Every browser the app supports (Chrome and Edge 111, Firefox 128, Safari 16.4)
 * has both, so the fallbacks never apply and only cost bytes. Tailwind's Vite plugin has no
 * switch for them.
 *
 * This step removes them from a built stylesheet. It is safe by construction: a block is
 * unwrapped only when it matches, exactly, a shape Tailwind has been seen to write, and anything
 * else is left as written. A block left in place is still valid CSS that every browser reads
 * correctly, so the worst outcome is a few extra bytes. It never fails a build and never guesses.
 * A change in Tailwind's output is caught by the unit test that compiles the real stylesheet.
 */

/** The Tailwind release whose output the unit tests copy. An upgrade refreshes them on purpose. */
export const FIXTURE_TAILWIND_VERSION = '4.3.5';

const COLOR_MIX_CONDITION = '(color:color-mix(inlab,red,red))';
const AT_PROPERTY_FALLBACK_CONDITION =
    '(((-webkit-hyphens:none))and(not(margin-trim:block)))or((-moz-orient:inline)and(not(color:rgb(fromredrgb))))';
const UNIVERSAL_SELECTOR = '*,:before,:after,::backdrop';

/** The three fallbacks Tailwind has been seen to write, and nothing looser. */
const HEX_FALLBACK = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/;
const CURRENT_COLOUR_FALLBACKS = new Set(['currentColor', 'currentcolor']);
const SRGB_MIX_FALLBACK = /^color-mix\(in srgb, .+ \d+(?:\.\d+)?%, transparent\)$/;
/** What an arbitrary variable colour with an opacity gets. Recognised, and always kept. */
const VARIABLE_FALLBACK = /^var\(--[\w-]+\)$/;
const OKLAB_MIX_OVERRIDE = 'color-mix(in oklab, ';
const BORDER_SIDE = '(?:top|right|bottom|left|inline|block|inline-start|inline-end|block-start|block-end)';
const BORDER_COLOUR = new RegExp(`^border(?:-${BORDER_SIDE})?(?:-color)?$`);

interface RetainedFallback {
    /** The selector of the rule inside the block, or the block's own condition. */
    selector: string;
    reason: string;
}

interface FallbackRemoval {
    css: string;
    unwrapped: number;
    retained: RetainedFallback[];
}

/**
 * An `@supports` condition as its tokens joined together: comments and whitespace dropped,
 * strings kept whole, the rest lower-cased. Two spellings of one condition give one result.
 */
function conditionTokens(atRule: AtRule): string {
    const source = atRule.raws.params?.raw ?? atRule.params;
    let tokens = '';
    for (let index = 0; index < source.length; index++) {
        const char = source[index];
        if (char === '/' && source[index + 1] === '*') {
            const end = source.indexOf('*/', index + 2);
            index = end < 0 ? source.length : end + 1;
        } else if (char === '"' || char === "'") {
            let end = index + 1;
            while (end < source.length && source[end] !== char) end += source[end] === '\\' ? 2 : 1;
            tokens += source.slice(index, end + 1);
            index = end;
        } else if (!/\s/.test(char)) {
            tokens += char.toLowerCase();
        }
    }
    return tokens;
}

function meaningful(nodes: ChildNode[] | undefined): ChildNode[] {
    return (nodes ?? []).filter(node => node.type !== 'comment');
}

function declarationsOnly(rule: Rule): Declaration[] | null {
    const nodes = meaningful(rule.nodes);
    return nodes.every((node): node is Declaration => node.type === 'decl') ? nodes : null;
}

function previousRule(atRule: AtRule): ChildNode | undefined {
    let node = atRule.prev();
    while (node?.type === 'comment') node = node.prev();
    return node;
}

/** Whether two properties can set the same colour, as a shorthand and its longhand do. */
function setsTheSameColour(property: string, other: string): boolean {
    if (property.startsWith('--') || other.startsWith('--')) return false;
    if (other.startsWith(`${property}-`) || property.startsWith(`${other}-`)) return true;
    return BORDER_COLOUR.test(property) && BORDER_COLOUR.test(other);
}

/** The fallback declarations a block's rule overrides, or the reason the pair is left alone. */
function fallbacksFor(override: Declaration[], fallbackRule: Declaration[]): Declaration[] | string {
    const fallbacks: Declaration[] = [];
    for (const declaration of override) {
        if (!declaration.value.startsWith(OKLAB_MIX_OVERRIDE)) return 'the override is not an oklab color-mix value';
        const matches = fallbackRule.filter(candidate => candidate.prop === declaration.prop);
        if (matches.length !== 1) return `${declaration.prop} is set ${matches.length} times in the fallback rule`;
        const [fallback] = matches;
        if (Boolean(fallback.important) !== Boolean(declaration.important)) return `${declaration.prop} differs in !important`;
        const rival = fallbackRule.find(candidate => candidate !== fallback && setsTheSameColour(declaration.prop, candidate.prop));
        if (rival) return `${rival.prop} in the fallback rule also sets ${declaration.prop}`;
        if (VARIABLE_FALLBACK.test(fallback.value)) return 'the fallback is a variable, which is kept';
        const known = HEX_FALLBACK.test(fallback.value) || CURRENT_COLOUR_FALLBACKS.has(fallback.value) || SRGB_MIX_FALLBACK.test(fallback.value);
        if (!known) return 'the fallback is not a value Tailwind writes';
        fallbacks.push(fallback);
    }
    return fallbacks;
}

/** Unwraps one color-mix block, or returns why it was left as written. */
function unwrapColorMix(block: AtRule): string | null {
    const children = meaningful(block.nodes);
    const [override] = children;
    if (children.length !== 1 || override.type !== 'rule') return 'the block does not hold exactly one rule';
    const overrideDeclarations = declarationsOnly(override);
    if (!overrideDeclarations) return 'the block does not hold exactly one rule';

    const before = previousRule(block);
    if (!before) return 'no rule comes before the block';
    // Selectors are compared as PostCSS read them: `.a b` and `.ab` are different rules.
    if (before.type !== 'rule' || before.selector !== override.selector) return 'the rule before the block has a different selector';
    const fallbackDeclarations = declarationsOnly(before);
    if (!fallbackDeclarations) return 'the rule before the block has a different selector';

    const fallbacks = fallbacksFor(overrideDeclarations, fallbackDeclarations);
    if (typeof fallbacks === 'string') return fallbacks;

    for (const fallback of fallbacks) fallback.remove();
    if (meaningful(before.nodes).length === 0) before.remove();
    block.replaceWith(override);
    return null;
}

/** Drops the `@property` fallback block, or returns why it was left as written. */
function dropAtPropertyFallback(block: AtRule): string | null {
    const onlyInitialValues = meaningful(block.nodes).every(node => {
        if (node.type !== 'rule' || node.selector !== UNIVERSAL_SELECTOR) return false;
        return declarationsOnly(node)?.every(declaration => declaration.prop.startsWith('--tw-')) ?? false;
    });
    if (!onlyInitialValues) return 'the @property fallback block holds more than initial values';
    block.remove();
    return null;
}

/**
 * Removes the fallbacks no supported browser reads, wherever a block matches Tailwind's shape
 * exactly. Everything else, including a stylesheet that does not parse, comes back as written.
 */
export function dropUnsupportedBrowserFallbacks(css: string): FallbackRemoval {
    const untouched: FallbackRemoval = { css, unwrapped: 0, retained: [] };
    let root: postcss.Root;
    try {
        root = postcss.parse(css);
    } catch {
        return untouched;
    }

    const colorMix: AtRule[] = [];
    const atProperty: AtRule[] = [];
    root.walkAtRules(atRule => {
        if (atRule.name.toLowerCase() !== 'supports') return;
        const tokens = conditionTokens(atRule);
        if (tokens === COLOR_MIX_CONDITION) colorMix.push(atRule);
        else if (tokens === AT_PROPERTY_FALLBACK_CONDITION) atProperty.push(atRule);
    });

    const retained: RetainedFallback[] = [];
    let unwrapped = 0;
    for (const block of colorMix) {
        const selector = meaningful(block.nodes).map(node => (node.type === 'rule' ? node.selector : `@${node.type}`)).join(', ');
        const reason = unwrapColorMix(block);
        if (reason) retained.push({ selector, reason });
        else unwrapped++;
    }
    for (const block of atProperty) {
        const reason = dropAtPropertyFallback(block);
        if (reason) retained.push({ selector: `@supports ${block.params}`, reason });
        else unwrapped++;
    }
    return unwrapped === 0 ? { ...untouched, retained } : { css: root.toString(), unwrapped, retained };
}
