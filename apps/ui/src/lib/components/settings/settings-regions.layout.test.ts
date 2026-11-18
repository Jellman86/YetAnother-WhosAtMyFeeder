// Node types are intentionally absent from the browser tsconfig; this audit runs under Vitest's Node environment.
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import { parse } from 'svelte/compiler';
import { describe, expect, it } from 'vitest';

/**
 * A part split across a section's first screen and its More options is drawn twice, once with
 * `region="main"` and once with `region="more"`. A card outside both regions would be drawn twice, and
 * one inside both would contradict itself, so every card belongs to exactly one.
 */
const REGION_PARTS = ['ConnectionSettings', 'NotificationSettings', 'DataSettings', 'AppearanceSettings', 'AccessibilitySettings'];

type Region = 'main' | 'more';
interface AstNode {
    type: string;
    name?: string;
    start: number;
    end: number;
    test?: AstNode;
    consequent?: { nodes: AstNode[] };
    alternate?: { nodes: AstNode[] } | null;
    fragment?: { nodes: AstNode[] };
    body?: { nodes: AstNode[] };
    nodes?: AstNode[];
}

/** The region a block's condition selects, for `region === '…'` and the `showMain`/`showMore` flags. */
function regionOf(source: string, test: AstNode): Region | null {
    const text = source.slice(test.start, test.end).trim();
    const exact = /^region === '(main|more)'$/.exec(text);
    if (exact) return exact[1] as Region;
    if (text === 'showMain') return 'main';
    if (text === 'showMore') return 'more';
    return null;
}

function cardsByRegion(source: string): Array<{ at: number; regions: Region[] }> {
    const ast = parse(source, { modern: true }) as unknown as { fragment: { nodes: AstNode[] } };
    const cards: Array<{ at: number; regions: Region[] }> = [];
    const walk = (nodes: AstNode[], regions: Region[]): void => {
        for (const node of nodes) {
            if (node.type === 'IfBlock' && node.test) {
                const region = regionOf(source, node.test);
                const other: Region | null = region === 'main' ? 'more' : region === 'more' ? 'main' : null;
                walk(node.consequent?.nodes ?? [], region ? [...regions, region] : regions);
                walk(node.alternate?.nodes ?? [], other && /^region === /.test(source.slice(node.test.start, node.test.end).trim()) ? [...regions, other] : regions);
                continue;
            }
            if (node.type === 'Component' && node.name === 'SettingsCard') cards.push({ at: node.start, regions });
            for (const child of [node.fragment?.nodes, node.body?.nodes, node.consequent?.nodes, node.alternate?.nodes, node.nodes]) {
                if (child) walk(child, regions);
            }
        }
    };
    walk(ast.fragment.nodes, []);
    return cards;
}

describe('every card of a part drawn in two regions', () => {
    it.each(REGION_PARTS)('%s draws each card in exactly one region', (part) => {
        const source: string = readFileSync(new URL(`./${part}.svelte`, import.meta.url), 'utf-8');
        expect(source).toMatch(/region: 'main' \| 'more';/);
        const cards = cardsByRegion(source);
        expect(cards.length, part).toBeGreaterThan(0);
        const line = (at: number) => source.slice(0, at).split('\n').length;
        const misplaced = cards.filter((card) => new Set(card.regions).size !== 1).map((card) => `line ${line(card.at)}: ${card.regions.join(', ') || 'no region'}`);
        expect(misplaced, part).toEqual([]);
    });

    it('fails a card left outside both regions', () => {
        const source = `<script lang="ts">let { region }: { region: 'main' | 'more'; } = $props();</script>\n{#if region === 'main'}<SettingsCard title="a" />{:else}<SettingsCard title="b" />{/if}\n<SettingsCard title="twice" />`;
        expect(cardsByRegion(source).map((card) => card.regions)).toEqual([['main'], ['more'], []]);
    });
});
