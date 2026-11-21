import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import { installMediaFallback } from '../src/lib/app/media-fallback';
import RecordLayoutFixture from './RecordLayoutFixture.svelte';

// As the app entry does, so failed pictures degrade here the way they do in the app.
installMediaFallback(document);
// `?theme=dark` draws the record as the dark theme does.
document.documentElement.classList.toggle('dark', new URLSearchParams(window.location.search).get('theme') === 'dark');

// `?font=classic` sets the reader's Classic font theme, as the theme store does on <html>.
if (new URLSearchParams(window.location.search).get('font') === 'classic') {
    document.documentElement.style.setProperty('--font-body', "'Source Serif 4', 'Georgia', serif");
    document.documentElement.style.setProperty('--font-display', "'Playfair Display', 'Source Serif 4', serif");
}

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing record layout fixture mount');
mount(RecordLayoutFixture, { target });
