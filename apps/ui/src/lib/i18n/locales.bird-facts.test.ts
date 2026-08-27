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
        for (const [name, data] of Object.entries(locales)) {
            const longest = Math.max(...data.footer.bird_facts.map((fact) => fact.length));
            expect(longest, `${name} has a fact too long for the reserved mobile rail`).toBeLessThanOrEqual(180);
        }
    });

    it('does not repeat debunked or overstated bird claims', () => {
        // Van Wassenbergh et al., Current Biology 2022: the skull works as a stiff hammer,
        // not as a shock absorber.
        for (const data of Object.values(locales)) {
            for (const fact of data.footer.bird_facts) {
                expect(fact).not.toMatch(/absorb shock|air pockets/i);
            }
        }
        expect(en.footer.bird_facts.join(' ')).not.toMatch(
            /only birds that can hover|people who have wronged|toilets flushing|scare other birds away|feathers weigh more|few animals that can recognize|penguins propose|geese have teeth|around 30 percent|months later|every bird walking up has missed|only its seven|bare tuft|without ever closing/i
        );
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
    });

    it('keeps a stable mobile footprint and honours reduced motion', () => {
        expect(footerSource).toContain('min-h-28');
        expect(footerSource).toContain('sm:min-h-10');
        expect(footerSource).toContain('motion-safe:transition-opacity');
        expect(footerSource).toContain("matchMedia('(prefers-reduced-motion: reduce)')");
    });

    it('handles empty facts and clears both timers on teardown', () => {
        expect(footerSource).toContain('if (birdFacts.length === 0) return;');
        expect(footerSource).toContain('clearInterval(interval)');
        expect(footerSource).toContain('clearTimeout(transitionTimeout)');
    });
});
