"""Shape stored bird detections into the API detection view for one viewer.

Which name a viewer reads in their language, which nearby audio they may hear
about and which owner-only fields a guest never receives are decided here
once, so the event list, visits and later the daily summary and species detail
cannot drift apart. Network work such as asking Frigate which clips exist
happens before this is called; the presenter only reads the history
connection it is given.
"""

import asyncio
from dataclasses import dataclass

import aiosqlite

from app.config import settings
from app.models import DetectionBirdSummary, DetectionResponse
from app.repositories.audio_history_repository import AudioHistoryRepository
from app.repositories.bird_observation_repository import BirdObservationRepository
from app.repositories.detection_repository import Detection as StoredDetection
from app.services.bird_summary_names import name_summaries, resolve_label_names, summary_labels
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.utils.audio_localization import localize_audio_detections, localize_audio_species_name
from app.utils.canonical_species import user_facing_species_fields
from app.utils.public_access import approximate_coordinate, hide_public_audio_fields, refresh_public_audio_fields

LOCALIZED_NAME_CONCURRENCY = 5


@dataclass(frozen=True)
class PresentationScope:
    """Who is looking, in which language."""

    language: str
    is_owner: bool

    @property
    def hides_camera_names(self) -> bool:
        return not self.is_owner and settings.public_access.enabled and not settings.public_access.show_camera_names


def video_classification_model_name(model_id: str | None) -> str | None:
    """A display name for the model that produced a classification.

    Falls back to the id itself when the registry does not know it. Returning
    nothing hid the model entirely on the detection card, which reads as "no
    model was involved" rather than "this model is no longer published" (§5).
    """
    normalized = str(model_id or "").strip()
    if not normalized:
        return None
    try:
        from app.services.model_manager import REMOTE_REGISTRY

        registry = list(REMOTE_REGISTRY)
    except Exception:
        return normalized

    model_meta = next((m for m in registry if m.get("id") == normalized), None)
    if model_meta:
        return str(model_meta.get("name") or "").strip() or normalized

    # A regional model is addressed as `parent/region`; the variant is nested
    # under its parent and carries no id of its own, so an exact match misses.
    if "/" in normalized:
        parent_id, _, region = normalized.partition("/")
        parent = next((m for m in registry if m.get("id") == parent_id), None)
        variant = dict((parent or {}).get("region_variants", {}).get(region) or {})
        if variant or parent:
            base = str(variant.get("name") or (parent or {}).get("name") or parent_id).strip()
            label = region.strip().upper()
            return f"{base} ({label})" if base and label else base or normalized

    return normalized


