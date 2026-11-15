import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import { installMediaFallback } from '../src/lib/app/media-fallback';

// As the app entry does, so failed pictures degrade here the way they do in the app.
installMediaFallback(document);
import ModalTextLayoutFixture from './ModalTextLayoutFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing capture text layout fixture mount');
mount(ModalTextLayoutFixture, { target });
