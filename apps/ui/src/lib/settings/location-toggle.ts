export function locationTogglePresentation(locationAuto: boolean): {
    autoActive: boolean;
    manualActive: boolean;
    thumbTranslateClass: string;
} {
    return {
        autoActive: locationAuto,
        manualActive: !locationAuto,
        thumbTranslateClass: locationAuto ? 'translate-x-0' : 'translate-x-5'
    };
}
