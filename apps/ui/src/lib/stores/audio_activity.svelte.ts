/**
 * BirdNET-Go calls heard, hidden or restored, as the live stream announces them to the owner. Views
 * of recent audio follow `version` instead of polling while the stream is connected.
 */
class AudioActivity {
    version = $state(0);

    announce(): void {
        this.version += 1;
    }
}

export const audioActivity = new AudioActivity();
