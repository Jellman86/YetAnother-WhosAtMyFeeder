import type { Settings } from '../api/settings';
import type { ColorTheme, FontTheme } from '../stores/theme.svelte';
import { normalizeDateFormat, normalizeTimeFormat } from '../utils/datetime';
import type { SettingsSectionAdapter } from './section-adapter';

export type ExplorerView = 'cards' | 'list';

/** The Appearance choices that are saved for the whole installation. */
export interface AppearanceDraft {
    displayCommonNames: boolean;
    scientificNamePrimary: boolean;
    explorerView: ExplorerView;
    dateFormat: ReturnType<typeof normalizeDateFormat>;
    timeFormat: ReturnType<typeof normalizeTimeFormat>;
    fontTheme: FontTheme;
    colorTheme: ColorTheme;
}

interface AppearancePatch {
    display_common_names: boolean;
    scientific_name_primary: boolean;
    appearance_explorer_view: ExplorerView;
    date_format: AppearanceDraft['dateFormat'];
    time_format: AppearanceDraft['timeFormat'];
    appearance_font_theme: FontTheme;
    appearance_color_theme: ColorTheme;
}

function normalizeFontTheme(value: unknown): FontTheme {
    return value === 'default' || value === 'clean' || value === 'studio' || value === 'classic' || value === 'compact'
        ? value
        : 'classic';
}

function normalizeColorTheme(value: unknown): ColorTheme {
    return value === 'default' || value === 'bluetit' ? value : 'bluetit';
}

function normalizeExplorerView(value: unknown): ExplorerView {
    return value === 'list' ? 'list' : 'cards';
}

export const appearanceSection: SettingsSectionAdapter<AppearanceDraft, AppearancePatch> = {
    decode(saved: Settings): AppearanceDraft {
        return {
            displayCommonNames: saved.display_common_names ?? true,
            scientificNamePrimary: saved.scientific_name_primary ?? false,
            explorerView: normalizeExplorerView(saved.appearance_explorer_view),
            dateFormat: normalizeDateFormat(saved.date_format),
            timeFormat: normalizeTimeFormat(saved.time_format),
            fontTheme: normalizeFontTheme(saved.appearance_font_theme),
            colorTheme: normalizeColorTheme(saved.appearance_color_theme)
        };
    },
    encodePatch(draft: AppearanceDraft): AppearancePatch {
        return {
            display_common_names: draft.displayCommonNames,
            scientific_name_primary: draft.scientificNamePrimary,
            appearance_explorer_view: draft.explorerView,
            date_format: draft.dateFormat,
            time_format: draft.timeFormat,
            appearance_font_theme: draft.fontTheme,
            appearance_color_theme: draft.colorTheme
        };
    }
};
