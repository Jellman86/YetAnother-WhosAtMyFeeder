import { describe, expect, it } from 'vitest';
import modelManagerSource from './ModelManager.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';
import { authoredLocale } from '../../i18n/authored-locales';
import panelSource from './FinderDevicePanel.svelte?raw';
import modelSettingsSource from '../../components/settings/ModelSettings.svelte?raw';
import modelStepSource from '../../components/setup/ModelStep.svelte?raw';

const en = { settings: enSettings };

describe('bird finder choice', () => {
    it('offers both accurate detectors as one labelled radio group on the default surface', () => {
        expect(modelManagerSource).toContain('<fieldset');
        expect(modelManagerSource).toContain('name="bird-finder"');
        expect(modelManagerSource).toContain('BIRD_FINDER_MODEL_IDS');
        // The finder is a model choice, not a thumbnail detail behind a disclosure.
        expect(modelManagerSource).not.toContain('model_manager_thumbnail_crop_title');
        const finder = modelManagerSource.indexOf('name="bird-finder"');
        const technicalDetails = modelManagerSource.lastIndexOf('model_manager_technical_details');
        const devicePanel = modelManagerSource.indexOf('<FinderDevicePanel');
        expect(finder).toBeGreaterThan(technicalDetails);
        expect(finder).toBeLessThan(devicePanel);
    });

    it('stages the choice in the settings form instead of saving it on click', () => {
        expect(modelManagerSource).toContain('birdFinder = $bindable');
        expect(modelManagerSource).not.toContain('updateSettings');
        expect(modelManagerSource).not.toContain('bird_finder_save_failed');
        expect(modelManagerSource).toContain('cropDetectorStatus.chosen_model_id');
    });

    it("states each finder's costs on its option, and no device sentence", () => {
        expect(modelManagerSource).toContain('ramShortLabel(option.model.estimated_ram_mb)');
        expect(modelManagerSource).toContain('option.model.file_size_mb');
        expect(en.settings.detection.bird_finder_default_badge).toBe('Default');
        // The device caveat used to be repeated, in bold, on every option. It is one row now.
        const options = modelManagerSource.slice(modelManagerSource.indexOf('{#each birdFinderOptions as option'), modelManagerSource.indexOf('<FinderDevicePanel'));
        expect(options).not.toMatch(/bird_finder_(recommended|runs|device)/);
        expect(options).not.toContain('font-bold');
        for (const key of Object.keys(en.settings.detection)) expect(key).not.toMatch(/^bird_finder_recommended_/);
    });

    it('states where the finder runs once, from the last device check, and never guesses a cause', () => {
        expect(modelManagerSource.match(/<FinderDevicePanel/g)).toHaveLength(1);
        expect(modelManagerSource).toContain('check={cropDetectorStatus?.device_check}');
        expect(panelSource).toContain('finderRunsOn(');
        expect(panelSource.match(/bird_finder_runs_on'/g)).toHaveLength(1);
        expect(en.settings.detection.bird_finder_runs_failed_dated).toBe('CPU · {devices} failed the device check on {date}');
        expect(en.settings.detection.bird_finder_runs_cause_mismatch).toMatch(/did not match the CPU/);
        expect(en.settings.detection.bird_finder_runs_never).toBe('CPU · no accelerator has passed a check on this host yet');
        // The fallback is said in words; the attention colour only agrees with them (rule unit-tested in bird-finder.test.ts).
        expect(panelSource).toContain('finderNeedsAttention(runsOn, accelerators, savedProvider)');
        // Values and help are normal weight: bold is for labels alone.
        expect(panelSource).not.toMatch(/font-(bold|semibold)/);
    });

    it('never says "in this image, on this host, or for the active model" again, in any language', () => {
        const guess = /in this image, on this host, or for the active model/;
        for (const source of [modelManagerSource, panelSource, modelSettingsSource, modelStepSource]) expect(source).not.toMatch(guess);
        for (const language of ['en', 'de', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh']) {
            const detection = (authoredLocale(language).settings as { detection: Record<string, unknown> }).detection;
            expect(String(detection.provider_saved_unavailable)).toContain('{provider}');
            expect(String(detection.bird_finder_device_unpassed_saved).match(/\{provider\}/g)?.length).toBeGreaterThanOrEqual(1);
        }
        expect(en.settings.detection.provider_saved_unavailable).not.toMatch(/image/);
        expect(en.settings.detection.bird_finder_device_unpassed_saved)
            .toBe('Saved: {provider}. It runs on CPU until {provider} passes a check. Check devices, or choose Automatic.');
    });

    it('names a device without a passing check, and keeps only the saved one selectable', () => {
        expect(panelSource).toContain('finderDeviceOptions(');
        // The server keeps an unchanged saved device and refuses a newly chosen unpassed one.
        expect(panelSource).toContain('disabled: !option.selectable');
        expect(panelSource).toContain('finderSaved ? savedProvider : null');
        expect(modelManagerSource).toContain('finderSaved={savedBirdFinder === null || savedBirdFinder === birdFinder}');
        expect(en.settings.detection.bird_finder_device_not_passed).toBe('{provider} · not passed on this host');
        expect(en.settings.detection.bird_finder_device_auto).toBe('Automatic (fastest device that passed)');
        expect(en.settings.detection.bird_finder_device_unpassed_chosen).toMatch(/cannot be saved yet/);
    });

    it('offers one check button with its hint directly under it, scoped to the chosen finder', () => {
        expect(modelManagerSource).toContain('oncheckfinderdevices');
        // Named for what it checks, so it is never taken for the Hardware check of every model.
        expect(en.settings.detection.bird_finder_check_devices).toBe('Check devices for the bird finder');
        expect(en.settings.detection.compat_run).toBe('Check devices for every installed model');
        expect(en.settings.detection.bird_finder_check_devices_hint).toMatch(/identification model is not changed/);
        const button = panelSource.indexOf("bird_finder_check_devices'");
        const hint = panelSource.indexOf('id="bird-finder-check-hint"');
        const repair = panelSource.indexOf('data-finder-repair');
        expect(button).toBeGreaterThan(-1);
        expect(hint).toBeGreaterThan(button);
        expect(repair).toBeGreaterThan(hint);
    });

    it('puts re-download behind Repair and the background behind "How the finder works"', () => {
        const repair = panelSource.slice(panelSource.indexOf('<details class="group" data-finder-repair'));
        expect(repair).toContain('bird_finder_redownload');
        expect(repair).toContain('btn btn-ghost');
        const how = panelSource.slice(panelSource.indexOf('data-finder-how'));
        expect(how).toContain('bird_finder_backup');
        expect(how).toContain('bird_finder_how_save');
        expect(en.settings.detection.bird_finder_how_title).toBe('How the finder works');
    });

    it('shows the last completed run only when there is one', () => {
        expect(panelSource).toContain('{#if lastRun}');
        expect(panelSource).toContain('<ModelExecutionEvidence');
    });

    it('says plainly when the chosen finder is not in use yet, and when a change waits for Apply', () => {
        expect(modelManagerSource).toContain("cropDetectorStatus?.reason === 'fallback_default_accurate'");
        expect(en.settings.detection.bird_finder_fallback).toMatch(/not downloaded yet/);
        expect(modelManagerSource).toContain('birdFinder !== savedBirdFinder');
        expect(en.settings.detection.bird_finder_pending).toMatch(/Save changes/);
    });

    it('states the cost of the wide-frame finder once, rounded, without em dashes', () => {
        // The download size is in the option's own facts line, from the catalogue, rounded to whole
        // megabytes; the description no longer repeats a second, differently rounded figure.
        expect(en.settings.detection.bird_finder_wide_desc).not.toMatch(/\d+(\.\d+)? MB/);
        expect(modelManagerSource).toContain('{ size: Math.round(option.model.file_size_mb) }');
        for (const key of Object.keys(en.settings.detection).filter((k) => k.startsWith('bird_finder'))) {
            expect(String((en.settings.detection as Record<string, string>)[key])).not.toContain('—');
        }
    });
});
