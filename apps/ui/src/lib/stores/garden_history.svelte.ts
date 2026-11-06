/** Invalidates private Garden projections without adding animal data to bird history. */
class GardenHistory {
    version = $state(0);

    invalidate(): void {
        this.version += 1;
    }
}

export const gardenHistory = new GardenHistory();
