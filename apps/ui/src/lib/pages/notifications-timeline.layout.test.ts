import { describe, expect, it } from 'vitest';
import source from './Notifications.svelte?raw';
import appSource from '../../App.svelte?raw';
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
        expect(en.notifications.clear_notifications).toBe('Clear notifications');
    });

    it('hides owner-only filters rather than showing them empty', () => {
        expect(source).toContain('isOwner || !isOwnerOnlyFilter(name)');
        // Leaving an owner filter selected as access drops must not strand a guest on it.
        expect(source).toContain("!isOwner && isOwnerOnlyFilter(filter) ? 'all' : filter");
    });

    it('gates the operational timeline at the route and data-source boundaries', () => {
        expect(appSource).toContain('const isOwnerOnly = isNotificationRoute(currentRoute)');
        expect(source).toContain('serverJobsStore.mergeActive(jobProgressStore.activeJobs)');
        expect(source).toContain('buildTimelineItems(');
        expect(source).toContain('untrack(() => serverJobsStore.retain())');
    });

    it('keeps every timeline control at the repository touch-target minimum', () => {
        const buttonTags = source.match(/<button\b[\s\S]*?>/g) ?? [];
        expect(buttonTags.length).toBeGreaterThan(0);
        for (const button of buttonTags) expect(button).toContain('min-h-11');
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

    it('centres the rail and its markers in one column instead of offsetting by hand', () => {
        // The dot was pushed out with an arbitrary negative offset measured against the list's
        // border, which left its centre 1.5px off the line and hanging outside the box.
        expect(source).not.toContain('-left-[27px]');
        expect(source).not.toContain('border-l border-slate-200');
        expect(source).toContain('grid-cols-[0.75rem_minmax(0,1fr)]');
        expect(source).toContain('absolute left-1/2 w-px -translate-x-1/2');
    });

    it('keeps the rail unbroken between rows and capped at the outer dots', () => {
        // Vertical padding lives on the content column, not the row: as a grid item the rail's
        // box stopped at the row's padding and the line broke between every entry.
        expect(source).toContain('flex items-start gap-3 py-3');
        expect(source).toContain("? 'top-7 bottom-0'");
        expect(source).toContain("? 'top-0 h-7'");
        expect(source).toContain('{#if group.items.length > 1}');
    });

    it('shows the capture as evidence and an icon for every other kind', () => {
        // The field log leads with the photograph; a detection notification should not be an
        // abstract badge when the evidence exists.
        expect(source).toContain('getThumbnailUrl(capture)');
        // Fixed box and placeholder underneath, so a missing image cannot shift the row.
        expect(source).toContain('h-8 w-8 object-cover');
        for (const kind of ['warn', 'check', 'clock', 'update', 'bird']) {
            expect(source).toContain(`kind === '${kind}'`);
        }
    });

    it('does not repeat the date on rows the group heading already dates', () => {
        expect(source).toContain("group.key === 'older' || group.key === 'yesterday'");
    });
});
