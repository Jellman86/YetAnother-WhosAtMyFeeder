import './app.css'
import './lib/i18n'
import { mount } from 'svelte'
import App from './App.svelte'
import { waitLocale } from 'svelte-i18n'

// Ensure app mounts even if i18n has hiccups
waitLocale()
    .then(() => {
        mount(App, { target: document.getElementById('app')! })
    })
    .catch((err) => {
        console.error('Failed to load locale, mounting anyway:', err);
        mount(App, { target: document.getElementById('app')! })
    });
