import { describe, expect, it } from 'vitest';
import { matchingPromptStyle, promptTemplatesFor } from './llm-prompt-templates';

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

describe('which built-in style the saved templates are', () => {
    it('names the style whose wording the templates hold, in the reader language', () => {
        expect(matchingPromptStyle(promptTemplatesFor('field', 'de'), 'de-DE')).toBe('field');
        expect(matchingPromptStyle(promptTemplatesFor('classic', 'en'), 'en-GB')).toBe('classic');
    });

    it('names none once the wording has been edited', () => {
        const edited = { ...promptTemplatesFor('classic', 'en'), chart: 'Describe the chart.' };
        expect(matchingPromptStyle(edited, 'en')).toBeNull();
        expect(matchingPromptStyle({ analysis: '', conversation: '', chart: '' }, 'en')).toBeNull();
    });
});
