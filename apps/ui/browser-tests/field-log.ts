import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import FieldLogFixture from './FieldLogFixture.svelte';
await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing field log fixture mount');
mount(FieldLogFixture, { target });
