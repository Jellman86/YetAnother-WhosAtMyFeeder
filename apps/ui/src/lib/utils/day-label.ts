import { formatDate } from './datetime';

type Translate = (key: string, options: { default: string }) => string;

/** Today and Yesterday by name; anything older by date. The Explorer rows and cards share it. */
export function relativeDayLabel(value: string, translate: Translate, now: Date = new Date()): string {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === now.toDateString()) return translate('common.today', { default: 'Today' });
    if (date.toDateString() === yesterday.toDateString()) return translate('common.yesterday', { default: 'Yesterday' });
    return formatDate(date);
}
