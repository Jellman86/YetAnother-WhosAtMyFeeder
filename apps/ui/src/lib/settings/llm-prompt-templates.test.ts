import { describe, expect, it } from 'vitest';
import { promptTemplatesFor } from './llm-prompt-templates';

describe('built-in prompt templates', () => {
    it('offers analysis, conversation and chart templates in the reader language', () => {
        const german = promptTemplatesFor('classic', 'de-DE');
        expect(german.analysis).not.toBe(promptTemplatesFor('classic', 'en').analysis);
        for (const template of Object.values(german)) expect(template.length).toBeGreaterThan(0);
    });

    it('falls back to English for a language without templates', () => {
        expect(promptTemplatesFor('field', 'nl')).toEqual(promptTemplatesFor('field', 'en'));
    });

    it('falls back to English classic for a style it does not know', () => {
        expect(promptTemplatesFor('poetry', 'fr')).toEqual(promptTemplatesFor('classic', 'en'));
    });
});
