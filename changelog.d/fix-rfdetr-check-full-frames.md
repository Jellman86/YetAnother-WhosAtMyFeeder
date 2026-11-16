- The bird finder device check now runs on full camera frames. On hosts that keep
  bird crops as their snapshots (for example with the HQ bird crop option on), the
  check used to pick those crops, found no birds in them, and left RF-DETR on the CPU.
  It now skips crops, retained snapshots, thumbnails, event snapshots that HQ
  processing replaced with a bird crop, and images under 480 px on the short side or
  that do not fully decode. It prefers saved full frames (final-frame captures
  included) and takes at most two per visit. The snapshot folder is read only when a
  check is due, and listed again only after it changes. A host
  without three full frames yet waits as "no full frames", says so under Runs on, and
  retries when they appear. Check devices uses the same frames, and a check that
  failed on the old crop panel runs again straight after the update.
