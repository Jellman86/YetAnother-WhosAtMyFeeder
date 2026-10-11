import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import OwnerHistoryFixture from './OwnerHistoryFixture.svelte';

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing owner history fixture mount');
mount(OwnerHistoryFixture, { target });
