import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import AboutPortraitFixture from './AboutPortraitFixture.svelte';

declare global {
    interface Window {
        aboutPortrait?: { invalidate: () => void; setMounted: (value: boolean) => void };
    }
}

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing About portrait fixture mount');
mount(AboutPortraitFixture, { target });