async def present_detections(
    events: list[StoredDetection],
    scope: PresentationScope,
    db: aiosqlite.Connection,
    *,
    clip_availability: dict[str, dict[str, bool]],
    manual_observations: dict[str, dict[str, object]],
) -> list[DetectionResponse]:
    """The detection view of each stored row, in order, with everything this viewer may not see removed."""
    language = scope.language
    event_ids = [event.frigate_event for event in events]
    audio_history = AudioHistoryRepository(db)
    # Get labels that should be displayed as "Unknown Bird"
    unknown_labels = settings.classification.unknown_bird_labels

    # Preload localized names for this page to avoid per-row network calls.
    localized_names: dict[int, str] = {}
    taxa_ids = {event.taxa_id for event in events if event.taxa_id}
    if taxa_ids:
        semaphore = asyncio.Semaphore(LOCALIZED_NAME_CONCURRENCY)

        async def lookup(taxa_id: int) -> tuple[int, str | None]:
            async with semaphore:
                name = (
                    await taxonomy_service.get_localized_common_name(taxa_id, language, db=db)
                    if language != "en"
                    else await taxonomy_service.get_canonical_english_name(taxa_id, db=db)
                )
                return taxa_id, name

        results = await asyncio.gather(*(lookup(taxa_id) for taxa_id in taxa_ids))
        localized_names = {taxa_id: name for taxa_id, name in results if name}

    bird_summaries = await BirdObservationRepository(db).summaries_for_events(event_ids) if scope.is_owner else {}
    if bird_summaries:
        label_names = await asyncio.to_thread(resolve_label_names, summary_labels(bird_summaries), language)
        bird_summaries = name_summaries(bird_summaries, label_names)

    public_audio = {}
    if not scope.is_owner:
        if settings.public_access.show_audio:
            public_audio = await audio_history.get_public_audio_for_detections(events)
        for event in events:
            await refresh_public_audio_fields(event, audio_history, public_audio.get(event.frigate_event, {}))

    # Pre-resolve unconfirmed audio_species names concurrently.
    # audio_confirmed species are resolved via localized_names[taxa_id] in the loop below.
    unconfirmed_audio_species: set[str] = {
        event.audio_species.strip() for event in events if event.audio_species and not event.audio_confirmed
    }
    unconfirmed_audio_canonical: dict[str, str] = {}
    if unconfirmed_audio_species:

        async def resolve_unconfirmed(comname: str) -> tuple[str, str | None]:
            return comname, await localize_audio_species_name(comname, language, db)

        audio_pairs = await asyncio.gather(*(resolve_unconfirmed(n) for n in unconfirmed_audio_species))
        unconfirmed_audio_canonical = {k: v for k, v in audio_pairs if v}

    owner_audio_contexts = {}
    if scope.is_owner:
        owner_audio_contexts = await audio_history.get_audio_contexts_for_detections(
            [event for event in events if event.audio_species and not event.audio_confirmed],
            settings.frigate.camera_audio_mapping or {},
            settings.frigate.audio_correlation_window_seconds,
        )

    audio_context_species_by_event: dict[str, list[str]] = {}
    for event in events:
        if not scope.is_owner and not settings.public_access.show_audio:
            continue
        if event.audio_confirmed or not event.audio_species:
            continue

        # The suppressed count is for the detail view, which explains an empty
        # result; the event list only needs the species it can show.
        if scope.is_owner:
            nearby_audio, _ = owner_audio_contexts[event.frigate_event]
        else:
            nearby_audio = public_audio.get(event.frigate_event, {}).get("context", [])
        await localize_audio_detections(nearby_audio, language, db)

        seen_species: set[str] = set()
        ordered_species: list[str] = []

        raw_primary = str(event.audio_species or "").strip()
        primary_heard = unconfirmed_audio_canonical.get(raw_primary, raw_primary)
        if primary_heard:
            ordered_species.append(primary_heard)
            seen_species.add(primary_heard.casefold())

        for item in nearby_audio:
            species_name = str(item.get("species") or "").strip()
            if not species_name:
                continue
            species_key = species_name.casefold()
            if species_key in seen_species:
                continue
            seen_species.add(species_key)
            ordered_species.append(species_name)
            if len(ordered_species) >= 4:
                break

        if ordered_species:
            audio_context_species_by_event[event.frigate_event] = ordered_species

    # Convert to response models with clip info
    response_events = []
    for event in events:
        manual_metadata = manual_observations.get(event.frigate_event, {})
        # Transform unknown bird labels for display
        public_species = user_facing_species_fields(
            display_name=event.display_name,
            category_name=event.category_name,
            scientific_name=event.scientific_name,
            common_name=event.common_name,
            taxa_id=event.taxa_id,
            extra_unknown_labels=unknown_labels,
        )
        display_name = str(public_species["display_name"])
        category_name = public_species["category_name"]
        common_name = public_species["common_name"]
        scientific_name = public_species["scientific_name"]
        taxa_id = public_species["taxa_id"]
        # Replace stored name with canonical/localized name to handle BirdNET locale mismatch
        if taxa_id:
            localized_name = localized_names.get(taxa_id)
            if localized_name:
                common_name = localized_name

        # Resolve audio_species: confirmed case shares taxa_id with visual detection;
        # unconfirmed (or confirmed-but-no-taxa_id) was pre-resolved above.
        raw_audio_species = event.audio_species
        if raw_audio_species:
            if event.audio_confirmed and taxa_id:
                # Same species as visual — canonical name already in localized_names
                resolved_audio = localized_names.get(taxa_id) or raw_audio_species
            elif event.audio_confirmed:
                # Confirmed but taxonomy not enriched yet — nothing to resolve
                resolved_audio = raw_audio_species
            else:
                resolved_audio = unconfirmed_audio_canonical.get(raw_audio_species.strip(), raw_audio_species)
        else:
            resolved_audio = raw_audio_species

        response_event = DetectionResponse(
            id=event.id,
            classification_input=event.classification_input if scope.is_owner else None,
            initial_classification_input=event.initial_classification_input if scope.is_owner else None,
            detection_time=event.detection_time,
            detection_index=event.detection_index,
            score=event.score,
            display_name=display_name,
            category_name=category_name,
            frigate_event=event.frigate_event,
            observation_source="manual_upload" if event.frigate_event.startswith("manual_") else "frigate",
            observation_notes=manual_metadata.get("notes"),
            observation_latitude=(
                approximate_coordinate(manual_metadata.get("latitude"))
                if not scope.is_owner and settings.public_access.location_precision == "approximate"
                else manual_metadata.get("latitude")
            ),
            observation_longitude=(
                approximate_coordinate(manual_metadata.get("longitude"))
                if not scope.is_owner and settings.public_access.location_precision == "approximate"
                else manual_metadata.get("longitude")
            ),
            observation_location_source=manual_metadata.get("location_source"),
            camera_name="Hidden" if scope.hides_camera_names else event.camera_name,
            has_clip=clip_availability.get(event.frigate_event, {}).get("has_clip", False),
            has_snapshot=clip_availability.get(event.frigate_event, {}).get("has_snapshot", False),
            has_frigate_event=clip_availability.get(event.frigate_event, {}).get("has_frigate_event", False),
            is_hidden=event.is_hidden,
            is_favorite=event.is_favorite,
            archive_state=event.archive_state,
            frigate_score=event.frigate_score,
            sub_label=event.sub_label,
            manual_tagged=event.manual_tagged,
            audio_confirmed=event.audio_confirmed,
            audio_species=resolved_audio,
            audio_score=event.audio_score,
            audio_context_species=audio_context_species_by_event.get(event.frigate_event),
            temperature=event.temperature,
            weather_condition=event.weather_condition,
            weather_cloud_cover=event.weather_cloud_cover,
            weather_wind_speed=event.weather_wind_speed,
            weather_wind_direction=event.weather_wind_direction,
            weather_precipitation=event.weather_precipitation,
            weather_rain=event.weather_rain,
            weather_snowfall=event.weather_snowfall,
            scientific_name=scientific_name,
            common_name=common_name,
            taxa_id=taxa_id,
            frigate_status=event.frigate_status,
            frigate_missing_since=event.frigate_missing_since,
            frigate_last_checked_at=event.frigate_last_checked_at,
            frigate_last_error=event.frigate_last_error,
            video_classification_score=event.video_classification_score,
            video_classification_label=event.video_classification_label,
            video_classification_timestamp=event.video_classification_timestamp,
            video_classification_status=event.video_classification_status,
            video_classification_error=event.video_classification_error,
            video_classification_provider=event.video_classification_provider,
            video_classification_backend=event.video_classification_backend,
            video_classification_model_id=event.video_classification_model_id,
            video_classification_model_name=video_classification_model_name(event.video_classification_model_id),
            video_classification_input_source=event.video_classification_input_source,
            video_classification_diagnostics=event.video_classification_diagnostics,
            ai_analysis=event.ai_analysis,
            ai_analysis_timestamp=event.ai_analysis_timestamp,
        )
        if scope.is_owner:
            summary = bird_summaries.get(event.frigate_event)
            response_event.bird_summary = DetectionBirdSummary.model_validate(summary) if summary else None
        if not scope.is_owner:
            # Public HTTP responses are the authoritative projection used after
            # SSE invalidation; producer diagnostics are owner information.
            for field in (
                "frigate_last_error",
                "video_classification_error",
                "video_classification_diagnostics",
                "video_classification_provider",
                "video_classification_backend",
                "video_classification_model_id",
                "video_classification_model_name",
                "video_classification_input_source",
            ):
                setattr(response_event, field, None)
            if not settings.public_access.show_audio:
                hide_public_audio_fields(response_event)
            if not settings.public_access.show_ai_conversation:
                response_event.ai_analysis = None
                response_event.ai_analysis_timestamp = None
        response_events.append(response_event)
    return response_events
