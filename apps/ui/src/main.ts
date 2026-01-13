import './app.css'
import './lib/i18n'
import { mount } from 'svelte'
import App from './App.svelte'
import { waitLocale } from 'svelte-i18n'

waitLocale().then(() => {
    mount(App, {
        target: document.getElementById('app')!,
    })
})
