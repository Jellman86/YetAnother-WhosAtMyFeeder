from app.utils.canonical_species import should_hide_species_label


def rank_video_top_frames(
    frame_scores: list[dict],
    *,
    limit: int,
    clip_variant: str,
) -> list[dict]:
    """Rank video-analysis frames, ignoring Unknown frames when known frames exist."""
    known_frames = [
        frame
        for frame in frame_scores
        if not should_hide_species_label(frame.get("top_label"))
    ]
    candidate_frames = known_frames if known_frames else frame_scores
    sorted_frames = sorted(candidate_frames, key=lambda f: f["frame_score"], reverse=True)
    return [
        {**frame, "rank": rank, "clip_variant": clip_variant}
        for rank, frame in enumerate(sorted_frames[:limit], 1)
    ]
