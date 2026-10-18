"""Whether a stored detection belongs in a bird-specific export (#728).

The automatic admission guard (#727) keeps new known non-birds out of
feeder history, but it deliberately preserves old rows. A bird-specific
export (the eBird record format) is a separate boundary over that
history, decided from durable positive evidence only:

* the producing model output's catalogue group, bound to the stored
  artifact and output index, and
* the current identity's catalogue group, from its scientific name.

Absent evidence proves nothing in either direction, so a row neither
source knows keeps exporting exactly as before. An owner correction is
the current identity: the old model index that produced the row no
longer describes it and must not veto — or vouch for — the corrected
name. This module is pure; gathering the evidence is the caller's job.
"""

from app.services.model_output_groups import OutputGroup


def is_bird_exportable(
    *,
    manual_tagged: bool,
    producing_group: OutputGroup,
    identity_group: OutputGroup,
) -> bool:
    """True unless durable evidence positively identifies a non-bird."""
    if manual_tagged:
        return identity_group != "nonbird"
    return producing_group != "nonbird" and identity_group != "nonbird"
