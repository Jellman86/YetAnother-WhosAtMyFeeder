# Upstream issue verification, 17 September 2026

## GPU validation, #479

Provider-specific runtime identities avoid invalidation by unrelated libraries. A previously
passing active accelerator receives one persisted recovery attempt per runtime/model identity.
Interrupted and failed attempts do not loop. Selection changes during validation discard the
pending recovery result. The Dashboard reports recovery and provider fallback.

Quark's Intel GPU produced finite RoPE output with exact CPU top-five agreement on four real
images. ConvNext CPU worked, but the Intel GPU probe aborted in the native runtime with a
`longjmp` stack-frame error. This is a failed device test, not evidence to bypass validation.
The isolated probe kept the live service running. Picard's RTX 4070 ran the RoPE ONNX artifact
using ONNX Runtime 1.26.0 CUDA with finite output and exact CPU top-one/top-five agreement on
four synthetic inputs. This establishes runtime execution, not model accuracy on wildlife.

A second review found a shutdown race: the child could exit between checking its status and
killing it, replacing cancellation with a process-lookup exception. A regression test now
requires reaping the child and preserving cancellation in that case.

## Photograph and frame choices, #481

Fallback crops use the same recorded-species/detail gate as ranked candidates. A selected
crop or full scene remains the preview's image, and the preview read comes from that image.
Existing HQ photographs permit explicit regeneration; empty generation retains saved choices.
The title, controls and frame strip occupy normal flow below the photo.

The reporter's actual 3840×2160 clip decoded independent frames at 1.48, 2.97 and 4.45 seconds
on Quark. Desktop and 390-pixel phone layouts showed no photo/footer overlap or horizontal
page overflow. Tests cover mismatched and unclassified crops, chosen framing and regeneration.

## Local audio removal, #478

Owner-only hiding removes audio from history, summaries, nearby context and the live buffer.
Tombstones survive MQTT replay and retention. Tests cover restart, simultaneous ingest/removal,
restore, guest denial and reversible migration with retained rows. Upstream BirdNET deletion
sync is not implemented; missing media alone is not a reliable deletion signal. Existing visual
identifications remain unchanged. The UI states the local scope and offers Undo.

## HLS playback, #459

Existing HLS support was exercised against Quark in desktop Chromium and WebKit. Both loaded
master/variant playlists, initialization and media segments, advanced playback, and resumed
after seeking. Forcing the HLS entry playlist to return 404 in the test browser exercised the
MP4 fallback in WebKit; playback and seeking still worked. This tests the Safari engine, not a
physical iPhone. Physical iOS verification remains necessary before claiming that device's
playback behaviour is settled.
