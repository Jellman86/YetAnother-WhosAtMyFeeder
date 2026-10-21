export interface MapMarker {
    lat: number;
    lng: number;
    title?: string;
    popupLines?: string[];
    isCenter?: boolean;
}

export function markerPopup(marker: MapMarker): HTMLElement | null {
    if (!marker.title && !marker.popupLines?.length) return null;
    const content = document.createElement('div');
    content.className = 'font-sans';
    if (marker.title) {
        const title = document.createElement('p');
        title.className = 'font-bold text-sm mb-1';
        title.textContent = marker.title;
        content.append(title);
    }
    for (const [index, line] of (marker.popupLines ?? []).entries()) {
        const row = document.createElement('p');
        row.className = index === 0 ? 'text-xs opacity-75' : 'text-xs font-bold mt-1';
        row.textContent = line;
        content.append(row);
    }
    return content;
}
