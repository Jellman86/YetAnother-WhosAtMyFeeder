import MarkdownIt from 'markdown-it';

const markdown = new MarkdownIt({
    html: false,
    linkify: true,
    breaks: true,
    typographer: true,
});

export function renderMarkdown(text: string): string {
    if (!text) return '';
    return markdown.render(text);
}
