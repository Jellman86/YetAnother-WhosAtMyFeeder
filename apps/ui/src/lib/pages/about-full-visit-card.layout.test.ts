import { describe, expect, it } from 'vitest';
import aboutPageSource from './About.svelte?raw';
import enLocaleSource from '../i18n/locales/en.json?raw';

describe('about page full-visit feature card', () => {
    it('lists a dedicated full-visit clip feature with its own copy', () => {
        expect(aboutPageSource).toContain("icon: '🎞️'");
        expect(aboutPageSource).toContain("titleKey: 'about.feature_list.full_visit_clip.title'");
        expect(aboutPageSource).toContain("descriptionKey: 'about.feature_list.full_visit_clip.desc'");

        expect(enLocaleSource).toContain('"full_visit_clip"');
        expect(enLocaleSource).toContain('"title": "Full-Visit Clips"');
    });
});
