import { describe, expect, it } from 'vitest';
import source from './Notifications.svelte?raw';
import appSource from '../../App.svelte?raw';
import enNotifications from '../i18n/locales/en/notifications.json';

const en = { notifications: enNotifications };

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

    it('paginates the filtered river instead of rendering the full retained history', () => {
        expect(source).toContain("import Pagination from '../components/Pagination.svelte'");
        expect(source).toContain('paginateItems(filteredItems, requestedPage, pageSize)');
        expect(source).toContain('groupNotifications(timelinePage.items)');
        expect(source).toContain('data-notifications-pagination');
        expect(source).toContain('onPageChange={changePage}');
        expect(source).toContain('onPageSizeChange={changePageSize}');
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
        // The jobs come with the pushed status; nothing is claimed before the first one.
        expect(source).toContain('isOwner && serverJobsStore.snapshot === null');
    });

    it('keeps every timeline control at the repository touch-target minimum', () => {
        const buttonTags = source.match(/<button\b[\s\S]*?>/g) ?? [];
        expect(buttonTags.length).toBeGreaterThan(0);
        for (const button of buttonTags) expect(button).toContain('min-h-11');
    });

    it('keeps amber for what needs a person', () => {
        // The progress bar used to run a three colour gradient through the attention colour.
        expect(source).not.toContain('from-accent-500');
        expect(source).toContain("running: 'bg-accent border-accent'");
        // layout-patterns §1.3: "Amber is reserved for 'this needs a person'": the attention status
        // token is amber in every theme, while the accent follows the theme's brand colour.
        expect(source).toContain("attention: 'bg-status-attention border-status-attention'");
        // Anything meaning confirmed uses the ok status token, so it stays green in every theme.
        expect(source).toContain("done: 'bg-status-ok border-status-ok'");
        expect(source).not.toMatch(/\baccent-\d|emerald-/);
    });

    it('makes opening a notification a real control', () => {
        // Was a <p> that looked like an action and could not be focused or clicked.
        expect(source).toContain('onclick={() => openItem(item)}');
        // The whole row is the link, with a chevron: a boxed Open on every row doubled the list.
        expect(source).toContain('data-notification-row="link"');
        expect(source).toContain('data-notification-chevron');
        expect(source).not.toMatch(/btn btn-secondary focus-ring[^\n]*\n[^\n]*openItem/);
    });

    it('states what the empty page will hold instead of that it is empty', () => {
        expect(source).toContain('notifications.empty_title');
        expect(source).toContain('notifications.empty_action');
        expect(en.notifications.empty_body).toContain('Newest first');
        // The page owns background work now, so the empty state has to say so.
        expect(en.notifications.empty_body).toContain('background work');
        // The shared state primitive, so an empty page reads as every other empty page does.
        expect(source).toContain("import StateBlock from '../components/ui/StateBlock.svelte';");
        expect(source).toMatch(/<StateBlock\s+state="empty"\s+title=\{\$_\('notifications\.empty_title'/);
        expect(source).toContain('state="empty" variant="inline" cause={$_(\'notifications.empty_filtered\'');
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
        expect(source).toContain('class="min-w-0 py-1"');
        // Dismiss sits under the words, never beside the chevron, so the time and chevron column holds.
        expect(source.indexOf('data-notification-dismiss')).toBeGreaterThan(source.indexOf('data-notification-row="plain"'));
        expect(source).toContain('ml-11 min-h-11 px-2 text-xs');
        expect(source).toContain("? 'top-7 bottom-0'");
        expect(source).toContain("? 'top-0 h-7'");
        expect(source).toContain('{#if group.items.length > 1}');
    });

    it('shows the capture as evidence and an icon for every other kind', () => {
        // The field log leads with the photograph; a detection notification should not be an
        // abstract badge when the evidence exists.
        expect(source).toMatch(/getThumbnailUrl\(capture[,)]/);
        // Fixed box and placeholder underneath, so a missing image cannot shift the row.
        expect(source).toContain('h-8 w-8 object-cover');
        for (const kind of ['warn', 'check', 'clock', 'update', 'bird']) {
            expect(source).toContain(`kind === '${kind}'`);
        }
    });

    it('does not repeat the date on rows the group heading already dates', () => {
        expect(source).toContain("groupKey === 'older' || groupKey === 'yesterday'");
    });
});

describe('a job that stopped reporting', () => {
    it('says so in words, stops the bar, and can be dismissed on its own', () => {
        expect(source).toContain('isStoppedJob(item)');
        expect(source).toContain("$_('notifications.job_stopped'");
        expect(source).toContain("$_('notifications.job_stopped_label')");
        // A stopped job's bar is grey and static, never the brand colour that means work in flight.
        expect(source).toContain("isStoppedJob(item) ? 'bg-status-neutral'");
        expect(source).toContain('notificationCenter.remove(item.id)');
        expect(en.notifications.job_stopped).toContain('Nothing is still running');
        expect(en.notifications.job_stopped).toContain('{time}');
        expect(en.notifications.global_progress_stale).not.toContain('stale');
    });
});
