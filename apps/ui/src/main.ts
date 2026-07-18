import './app.css'
import { i18nReady } from './lib/i18n'
import { mount } from 'svelte'
import App from './App.svelte'

// Safari/WebKit has a bug where its internal autofill scanner throws a null
// reference on any page with password-type inputs, surfaced as an unhandled
// promise rejection. Suppress it so it doesn't interfere with navigation.
window.addEventListener('unhandledrejection', (event) => {
    const msg = event.reason?.message ?? String(event.reason ?? '');
    if (msg.includes('autofillFieldData')) {
        event.preventDefault();
    }
});
import { APP_BASE_PATH } from './lib/app/url-base';

const appTarget = document.getElementById('app');
if (!appTarget) {
  throw new Error('YA-WAMF application target is missing');
}

try {
  await i18nReady;
  mount(App, { target: appTarget });
} catch (error: unknown) {
  console.error('[i18n] Application language could not be loaded.', error);
  appTarget.setAttribute('role', 'alert');
  appTarget.setAttribute('aria-live', 'assertive');
  const message = document.createElement('p');
  message.className = 'mx-auto mt-16 max-w-xl px-6 text-center text-slate-700 dark:text-slate-200';
  message.textContent = 'YA-WAMF could not load its interface language. Check the connection and refresh the page.';
  const retry = document.createElement('button');
  retry.type = 'button';
  retry.className = 'btn btn-primary mx-auto mt-5 flex';
  retry.textContent = 'Refresh page';
  retry.onclick = () => window.location.reload();
  appTarget.replaceChildren(message, retry);
}

if (import.meta.env.PROD && !APP_BASE_PATH && 'serviceWorker' in navigator) {
  window.addEventListener('load', async () => {
    try {
      const registration = await navigator.serviceWorker.register('/sw.js');

      let refreshing = false;
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (refreshing) return;
        refreshing = true;
        window.location.reload();
      });

      // If a new worker is already waiting, activate it now to avoid showing the
      // "Update available" toast on every refresh.
      if (registration.waiting) {
        registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      }

      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (!newWorker) return;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            // Auto-activate so we don't nag on every refresh.
            newWorker.postMessage({ type: 'SKIP_WAITING' });
          }
        });
      });
    } catch {
      // Ignore service worker registration failures
    }
  });
}
