import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import pageHeaderSource from './AppPageHeader.svelte?raw';
import sharedPageHeaderSource from './ui/PageHeader.svelte?raw';
import notificationCenterSource from './NotificationCenter.svelte?raw';
import notificationsSource from '../pages/Notifications.svelte?raw';
import mobileTopBarSource from './MobileTopBar.svelte?raw';
import loginSource from './Login.svelte?raw';
import toastSource from './Toast.svelte?raw';
import pipelineSource from './InstancePipeline.svelte?raw';
import backendStatusSource from './BackendStatusScreen.svelte?raw';
import enAuth from '../i18n/locales/en/auth.json';
import enNotFound from '../i18n/locales/en/not_found.json';
import enNotifications from '../i18n/locales/en/notifications.json';

const en = { auth: enAuth, not_found: enNotFound, notifications: enNotifications };

describe('the app shell', () => {
    it('titles pages with their navigation labels and names the browser tab', () => {
        expect(appSource).toContain("case 'explorer': return $_('nav.explorer'");
        expect(appSource).toContain("case 'leaderboard': return $_('nav.leaderboard'");
        expect(appSource).not.toContain("$_('nav.events'");
        expect(appSource).not.toContain("$_('nav.species'");
        expect(appSource).toContain('document.title = documentTitle(');
    });

    it('leaves the Dashboard h1 to its day bar and gives guests a named page', () => {
        expect(appSource).toContain("routeId === 'dashboard' ? undefined : pageTitle");
        expect(appSource).toContain('showOwnerActions={!authStore.isGuest}');
        expect(pageHeaderSource).toContain('{#if title}');
        expect(pageHeaderSource).toContain('{:else if showOwnerActions}');
    });

    it('answers an unknown address with a way back instead of an empty page', () => {
        expect(appSource).toContain('data-not-found');
        expect(appSource).toContain("$_('not_found.body'");
        expect(appSource).toContain('class="btn btn-primary min-h-11 px-4 py-2" onclick={() => navigate(\'/\')}');
        expect(en.not_found.title).toBe('This page does not exist');
        expect(en.not_found.action).toBe('Open the dashboard');
    });

    it('uses runes for the phone top bar and tells assistive tech whether the menu is open', () => {
        expect(mobileTopBarSource).not.toContain('export let');
        expect(mobileTopBarSource).toContain('$props()');
        expect(mobileTopBarSource).toContain('aria-expanded={menuOpen}');
        expect(mobileTopBarSource).toContain('aria-controls={menuControls}');
    });
});

describe('notification state for assistive tech', () => {
    it('puts the unread count in the bell name and marks it current on its page', () => {
        expect(notificationCenterSource).toContain("$_('notifications.bell_unread'");
        expect(notificationCenterSource).toContain("aria-current={current ? 'page' : undefined}");
        expect(pageHeaderSource).toContain('current={notificationsCurrent}');
        expect(appSource).toContain("notificationsCurrent={routeId === 'notifications'}");
    });

    it('draws the badge at AA contrast on the spacing scale', () => {
        expect(notificationCenterSource).toContain('min-w-5 h-5');
        expect(notificationCenterSource).toContain('bg-danger text-danger-fg');
        expect(notificationCenterSource).not.toContain('min-w-[18px]');
        expect(notificationCenterSource).not.toContain('bg-rose-500');
    });

    it('says unread in words and names the filter group for what it does', () => {
        expect(notificationsSource).toContain(`<span class="sr-only">{$_('notifications.count_unread'`);
        expect(notificationsSource).toContain("aria-label={$_('notifications.filter_group'");
        expect(en.notifications.filter_group).toBe('Filter notifications');
    });
});

describe('toasts', () => {
    it('announces errors at once in an alert region and everything else politely', () => {
        expect(toastSource).toContain('role="alert" data-toast-region="errors"');
        expect(toastSource).toContain('aria-live="polite" aria-relevant="additions" data-toast-region="status"');
    });

    it('holds the countdown while a toast is pointed at or focused', () => {
        expect(toastSource).toContain('onmouseenter={() => toastStore.pause(toast.id)}');
        expect(toastSource).toContain('onfocusin={() => toastStore.pause(toast.id)}');
        expect(toastSource).toContain('toastStore.resume(toast.id)');
    });
});

