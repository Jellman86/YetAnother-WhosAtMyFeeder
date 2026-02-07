import './app.css'
import './lib/i18n'
import { mount } from 'svelte'
import App from './App.svelte'
import { toastStore } from './lib/stores/toast.svelte';
import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';

mount(App, { target: document.getElementById('app')! });

function getLabel(key: string, fallback: string) {
  try {
    return get(_)(key, { default: fallback });
  } catch {
    return fallback;
  }
}

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
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
