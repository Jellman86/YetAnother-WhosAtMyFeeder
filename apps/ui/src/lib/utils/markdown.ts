import MarkdownIt from 'markdown-it';

const markdown = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true,
    typographer: true,
});

const isHeadingLike = (value: string) => {
    if (value.length < 3 || value.length > 40) return false;
    const cleaned = value.replace(/[:.]+$/, '').trim();
    if (!/[A-Z]/.test(cleaned)) return false;
    return /^[A-Z0-9][A-Za-z0-9\s/&()\-]+$/.test(cleaned);
};

const normalizeMarkdown = (input: string) => {
    const lines = input.split(/\r?\n/);
    const out: string[] = [];
    let inCode = false;

    for (const rawLine of lines) {
        const line = rawLine.trimEnd();
        const trimmed = line.trim();

        if (trimmed.startsWith('```')) {
            inCode = !inCode;
            out.push(line);
            continue;
        }

        if (inCode) {
            out.push(line);
            continue;
        }

        if (!trimmed) {
            out.push('');
            continue;
        }

        if (trimmed.startsWith('#')) {
            out.push(trimmed);
            continue;
        }

        if (trimmed.endsWith(':') || isHeadingLike(trimmed)) {
            const heading = trimmed.replace(/[:.]+$/, '').trim();
            out.push(`## ${heading}`);
            continue;
        }

        out.push(trimmed);
    }

    return out.join('\n');
};

export function renderMarkdown(text: string): string {
    if (!text) return '';
    return markdown.render(normalizeMarkdown(text));
}