describe('the sign-in screen', () => {
    it('is the page heading and keeps the decorative logo silent', () => {
        expect(loginSource).toContain('<h1');
        expect(loginSource).toContain('alt=""');
        expect(loginSource).not.toContain('alt="Logo"');
    });

    it('announces a failure and ties it to the fields', () => {
        expect(loginSource).toContain('id="login-error" role="alert"');
        expect(loginSource).toContain("aria-invalid={passwordMissing || credentialsRefused ? 'true' : undefined}");
        expect(loginSource).toContain("return credentialsRefused ? 'login-error' : undefined;");
        expect(loginSource).toContain('passwordInput?.focus();');
        // The message is worded here from why the sign-in failed, never passed through from the server.
        expect(loginSource).toContain('failure = signInFailure(err);');
        expect(loginSource).not.toContain('err.message');
        expect(loginSource).not.toContain("'Login failed'");
    });

    it('checks its own fields and says what is missing beside each, without the browser bubble', () => {
        expect(loginSource).toContain('novalidate>');
        expect(loginSource).not.toMatch(/\n\s+required\n/);
        expect(loginSource.match(/aria-required="true"/g) ?? []).toHaveLength(2);
        // Messages are rendered before focus moves, and one live region speaks when it cannot.
        expect(loginSource.indexOf('await tick();')).toBeLessThan(loginSource.indexOf('field.focus();'));
        expect(loginSource.match(/role="status"/g) ?? []).toHaveLength(1);
        expect(loginSource).toContain("$_('auth.username_required'");
        expect(loginSource).toContain("$_('auth.password_required'");
    });

    it('is built from the shared kit, flat, with no retired glass styling', () => {
        expect(loginSource).toContain('class="card-base');
        expect(loginSource.match(/class="input-base/g) ?? []).toHaveLength(2);
        expect(loginSource).toContain('class="btn btn-primary');
        expect(loginSource).toContain('class="btn btn-secondary');
        expect(loginSource).toMatch(/<label for="username" class="[^"]*text-sm/);
        for (const retired of ['backdrop-blur', 'shadow-2xl', 'animate-in', 'slide-in-from', 'handleGuest', 'uppercase tracking-widest']) {
            expect(loginSource).not.toContain(retired);
        }
    });

    it('speaks plainly in sentence case', () => {
        expect(loginSource).toContain("$_('auth.signin_heading'");
        expect(loginSource).not.toContain('auth.welcome_back');
        expect(loginSource).not.toContain('auth.secure_access');
        expect(en.auth.signin_heading).toBe('Sign in');
        expect(en.auth.signin_desc).toBe('Sign in to manage your feeder.');
        expect(en.auth.signin_button).toBe('Sign in');
        expect(en.auth.continue_guest).toBe('Continue without signing in');
    });
});

describe('the About pipeline', () => {
    it('reads the classifier through the helper that never guesses not loaded', () => {
        expect(pipelineSource).toContain('pipelineClassifierState(classifier)');
        expect(pipelineSource).not.toContain('classifier.loaded');
        expect(pipelineSource).not.toContain("about.pipeline.not_loaded");
    });
});

describe('unmeasured reassurance', () => {
    const authLocales = import.meta.glob('../i18n/locales/*/auth.json', { eager: true, import: 'default' }) as Record<string, Record<string, string>>;

    it('does not say the feeder data is safe while the service cannot be reached to ask', () => {
        // Nobody read the database when the backend is down or stopped during startup.
        expect(backendStatusSource).not.toMatch(/data is safe/i);
        expect(en.auth.status_unavailable_desc).toBe('The service may still be starting after an update or model change.');
        expect(en.auth.startup_failed_desc).toBe('Startup stopped during a required check. Check the container logs for the cause.');
        // Each translation is one or two sentences long, as the English is: the safety sentence is gone.
        expect(Object.keys(authLocales)).toHaveLength(9);
        for (const [path, locale] of Object.entries(authLocales)) {
            expect(locale.status_unavailable_desc.split(/[.。]/).filter((part) => part.trim()), path).toHaveLength(1);
            expect(locale.startup_failed_desc.split(/[.。;；]/).filter((part) => part.trim()), path).toHaveLength(2);
        }
    });

    it('keeps "Live" for camera events: the browser step of About says only that it is connected', () => {
        const browserStep = pipelineSource.slice(pipelineSource.indexOf("key: 'browser'"), pipelineSource.indexOf('function toneClass'));
        expect(browserStep).toContain("$_('status.state_connected'");
        expect(browserStep).not.toContain('state_live');
    });
});

describe('the page header', () => {
    it('never squeezes the title to nothing: the actions wrap below it when they do not fit beside it', () => {
        expect(pageHeaderSource).toContain('<PageHeader {title} {subtitle} actions={controls} />');
        expect(sharedPageHeaderSource).toContain('flex flex-wrap items-start justify-between');
        expect(sharedPageHeaderSource).toContain('page-title-block min-w-0 flex-1 basis-32');
        expect(sharedPageHeaderSource).toContain('basis-full order-last');
        expect(sharedPageHeaderSource).not.toContain('page-header-grid');
    });
});
