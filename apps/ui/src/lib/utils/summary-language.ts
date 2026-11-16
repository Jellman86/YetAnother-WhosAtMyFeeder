import { languageLabel } from '../taxonomy/taxon-facts';

/**
 * The language a reference description is in, when it is not the one the page is being read in.
 *
 * A species with no article in the reader's language is described by the article its taxon links
 * to, which is usually English. The page then says so beside the text, and marks the text with its
 * language so a screen reader reads it in the right voice. Null when the description is in the
 * reader's language, or does not say which language it is in.
 */
export function summaryInAnotherLanguage(
    info: { extract?: string | null; summary_language?: string | null } | null | undefined,
    reading: string | null | undefined
): { code: string; name: string } | null {
    const code = info?.extract ? info.summary_language?.trim().toLowerCase() : null;
    if (!code) return null;
    // With no language of the reader's to compare, English is what the page falls back to.
    const locale = reading?.trim() || 'en';
    if (locale.toLowerCase().split('-')[0] === code.split('-')[0]) return null;
    return { code, name: languageLabel(code, locale) };
}
