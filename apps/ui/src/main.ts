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

      if (registration.waiting) {
        toastStore.info(getLabel('pwa.update_available', 'Update available. Refresh to apply.'), 6000);
      }

      registration.addEventListener('updatefound', () => {
        const newWorker = registration.installing;
        if (!newWorker) return;
        newWorker.addEventListener('statechange', () => {
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            toastStore.info(getLabel('pwa.update_available', 'Update available. Refresh to apply.'), 6000);
          }
        });
      });
    } catch {
      // Ignore service worker registration failures
    }
  });
}
