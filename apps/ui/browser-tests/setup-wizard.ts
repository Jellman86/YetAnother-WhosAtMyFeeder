import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import { authStore } from '../src/lib/stores/auth.svelte';
import '../src/app.css';
import SetupWizardFixture from './SetupWizardFixture.svelte';

await i18nReady;
// The fake backend's /api/auth/status decides whether this is a first run,
// exactly as it does for the app shell.
await authStore.loadStatus();
const target = document.getElementById('app');
if (!target) throw new Error('Missing setup wizard fixture mount');
mount(SetupWizardFixture, { target });
