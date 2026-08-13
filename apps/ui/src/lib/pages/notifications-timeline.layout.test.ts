import { describe, expect, it } from 'vitest';
import source from './Notifications.svelte?raw';
import en from '../i18n/locales/en.json';

describe('Notifications timeline layout', () => {
    it('replaces the tab split with one filtered river', () => {
        expect(source).toContain('data-notifications-timeline');
        // A failed job is the most urgent thing this app says; it must not sit behind a tab.
        expect(source).not.toContain('activeTab');
        expect(source).not.toContain('getNotificationsTabFromPath');
        expect(source).toContain('groupNotifications(');
        for (const name of ['all', 'birds', 'updates', 'jobs', 'errors']) {
            expect(en.notifications[`filter_${name}` as keyof typeof en.notifications]).toBeTruthy();
        }
    });

    it('hides owner-only filters rather than showing them empty', () => {
        expect(source).toContain('isOwner || !isOwnerOnlyFilter(name)');
        // Leaving an owner filter selected as access drops must not strand a guest on it.
        expect(source).toContain("!isOwner && isOwnerOnlyFilter(filter) ? 'all' : filter");
    });

    it('keeps amber for what needs a person', () => {
        // The progress bar used to run a three colour gradient through the attention colour.
        expect(source).not.toContain('from-accent-500');
        expect(source).toContain("running: 'bg-brand-500 border-brand-500'");
        expect(source).toContain("attention: 'bg-accent-500 border-accent-500'");
    });

    it('makes opening a notification a real control', () => {
        // Was a <p> that looked like an action and could not be focused or clicked.
        expect(source).toContain('onclick={() => openItem(item)}');
        expect(source).toContain('btn btn-secondary focus-ring');
    });

    it('states what the empty page will hold instead of that it is empty', () => {
        expect(source).toContain('notifications.empty_title');
        expect(source).toContain('notifications.empty_action');
        expect(en.notifications.empty_body).toContain('newest first');
    });

    it('does not repeat the date on rows the group heading already dates', () => {
        expect(source).toContain("group.key === 'older' || group.key === 'yesterday'");
    });
});
