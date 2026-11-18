/**
 * A short signature of unsaved values, for telling whether they still stand. The values can hold a
 * typed secret, so only this hash is kept, never the text (FNV-1a, 32 bits: enough to tell values
 * apart within one visit, and not a secret's safe keeping, which nothing here needs).
 */
export function draftSignature(text: string): string {
    let hash = 0x811c9dc5;
    for (let index = 0; index < text.length; index += 1) {
        hash ^= text.charCodeAt(index);
        hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, '0');
}
