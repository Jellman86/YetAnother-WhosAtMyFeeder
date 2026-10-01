import { mount } from 'svelte';
import { i18nReady } from '../src/lib/i18n';
import '../src/app.css';
import ReviewMediaFixture from './ReviewMediaFixture.svelte';

declare global {
    interface Window {
        reviewMedia?: {
            setRecord: (id: string) => void;
        };
    }
}

await i18nReady;
const target = document.getElementById('app');
if (!target) throw new Error('Missing review media fixture mount');
mount(ReviewMediaFixture, { target });
