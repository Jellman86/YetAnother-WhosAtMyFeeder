/**
 * Whether a photograph fills its box or is shown whole.
 *
 * Covering the box suits a scene or a near-square crop. A tall crop, a woodpecker on a pole, is
 * cut down to a band through its middle when it covers a wide card, which shows feathers instead
 * of a bird (#481). Past this share of the photo lost, it is shown whole over a soft fill instead.
 */
export type PhotoFit = 'cover' | 'contain';

const MAX_COVER_LOSS = 0.25;

export function photoFit(imageWidth: number, imageHeight: number, boxWidth: number, boxHeight: number): PhotoFit {
    const sizes = [imageWidth, imageHeight, boxWidth, boxHeight];
    if (sizes.some((size) => !Number.isFinite(size) || size <= 0)) return 'cover';
    const imageAspect = imageWidth / imageHeight;
    const boxAspect = boxWidth / boxHeight;
    const loss = imageAspect > boxAspect ? 1 - boxAspect / imageAspect : 1 - imageAspect / boxAspect;
    // A scene or a square loses exactly a quarter of a 4:3 box; the margin absorbs the box's pixel
    // rounding so those common shapes stay on cover.
    return loss > MAX_COVER_LOSS + 0.02 ? 'contain' : 'cover';
}

/** The fit for a loaded image element, from its own natural size and the box it is drawn in. */
export function photoFitFor(image: HTMLImageElement): PhotoFit {
    return photoFit(image.naturalWidth, image.naturalHeight, image.clientWidth, image.clientHeight);
}
