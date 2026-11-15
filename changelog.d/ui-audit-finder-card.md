- **The bird finder card says where the finder runs, once, and why.** Settings → Models now has one
  "Runs on" row built from the last device check: the device that passed, or "CPU · Intel NPU
  failed the device check on 12 Nov" with the measured cause when the backend reports one. The
  repeated bold device sentence on every finder option is gone, and nothing guesses "not available
  in this image, on this host, or for the active model" any more, for the finder or for the
  identification model.
- **A saved device that has not passed stays saved.** The Device list names it "not passed on this
  host" and keeps it selectable, with one line saying the finder runs on CPU until it passes and
  what to do: check devices, or choose Automatic.
- **Check devices is one short button with its explanation under it.** Re-download moved behind
  Repair, and the background on the fallback finder and when a change takes effect is under "How
  the finder works".
