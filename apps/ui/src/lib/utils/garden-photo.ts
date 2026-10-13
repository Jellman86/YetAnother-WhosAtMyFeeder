import type { GardenCapture } from '../api/garden';

type PhotoSize = readonly [number, number];

interface GardenPhotoOutline {
    kind: 'presence' | 'identification';
    box: readonly number[];
    size: PhotoSize;
}

export function gardenPhotoOutline(capture: GardenCapture, size: PhotoSize | undefined): GardenPhotoOutline | null {
    if (!size || !size.every(value => Number.isFinite(value) && value > 0)) return null;
    const motion = capture.source_kind === 'motion' ? capture.motion_source : null;
    const identification = capture.identification;
    const box = motion?.box_xywh ?? (
        identification?.review !== 'dismissed' && identification?.input_kind === 'tracked_crop'
        && identification.frame_size[0] === size[0] && identification.frame_size[1] === size[1]
            ? identification.box_xywh : null
    );
    if (!box || box.length !== 4 || !box.every(Number.isFinite)) return null;
    const [x, y, width, height] = box;
    if (x < 0 || y < 0 || width <= 0 || height <= 0 || x + width > 1 || y + height > 1) return null;
    return { kind: motion ? 'presence' : 'identification', box, size };
}
