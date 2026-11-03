- A bird misnamed from one distant whole frame is now corrected by its crops. When the first name
  came from an uncropped whole frame, such as a recording frame used because Frigate kept no
  snapshot, and crops from at least two separate moments of the visit agree confidently on another
  species, the photo search renames the visit. It records the crop source and the number of
  supporting moments. Names from crops, video analysis, Frigate sublabels or your own choice are
  never replaced, and neither is a visit you have hidden. Hiding, tagging or choosing a species
  while the search runs still wins, because the final write checks again. Blocked, out-of-range
  and Unknown species never win, and the rename sends no new alert. See [Deep Video Analysis](docs/features/video-analysis.md#correcting-a-name-read-from-a-whole-frame).
- A renamed visit's photo is chosen for its new species. When every crop disputes a whole-frame
  name that is not corrected, the photo may show what the crops saw while the old name stays, a
  cue to check the visit. This never happens for a blocked, out-of-range, Unknown or non-bird crop
  species, or for a hidden, tagged or owner-chosen visit; their earlier photo choice stays.
