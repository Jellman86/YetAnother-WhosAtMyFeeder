function fractionalDigits(value: number | undefined): number {
    if (value === undefined || !Number.isFinite(value) || value < 0.5 || value > 0.95) {
        return 0;
    }
    return String(value).split('.')[1]?.length ?? 0;
}

export function gardenThresholdStep(value: number | undefined, savedValue?: number): number {
    return 10 ** -Math.max(2, fractionalDigits(value), fractionalDigits(savedValue));
}
