import { describe, expect, it } from 'vitest';
import { createAnalysisAnnouncements } from './analysis-announcements';

const WORDS = {
    startedOne: (name: string) => `Analysing ${name}`,
    startedMany: (count: number) => `Analysing ${count} ${count === 1 ? 'visit' : 'visits'}`,
    finishedOne: (name: string) => `Analysis finished for ${name}`,
    finishedMany: (count: number) => `Analysis finished for ${count} ${count === 1 ? 'visit' : 'visits'}`
};

/** A clock the test drives: scheduled work runs only when it is told time has passed. */
function harness(names: Record<string, string> = {}) {
    const said: string[] = [];
    let due: { at: number; run: () => void }[] = [];
    let now = 0;
    const announcements = createAnalysisAnnouncements({
        announce: (text) => said.push(text),
        nameOf: (eventId) => names[eventId] ?? null,
        words: () => WORDS,
        delayMs: 400,
        schedule: (run, ms) => {
            const entry = { at: now + ms, run };
            due.push(entry);
            return () => { due = due.filter((item) => item !== entry); };
        }
    });
    const pass = (ms: number) => {
        now += ms;
        const ready = due.filter((item) => item.at <= now);
        due = due.filter((item) => item.at > now);
        for (const item of ready) item.run();
    };
    return { said, announcements, pass };
}

describe('analysis announcements', () => {
    it('says a bulk analysis once when it starts and once when every run has finished', () => {
        const { said, announcements, pass } = harness();
        for (let index = 0; index < 30; index += 1) announcements.started(`event-${index}`, 1);
        pass(400);
        expect(said).toEqual(['Analysing 30 visits']);
        // Runs finish over several seconds; nothing is said until the last one has.
        for (let index = 0; index < 29; index += 1) { announcements.finished(`event-${index}`, 1); pass(500); }
        expect(said).toEqual(['Analysing 30 visits']);
        announcements.finished('event-29', 1);
        pass(400);
        expect(said).toEqual(['Analysing 30 visits', 'Analysis finished for 30 visits']);
    });

    it('names the species when one visit is analysed', () => {
        const { said, announcements, pass } = harness({ a: 'Great Tit' });
        announcements.started('a', 7);
        pass(400);
        announcements.finished('a', 7);
        pass(400);
        expect(said).toEqual(['Analysing Great Tit', 'Analysis finished for Great Tit']);
    });

    it('never repeats a run it has already said finished, as when a correction renames the bird', () => {
        const { said, announcements, pass } = harness({ a: 'Great Tit' });
        announcements.started('a', 7);
        pass(400);
        announcements.finished('a', 7);
        pass(400);
        announcements.finished('a', 7);
        announcements.started('a', 7);
        pass(1000);
        expect(said).toEqual(['Analysing Great Tit', 'Analysis finished for Great Tit']);
    });

    it('says only that it finished when a run ends before its start was announced', () => {
        const { said, announcements, pass } = harness({ a: 'Dunnock' });
        announcements.started('a', 1);
        announcements.finished('a', 1);
        pass(400);
        expect(said).toEqual(['Analysis finished for Dunnock']);
    });

    it('counts one visit whose name is not known here, never inventing one', () => {
        const { said, announcements, pass } = harness();
        announcements.started('unknown', 1);
        pass(400);
        announcements.finished('unknown', 1);
        pass(400);
        expect(said).toEqual(['Analysing 1 visit', 'Analysis finished for 1 visit']);
    });

    it('announces a new run of the same visit again', () => {
        const { said, announcements, pass } = harness({ a: 'Robin' });
        announcements.started('a', 1);
        pass(400);
        announcements.finished('a', 1);
        pass(400);
        announcements.started('a', 2);
        pass(400);
        expect(said).toEqual(['Analysing Robin', 'Analysis finished for Robin', 'Analysing Robin']);
    });
});
