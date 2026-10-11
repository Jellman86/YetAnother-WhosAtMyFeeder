import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import ModalTextLayoutFixture from './ModalTextLayoutFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing capture text layout fixture mount');
mount(ModalTextLayoutFixture, { target });
