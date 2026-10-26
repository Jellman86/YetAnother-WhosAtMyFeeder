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


/** Percentage geometry for an undistorted preview centred on the saved animal box. */
export function gardenPreviewStyle(
    capture: GardenCapture,
    size: PhotoSize | undefined,
    aspect: number,
): { width: number; height: number; left: number; top: number } | null {
    const outline = gardenPhotoOutline(capture, size);
    if (!outline || !Number.isFinite(aspect) || aspect <= 0) return null;
    const [imageWidth, imageHeight] = outline.size;
    const [x, y, w, h] = outline.box;
    // A little context keeps paws, tails and the detector's imperfect edges visible.
    const fit = Math.min(aspect / imageWidth, 1 / imageHeight);
    const scale = Math.max(fit, Math.min(aspect / (w * imageWidth * 1.24), 1 / (h * imageHeight * 1.24)));
    const width = imageWidth * scale / aspect * 100;
    const height = imageHeight * scale * 100;
    const offset = (extent: number, centre: number): number => extent < 100
        ? (100 - extent) / 2
        : Math.max(100 - extent, Math.min(0, 50 - centre * extent));
    return { width, height, left: offset(width, x + w / 2), top: offset(height, y + h / 2) };
}
