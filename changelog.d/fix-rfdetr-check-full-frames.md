- The bird finder device check now runs on full camera frames. On hosts that keep
  bird crops as their snapshots (for example with the HQ bird crop option on), the
  check used to pick those crops, found no birds in them, and left RF-DETR on the CPU.
  It now skips crops, retained snapshots, thumbnails and images under 480 px on the
  short side, prefers saved full frames, and takes at most two per visit. A host
  without three full frames yet waits as "no full frames", says so under Runs on, and
  retries when they appear. Check devices uses the same frames, and a check that
  failed on the old crop panel runs again straight after the update.
