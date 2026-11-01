import { describe, expect, it } from 'vitest';
import appSource from '../../App.svelte?raw';
import pageHeaderSource from './PageHeader.svelte?raw';
import notificationCenterSource from './NotificationCenter.svelte?raw';
import notificationsSource from '../pages/Notifications.svelte?raw';
import mobileTopBarSource from './MobileTopBar.svelte?raw';
import loginSource from './Login.svelte?raw';
import toastSource from './Toast.svelte?raw';
import pipelineSource from './InstancePipeline.svelte?raw';
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
        expect(notificationCenterSource).toContain('bg-rose-700');
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
        expect(loginSource).toContain("aria-invalid={error ? 'true' : undefined}");
        expect(loginSource).toContain("aria-describedby={error ? 'login-error' : undefined}");
        expect(loginSource).toContain('passwordInput?.focus();');
        expect(loginSource).toContain("$_('auth.login_failed'");
        expect(loginSource).not.toContain("'Login failed'");
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
