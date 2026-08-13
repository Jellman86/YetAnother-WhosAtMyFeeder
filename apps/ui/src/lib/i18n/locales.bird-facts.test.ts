import { describe, expect, it } from 'vitest';
import de from './locales/de.json';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import itLocale from './locales/it.json';
import ja from './locales/ja.json';
import pt from './locales/pt.json';
import ru from './locales/ru.json';
import zh from './locales/zh.json';
import footerSource from '../components/Footer.svelte?raw';

const locales = { de, en, es, fr, it: itLocale, ja, pt, ru, zh } as const;

describe('footer bird facts', () => {
    it('keeps every locale at the same number of facts', () => {
        // The ticker indexes by position, so a short locale would show a different fact
        // from the one every other language is showing.
        const counts = Object.entries(locales).map(
            ([name, data]) => [name, data.footer.bird_facts.length] as const
        );
        for (const [, count] of counts) {
            expect(count).toBe(en.footer.bird_facts.length);
        }
        expect(en.footer.bird_facts.length).toBe(30);
    });

    it('no longer states the debunked woodpecker claim', () => {
        // Van Wassenbergh et al., Current Biology 2022: the skull works as a stiff hammer,
        // not as a shock absorber.
        for (const data of Object.values(locales)) {
            for (const fact of data.footer.bird_facts) {
                expect(fact).not.toMatch(/absorb shock|air pockets/i);
            }
        }
    });

    it('holds no em dashes and no duplicates', () => {
        for (const [name, data] of Object.entries(locales)) {
            const facts = data.footer.bird_facts;
            expect(new Set(facts).size, `${name} repeats a fact`).toBe(facts.length);
            for (const fact of facts) {
                expect(fact, `${name} uses an em dash`).not.toContain('—');
            }
        }
    });

    it('reads the footer signature from the footer namespace', () => {
        expect(footerSource).toContain("footer.built_with_ai");
        expect(footerSource).not.toContain('about.built_with_ai');
        expect(en.footer.built_with_ai).toBe('Built with AI assistance, and a lot of trial and error');
        // The ticker jumps the whole footer when a longer fact rotates in without this.
        expect(footerSource).toContain('min-h-8');
    });
});
