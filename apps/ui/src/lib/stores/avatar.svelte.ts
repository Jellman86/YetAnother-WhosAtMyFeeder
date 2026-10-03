import { deleteAvatar, fetchAvatar, uploadAvatar } from '../api/auth';
import { logger } from '../utils/logger';
import { getErrorMessage } from '../utils/error-handling';

/**
 * The owner's profile picture as an object URL. The picture is an owner-only route, so it is
 * fetched with the owner's credentials rather than linked; the version from the auth status
 * decides when to fetch again, and an old URL is released when it is replaced.
 */
class AvatarStore {
    url = $state<string | null>(null);
    private loadedVersion: number | null = null;
    private generation = 0;

    sync(version: number | null): void {
        if (version === this.loadedVersion) return;
        this.loadedVersion = version;
        const generation = ++this.generation;
        if (version === null) {
            this.replace(null);
            return;
        }
        void fetchAvatar()
            .then((blob) => {
                if (generation !== this.generation) return;
                this.replace(blob ? URL.createObjectURL(blob) : null);
            })
            .catch((error) => {
                if (generation !== this.generation) return;
                logger.warn('Profile picture unavailable', { message: getErrorMessage(error) });
                this.replace(null);
            });
    }

    async upload(file: File): Promise<void> {
        const { avatar_version } = await uploadAvatar(file);
        this.sync(avatar_version ?? null);
    }

    async remove(): Promise<void> {
        await deleteAvatar();
        this.sync(null);
    }

    private replace(next: string | null): void {
        if (this.url) URL.revokeObjectURL(this.url);
        this.url = next;
    }
}

export const avatarStore = new AvatarStore();
