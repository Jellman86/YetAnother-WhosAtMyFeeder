import { describe, expect, it } from 'vitest';
import deFooter from './locales/de/project_notes.json';
import enFooter from './locales/en/project_notes.json';
import esFooter from './locales/es/project_notes.json';
import frFooter from './locales/fr/project_notes.json';
import itFooter from './locales/it/project_notes.json';
import jaFooter from './locales/ja/project_notes.json';
import ptFooter from './locales/pt/project_notes.json';
import ruFooter from './locales/ru/project_notes.json';
import zhFooter from './locales/zh/project_notes.json';
import footerSource from '../components/Footer.svelte?raw';
import notesSource from '../components/ProjectNotes.svelte?raw';
import aboutSource from '../pages/About.svelte?raw';

const de = { footer: deFooter };
const en = { footer: enFooter };
const es = { footer: esFooter };
const fr = { footer: frFooter };
const itLocale = { footer: itFooter };
const ja = { footer: jaFooter };
const pt = { footer: ptFooter };
const ru = { footer: ruFooter };
const zh = { footer: zhFooter };

const locales = { de, en, es, fr, it: itLocale, ja, pt, ru, zh } as const;

describe('project notes and bird facts', () => {
    it('keeps every locale at the same number of facts', () => {
        // The facts are indexed by position, so a short locale would show a different fact
        // from the one every other language is showing.
        const counts = Object.entries(locales).map(
            ([name, data]) => [name, data.footer.bird_facts.length] as const
        );
        for (const [, count] of counts) {
            expect(count).toBe(en.footer.bird_facts.length);
        }
        expect(en.footer.bird_facts.length).toBe(29);
        for (const [name, data] of Object.entries(locales)) {
            const longest = Math.max(...data.footer.bird_facts.map((fact) => fact.length));
            expect(longest, `${name} has a fact too long to read at a glance`).toBeLessThanOrEqual(180);
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

    it('keeps the facts and the project line off every operational page, on About', () => {
        // The footer of a working page carries the version, the licence and the links only.
        expect(footerSource).not.toMatch(/bird_facts|did_you_know|built_with_ai|project_notes/);
        expect(footerSource).toContain("common.mit_license");
        expect(footerSource).toContain('v{version}');
        expect(aboutSource).toContain('<ProjectNotes />');
        expect(notesSource).toContain("project_notes.built_with_ai");
        expect(notesSource).toContain("project_notes.bird_facts");
        expect(en.footer.built_with_ai).toBe('Built with AI assistance, and a lot of trial and error');
    });

    it('drops the filler joke and writes no hyphen as a dash in English', () => {
        expect(en.footer.bird_facts.join(' ')).not.toMatch(/aren't real|surveillance drones/i);
        expect(en.footer.bird_facts.filter((fact) => fact.includes(' - '))).toEqual([]);
    });

    it('changes the fact only when asked, never by itself', () => {
        // Text that turns over by itself needs a way to pause it (WCAG 2.2.2).
        expect(notesSource).not.toMatch(/setInterval|setTimeout/);
        expect(notesSource).toContain('data-project-notes-another');
    });
});
