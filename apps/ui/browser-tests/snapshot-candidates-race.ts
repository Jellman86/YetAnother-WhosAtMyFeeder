import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import SnapshotCandidatesRaceFixture from './SnapshotCandidatesRaceFixture.svelte';

declare global {
    interface Window {
        snapshotRace?: {
            setCapture: (id: 'A' | 'B') => void;
            setOwner: (owner: boolean) => void;
            setSummary: (counted: number) => void;
        };
    }
}

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing snapshot race fixture mount');
mount(SnapshotCandidatesRaceFixture, { target });
