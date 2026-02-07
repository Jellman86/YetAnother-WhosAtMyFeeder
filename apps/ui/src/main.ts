import './app.css'
import './lib/i18n'
import { mount } from 'svelte'
import App from './App.svelte'

mount(App, { target: document.getElementById('app')! });

if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {
      // Ignore service worker registration failures
    });
  });
}
