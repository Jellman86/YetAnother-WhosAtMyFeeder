import { describe, expect, it } from 'vitest';
import { ResetCountChanged, resetWithConfirmedCount, type ResetQuestion } from './reset-history';

/** An owner who reads the count in the dialog and then answers each question in turn. */
function owner(answers: boolean[], asked: ResetQuestion[] = []) {
    return async (question: ResetQuestion): Promise<boolean> => {
        asked.push(question);
        if (question.kind === 'count') await question.read().catch(() => undefined);
        return answers.shift() ?? false;
    };
}

describe('deleting all history with the number that was confirmed', () => {
    it('sends the count the owner was shown, so the server deletes that number or refuses', async () => {
        const sent: Array<number | null> = [];
        const result = await resetWithConfirmedCount({
            readCount: async () => 931,
            ask: owner([true]),
            reset: async (expected) => { sent.push(expected); return 'deleted'; }
        });
        expect(sent).toEqual([931]);
        expect(result).toBe('deleted');
    });

    it('asks again with the new number when detections arrived after the count, and deletes nothing in between', async () => {
        const asked: ResetQuestion[] = [];
        const sent: Array<number | null> = [];
        const result = await resetWithConfirmedCount({
            readCount: async () => 931,
            ask: owner([true, true], asked),
            reset: async (expected) => {
                sent.push(expected);
                if (expected === 931) throw new ResetCountChanged(933);
                return 'deleted';
            }
        });
        expect(asked.map((question) => question.kind)).toEqual(['count', 'changed']);
        expect(asked[1]).toEqual({ kind: 'changed', count: 933 });
        expect(sent).toEqual([931, 933]);
        expect(result).toBe('deleted');
    });

    it('deletes nothing when the owner declines the new number', async () => {
        const sent: Array<number | null> = [];
        const result = await resetWithConfirmedCount({
            readCount: async () => 931,
            ask: owner([true, false]),
            reset: async (expected) => { sent.push(expected); throw new ResetCountChanged(933); }
        });
        expect(sent).toEqual([931]);
        expect(result).toBeNull();
    });

    it('sends no number when the count could not be read, because the question stated none', async () => {
        const sent: Array<number | null> = [];
        await resetWithConfirmedCount({
            readCount: async () => { throw new Error('503'); },
            ask: owner([true]),
            reset: async (expected) => { sent.push(expected); return 'deleted'; }
        });
        expect(sent).toEqual([null]);
    });

    it('never calls the reset when the first question is cancelled', async () => {
        let called = false;
        const result = await resetWithConfirmedCount({
            readCount: async () => 931,
            ask: owner([false]),
            reset: async () => { called = true; return 'deleted'; }
        });
        expect(called).toBe(false);
        expect(result).toBeNull();
    });

    it('lets any other failure through', async () => {
        await expect(resetWithConfirmedCount({
            readCount: async () => 1,
            ask: owner([true]),
            reset: async () => { throw new Error('disk full'); }
        })).rejects.toThrow('disk full');
    });
});
