import postcss, { type AtRule, type ChildNode, type Declaration, type Rule } from 'postcss';

/**
 * Tailwind 4 writes every theme-driven colour that carries an opacity twice: a plain fallback,
 * then the real `color-mix()` value inside `@supports (color: color-mix(in lab, red, red))`. It
 * also ships a block that sets the initial value of each `--tw-*` property for browsers without
 * `@property`. Every browser the app supports (Chrome and Edge 111, Firefox 128, Safari 16.4)
 * has both, so the fallbacks never apply and only cost bytes. Tailwind's Vite plugin has no
 * switch for them.
 *
 * This removes them from a built stylesheet, and only where it can prove what it is removing.
 * A block is unwrapped when it holds one rule, the rule immediately before it has the same
 * selector, and every declaration it overrides is set exactly once there, with the same
 * `!important`, no shorthand or longhand beside it that sets the same colour, and one of the
 * three values Tailwind writes as a fallback. Anything else is left exactly as it was and
 * reported, so the build can refuse to ship it.
 */

/** The Tailwind release whose output the unit tests copy. An upgrade refreshes them on purpose. */
export const FIXTURE_TAILWIND_VERSION = '4.3.5';

const COLOR_MIX_CONDITION = '(color:color-mix(inlab,red,red))';
const AT_PROPERTY_FALLBACK_CONDITION =
    '(((-webkit-hyphens:none))and(not(margin-trim:block)))or((-moz-orient:inline)and(not(color:rgb(fromredrgb))))';
const UNIVERSAL_SELECTOR = '*,:before,:after,::backdrop';

/** The fallbacks Tailwind writes: a hex literal, `currentColor`, or an sRGB mix with transparent. */
const TAILWIND_FALLBACK = /^(?:#[0-9a-f]{3,8}|currentcolor|color-mix\(in srgb,.*,\s*transparent\))$/i;
const BORDER_SIDE = '(?:top|right|bottom|left|inline|block|inline-start|inline-end|block-start|block-end)';
const BORDER_COLOUR = new RegExp(`^border(?:-${BORDER_SIDE})?(?:-color)?$`);

interface KeptFallback {
    /** The selector of the rule inside the block, or the block's own condition. */
    selector: string;
    reason: string;
}

interface FallbackRemoval {
    css: string;
    removed: number;
    kept: KeptFallback[];
}

function condition(atRule: AtRule): string {
    return atRule.params.replace(/\s+/g, '').toLowerCase();
}

function withoutSpaces(text: string): string {
    return text.replace(/\s+/g, '');
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

/** The fallback declarations a block's rule overrides, or the reason the pair cannot be trusted. */
function fallbacksFor(override: Declaration[], fallbackRule: Declaration[]): Declaration[] | string {
    const fallbacks: Declaration[] = [];
    for (const declaration of override) {
        if (!declaration.value.includes('color-mix(')) return `${declaration.value} is not a color-mix value`;
        const matches = fallbackRule.filter(candidate => candidate.prop === declaration.prop);
        if (matches.length !== 1) return `${declaration.prop} is set ${matches.length} times in the fallback rule`;
        const [fallback] = matches;
        if (Boolean(fallback.important) !== Boolean(declaration.important)) return `${declaration.prop} differs in !important`;
        const rival = fallbackRule.find(candidate => candidate !== fallback && setsTheSameColour(declaration.prop, candidate.prop));
        if (rival) return `${rival.prop} in the fallback rule also sets ${declaration.prop}`;
        if (!TAILWIND_FALLBACK.test(fallback.value)) return `${fallback.value} is not a fallback Tailwind writes`;
        fallbacks.push(fallback);
    }
    return fallbacks;
}

/** Unwraps one color-mix block, or returns why it was left alone. */
function unwrapColorMix(block: AtRule): string | null {
    const children = meaningful(block.nodes);
    const [override] = children;
    if (children.length !== 1 || override.type !== 'rule') return 'the block does not hold exactly one rule';
    const overrideDeclarations = declarationsOnly(override);
    if (!overrideDeclarations) return 'the block does not hold exactly one rule';

    const before = previousRule(block);
    if (!before) return 'no rule comes before the block';
    if (before.type !== 'rule' || withoutSpaces(before.selector) !== withoutSpaces(override.selector)) {
        return 'the rule before the block has a different selector';
    }
    const fallbackDeclarations = declarationsOnly(before);
    if (!fallbackDeclarations) return 'the rule before the block has a different selector';

    const fallbacks = fallbacksFor(overrideDeclarations, fallbackDeclarations);
    if (typeof fallbacks === 'string') return fallbacks;

    for (const fallback of fallbacks) fallback.remove();
    if (meaningful(before.nodes).length === 0) before.remove();
    block.replaceWith(override);
    return null;
}

/** Drops the `@property` fallback block, or returns why it was left alone. */
function dropAtPropertyFallback(block: AtRule): string | null {
    const onlyInitialValues = meaningful(block.nodes).every(node => {
        if (node.type !== 'rule' || withoutSpaces(node.selector) !== UNIVERSAL_SELECTOR) return false;
        return declarationsOnly(node)?.every(declaration => declaration.prop.startsWith('--tw-')) ?? false;
    });
    if (!onlyInitialValues) return 'the @property fallback block holds more than initial values';
    block.remove();
    return null;
}

function fallbackBlocks(css: string): { root: postcss.Root; colorMix: AtRule[]; atProperty: AtRule[] } {
    const root = postcss.parse(css);
    const colorMix: AtRule[] = [];
    const atProperty: AtRule[] = [];
    root.walkAtRules(atRule => {
        if (atRule.name.toLowerCase() !== 'supports') return;
        if (condition(atRule) === COLOR_MIX_CONDITION) colorMix.push(atRule);
        else if (condition(atRule) === AT_PROPERTY_FALLBACK_CONDITION) atProperty.push(atRule);
    });
    return { root, colorMix, atProperty };
}

/** Removes the fallbacks no supported browser reads, wherever the pair is provably Tailwind's. */
export function dropUnsupportedBrowserFallbacks(css: string): FallbackRemoval {
    const { root, colorMix, atProperty } = fallbackBlocks(css);
    if (colorMix.length + atProperty.length === 0) return { css, removed: 0, kept: [] };

    const kept: KeptFallback[] = [];
    let removed = 0;
    for (const block of colorMix) {
        const selector = meaningful(block.nodes).map(node => (node.type === 'rule' ? node.selector : `@${node.type}`)).join(', ');
        const reason = unwrapColorMix(block);
        if (reason) kept.push({ selector, reason });
        else removed++;
    }
    for (const block of atProperty) {
        const reason = dropAtPropertyFallback(block);
        if (reason) kept.push({ selector: `@supports ${block.params}`, reason });
        else removed++;
    }
    return { css: removed === 0 ? css : root.toString(), removed, kept };
}

/** True when a stylesheet still carries a fallback this module exists to remove. */
export function hasUnsupportedBrowserFallbacks(css: string): boolean {
    const { colorMix, atProperty } = fallbackBlocks(css);
    return colorMix.length + atProperty.length > 0;
}
