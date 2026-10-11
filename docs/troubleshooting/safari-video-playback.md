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

Capture a diagnostics bundle from **Settings → Health → Diagnostics export**. It
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

`safari_compatible: false` identifies the known `hev1` packaging incompatibility in that sampled
clip. `codec: "h264"` rules out this HEVC-tag issue for the sample, not every possible decoding or
proxy fault. An unavailable sample does not prove that all camera recordings are compatible.

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
`true` and playback still fails, compare the sample with the exact failing clip, then check the
media proxy's response and byte-range handling. One compatible sample does not rule out a
corrupt or differently encoded recording elsewhere.
