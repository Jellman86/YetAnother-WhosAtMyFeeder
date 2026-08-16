# Video Will Not Play in Safari

A recording that plays in Firefox or Chrome, and opens fine in QuickTime, can still
refuse to play in Safari. The usual cause is not the recording itself but how it is
packaged.

## Why Safari is different

HEVC video in an MP4 carries a four character sample format. Two are in common use:

| Sample format | QuickTime | Safari `<video>` |
| --- | --- | --- |
| `hvc1` | Plays | Plays |
| `hev1` | Plays | Refuses |

Because QuickTime accepts both, downloading the clip and opening it does not tell you
whether Safari will play it. That test can look like a pass while the real cause is
still in place.

## Check how your clips are packaged

Capture a diagnostics bundle from **Settings > Health > Diagnostics export**. It
includes a `media_sample` section describing a recent clip:

```json
"media_sample": {
  "available": true,
  "codec_tag": "hvc1",
  "codec": "hevc",
  "safari_compatible": true,
  "note": "hevc tagged hvc1."
}
```

`safari_compatible: false` means the clip is tagged `hev1`, and that is the cause.
`codec: "h264"` means the packaging is not involved and the problem is elsewhere.

## Fix

Frigate has a per camera setting for this:

```yaml
cameras:
  your_camera:
    ffmpeg:
      apple_compatibility: true
```

See [Frigate's H.265 cameras via Safari guidance](https://docs.frigate.video/configuration/camera_specific/#h265-cameras-via-safari).

Two things are easy to miss:

- It applies only to recording segments created after the setting is added and Frigate
  is restarted. Existing events keep their original packaging, so test with a new one.
- YA-WAMF caches clips. A clip already in the cache keeps its old packaging until the
  cache entry is replaced.

## If it still fails

Capture a bundle after recording a new event and include it in your report, along with
the macOS and Safari versions and the approximate event time. If `safari_compatible` is
`true` and playback still fails, the packaging is ruled out and the next thing to look
at is the media proxy rather than the recording.
