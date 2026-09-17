import type { ClassifierStatus } from '../api/classifier';

export function providerNeedsAttention(status: ClassifierStatus | null): boolean {
    if (!status?.enabled) return false;
    if (status.fallback_reason) return true;
    const selected = status.selected_provider;
    const active = status.active_provider === 'tflite' ? 'cpu' : status.active_provider;
    return Boolean(selected && selected !== 'auto' && active && active !== selected);
}
