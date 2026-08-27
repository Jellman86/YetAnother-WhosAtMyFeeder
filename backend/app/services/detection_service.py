import structlog
import os
import asyncio
import math
from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services.classifier_service import ClassifierService, get_classifier
from app.services.species_catalog_resolver import ShadowResolution, species_catalog_resolver
from app.services.broadcaster import broadcaster
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.birdweather_service import birdweather_service
from app.utils.classifier_labels import normalize_classifier_label
from app.utils.canonical_species import (
    UNKNOWN_BIRD_DISPLAY_LABEL,
    rewrite_label,
    should_hide_species_label,
    unknown_species_labels,
    user_facing_species_fields,
)
from app.utils.blocked_species import is_blocked_species
from app.utils.frigate import normalize_sub_label
from app.utils.api_datetime import serialize_api_datetime, utc_naive_from_timestamp
from app.utils.tasks import create_background_task
from app.database import get_db

log = structlog.get_logger()


async def _catalog_shadow_resolution(
    classification: dict, scientific_name: str | None, frigate_event: str
) -> ShadowResolution:
    """Resolve the winning output through the catalogue beside the label path.

    Best-effort by design: any failure here degrades to a detection without
    canonical identity, never to a dropped detection.
    """
    output_index = classification.get("index")
    if not isinstance(output_index, int) or output_index < 0:
        return ShadowResolution(verdict="unavailable")
    try:
        model_sha256 = get_classifier().active_model_sha256()
        if not model_sha256:
            return ShadowResolution(verdict="unavailable")
        return await asyncio.to_thread(
            species_catalog_resolver.shadow_resolve,
            model_sha256,
            output_index,
            scientific_name,
            frigate_event,
        )
    except Exception as error:
        log.debug("Catalogue shadow resolution unavailable", event_id=frigate_event, error=str(error))
        return ShadowResolution(verdict="unavailable")


async def _catalog_identity_for_refinement(
    refinement_model_id: str | None, output_index: int | None, scientific_name: str | None, frigate_event: str
) -> ShadowResolution:
    """Shadow-resolve a queued refinement result, guarding against model swaps.

    A video result can be applied after the owner switches models; attributing
    it to the currently loaded artifact would record false provenance, so the
    result resolves only while the refining model is still the active one.
    """
    if not isinstance(output_index, int) or output_index < 0:
        return ShadowResolution(verdict="unavailable")
    try:
        classifier = get_classifier()
        status = classifier.get_status()
        current_model_id = str(status.get("effective_model_id") or status.get("active_model_id") or "").strip()
        if refinement_model_id and current_model_id and refinement_model_id != current_model_id:
            return ShadowResolution(verdict="unavailable")
        model_sha256 = classifier.active_model_sha256()
        if not model_sha256:
            return ShadowResolution(verdict="unavailable")
        return await asyncio.to_thread(
            species_catalog_resolver.shadow_resolve,
            model_sha256,
            output_index,
            scientific_name,
            frigate_event,
        )
    except Exception as error:
        log.debug("Catalogue refinement resolution unavailable", event_id=frigate_event, error=str(error))
        return ShadowResolution(verdict="unavailable")


TAXONOMY_LOOKUP_TIMEOUT_SECONDS = max(0.5, float(os.getenv("TAXONOMY_LOOKUP_TIMEOUT_SECONDS", "3")))


class DetectionService:
    """
    Centralized service for processing and saving detections.

    Shared logic used by:
    - EventProcessor (real-time MQTT events)
    - BackfillService (historical API events)
    """

    def __init__(self, classifier: ClassifierService):
        self.classifier = classifier
        self.broadcaster = broadcaster

    @staticmethod
    def _build_unknown_catchall(classification: dict, *, source: str) -> dict:
        """Preserve runtime provenance while hiding an untrusted species label."""
        return {
            "label": "Unknown Bird",
            "score": float(classification["score"]),
            "index": classification.get("index", -1),
            "source": source,
            **{
                key: classification[key]
                for key in (
                    "inference_provider",
                    "inference_backend",
                    "model_id",
                    "model_name",
                    "input_source",
                    "input_is_cropped",
                )
                if key in classification
            },
        }

    def filter_and_label(
        self,
        classification: dict,
        frigate_event: str,
        frigate_sub_label: str = None,
        frigate_score: float = None,
        frigate_sub_label_score: float = None,
    ) -> tuple[dict | None, str | None]:
        """
        Apply filtering and relabeling rules to a classification result.
        Returns (result_dict, reason_code).
        reason_code is populated when result is None (skip reason) or informative when result exists.
        """
        frigate_sub_label = normalize_sub_label(frigate_sub_label)
        top = classification
        try:
            score = float(top["score"])
        except (KeyError, TypeError, ValueError):
            log.warning("Invalid classification score", event_id=frigate_event, score=top.get("score"))
            return None, "invalid_score"
        if not math.isfinite(score):
            log.warning("Non-finite classification score", event_id=frigate_event, score=score, label=top.get("label"))
            return None, "invalid_score"
        top = {**top, "score": score}
        label = normalize_classifier_label(top["label"])
        top = {**top, "label": label}
        original_label = label
        normalized_label = str(label or "").strip().casefold()
        normalized_frigate_sub_label = frigate_sub_label.casefold() if frigate_sub_label else None

        # Relabel unknown bird classifications
        if label in settings.classification.unknown_bird_labels:
            log.info("Relabeled to Unknown Bird", original=label, event_id=frigate_event)
            label = "Unknown Bird"
            top = {**top, "label": label}

        if should_hide_species_label(label, extra_unknown_labels=unknown_species_labels()):
            log.info("Discarding classifier abstention label", label=label, event_id=frigate_event)
            return None, "abstention_label"

        # Filter out blocked labels (case-insensitive).
        # Also check the parenthetical-stripped label (e.g. "Cassin's Finch (Adult Male)" →
        # "Cassin's Finch") so that users can block a species by its base name regardless of
        # the plumage/age variant the model outputs.  Also check the Frigate sub_label, which
        # is always the plain common name and may differ from the (possibly parenthetical-laden)
        # local-model label.
        if is_blocked_species(
            blocked_labels=settings.classification.blocked_labels,
            blocked_species=getattr(settings.classification, "blocked_species", []),
            label=label,
            extra_labels=[frigate_sub_label],
        ):
            log.debug("Filtered blocked label", label=label, event_id=frigate_event)
            return None, "blocked_label"

        # Determine effective minimum confidence (floor)
        # If user sets threshold lower than min_confidence, use threshold as floor
        effective_min = min(settings.classification.min_confidence, settings.classification.threshold)

        # Check minimum confidence floor
        below_min_confidence = score < effective_min

        # Check primary threshold, with stricter guard when Frigate sublabel disagrees
        # and Frigate trust is disabled.
        required_threshold = float(settings.classification.threshold or 0.0)
        threshold_reason = "threshold_passed"
        sublabel_disagrees = bool(
            not settings.classification.trust_frigate_sublabel
            and normalized_frigate_sub_label
            and normalized_label
            and normalized_frigate_sub_label != normalized_label
        )
        if sublabel_disagrees:
            disagreement_min_score = min(0.95, required_threshold + 0.20)
            required_threshold = max(required_threshold, disagreement_min_score)
            threshold_reason = "threshold_passed_with_sublabel_disagreement_guard"

        below_threshold = score < required_threshold

        # If classification passes primary threshold, return it
        # (Implicitly passes min_confidence because threshold >= effective_min)
        if not below_threshold:
            return top, threshold_reason

        # Classification failed primary threshold - check if we can fall back to Frigate sublabel
        if settings.classification.trust_frigate_sublabel and frigate_sub_label:
            final_score = (
                frigate_sub_label_score
                if frigate_sub_label_score is not None
                else max(score, settings.classification.threshold)
            )

            # Frigate sublabel exists - use it as fallback regardless of confidence
            log.info(
                "Using Frigate sublabel as fallback",
                frigate_label=frigate_sub_label,
                yawamf_label=original_label,
                yawamf_score=score,
                final_score=final_score,
                event_id=frigate_event,
            )
            return {
                "label": frigate_sub_label,
                "score": final_score,
                "index": top.get("index", -1),
                "source": "frigate_fallback",
                "input_source": "frigate_sublabel",
            }, "frigate_fallback"

        # Check for "Unknown Bird" catch-all (middle ground between min_confidence and threshold)
        if not below_min_confidence:
            log.info(
                "Low confidence detection, saving as Unknown",
                original=original_label,
                score=score,
                required_threshold=required_threshold,
                sublabel_disagrees=sublabel_disagrees,
                event_id=frigate_event,
            )
            return self._build_unknown_catchall(top, source="low_confidence_catchall"), "unknown_catchall"

        # No fallback available or below absolute floor
        if below_min_confidence:
            log.debug("Below minimum confidence", score=score, min=effective_min, event_id=frigate_event)
            return None, "low_confidence"
        else:
            # This branch implies (not below_min and below_threshold) which is handled by catch-all above
            # But just in case logic drifts:
            log.debug(
                "Below threshold", score=score, threshold=settings.classification.threshold, event_id=frigate_event
            )
            return None, "below_threshold"

    def select_usable_classification(
        self,
        classifications: list[dict],
        frigate_event: str,
        frigate_sub_label: str = None,
        frigate_score: float = None,
        frigate_sub_label_score: float = None,
    ) -> tuple[dict | None, str | None]:
        """Return the first classifier result that survives filtering.

        Some model artifacts expose abstention classes such as "Unknown" or
        "No detection". Those classes are diagnostics, not useful species
        labels, so lower-ranked concrete species should still get a chance.
        """
        last_reason: str | None = None
        for classification in classifications or []:
            top, reason = self.filter_and_label(
                classification,
                frigate_event,
                frigate_sub_label,
                frigate_score,
                frigate_sub_label_score,
            )
            if top:
                return top, reason
            last_reason = reason
        fallback_label = normalize_sub_label(frigate_sub_label)
        if settings.classification.trust_frigate_sublabel and fallback_label:
            final_score = (
                frigate_sub_label_score
                if frigate_sub_label_score is not None
                else max(settings.classification.min_confidence, settings.classification.threshold)
            )
            return {
                "label": fallback_label,
                "score": final_score,
                "index": -1,
                "source": "frigate_fallback",
                "input_source": "frigate_sublabel",
            }, "frigate_fallback"
        return None, last_reason

    def select_manual_reclassification(
        self,
        classifications: list[dict],
        frigate_event: str,
        frigate_sub_label: str = None,
        frigate_score: float = None,
        frigate_sub_label_score: float = None,
    ) -> tuple[dict | None, str | None]:
        """Select a concrete result that is safe to apply on explicit reanalysis.

        A click on "reclassify" authorizes a new model run, not a confidence-
        threshold bypass. The normal live path may retain a mid-confidence result
        as ``Unknown Bird``; applying that catch-all during a manual run would
        silently downgrade a known identification. Manual reanalysis therefore
        requires the same concrete, above-threshold species evidence as a normal
        promotion.
        """
        selected, reason = self.select_usable_classification(
            classifications,
            frigate_event,
            frigate_sub_label,
            frigate_score,
            frigate_sub_label_score,
        )
        if selected is None:
            return None, reason
        if should_hide_species_label(
            selected.get("label"),
            extra_unknown_labels=unknown_species_labels(),
        ):
            return None, "below_threshold" if reason == "unknown_catchall" else (reason or "abstention_label")
        return selected, reason

    async def _is_blocked_with_taxonomy(
        self,
        *,
        label: str,
        scientific_name: str | None = None,
        common_name: str | None = None,
        taxa_id: int | None = None,
        extra_labels: list[str] | None = None,
        repo: "DetectionRepository | None" = None,
    ) -> bool:
        """Blocked-species check that bridges name variants via the taxonomy cache.

        A species blocked under one name or ``taxa_id`` must still be caught when the
        incoming label is a different variant. When identity is incomplete — the live
        taxonomy lookup timed out, or a write path (e.g. video promotion) skipped
        enrichment — fill the gaps from the taxonomy cache (a local read that never hangs
        on the network) before deciding. Abstention / unknown labels are never enriched.
        """
        extra = list(extra_labels or [])
        needs_bridge = taxa_id is None or not scientific_name or not common_name
        if needs_bridge and not should_hide_species_label(label):
            key = (scientific_name or label or "").strip()
            if key:
                cached: dict = {}
                try:
                    if repo is not None:
                        cached = await repo.get_taxonomy_names(key)
                    else:
                        async with get_db() as db:
                            cached = await DetectionRepository(db).get_taxonomy_names(key)
                except Exception as exc:
                    log.debug("Blocked-species taxonomy cache lookup failed", label=label, error=str(exc))
                    cached = {}
                if isinstance(cached, dict):
                    scientific_name = scientific_name or cached.get("scientific_name")
                    common_name = common_name or cached.get("common_name")
                    if taxa_id is None:
                        taxa_id = cached.get("taxa_id")
        return is_blocked_species(
            blocked_labels=settings.classification.blocked_labels,
            blocked_species=getattr(settings.classification, "blocked_species", []),
            label=label,
            scientific_name=scientific_name,
            common_name=common_name,
            taxa_id=taxa_id,
            extra_labels=extra,
        )

    async def save_detection(
        self,
        frigate_event: str,
        camera: str,
        start_time: float,
        classification: dict,
        frigate_score: float = None,
        sub_label: str = None,
        audio_confirmed: bool = False,
        audio_species: str = None,
        audio_score: float = None,
        temperature: float = None,
        weather_condition: str = None,
        weather_cloud_cover: float = None,
        weather_wind_speed: float = None,
        weather_wind_direction: float = None,
        weather_precipitation: float = None,
        weather_rain: float = None,
        weather_snowfall: float = None,
    ) -> tuple[bool, bool]:
        """
        Save or update a detection in the database and broadcast the event.
        Returns (changed, was_inserted).
        """
        sub_label = normalize_sub_label(sub_label)

        # 1. Normalize names (Bidirectional Scientific <-> Common)
        label = rewrite_label(classification["label"])
        taxonomy: dict = {}
        try:
            taxonomy = await asyncio.wait_for(
                taxonomy_service.get_names(label),
                timeout=TAXONOMY_LOOKUP_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            log.warning(
                "Taxonomy lookup timed out during detection save",
                label=label,
                timeout_seconds=TAXONOMY_LOOKUP_TIMEOUT_SECONDS,
            )
        except Exception as e:
            log.warning(
                "Taxonomy lookup failed during detection save",
                label=label,
                error=str(e),
            )
        if not isinstance(taxonomy, dict):
            taxonomy = {}

        scientific_name = taxonomy.get("scientific_name")
        common_name = taxonomy.get("common_name")
        taxa_id = taxonomy.get("taxa_id")

        # Preserve raw broad/non-species classifier labels in category_name for
        # diagnostics, but surface them to the rest of the app as Unknown Bird.
        if should_hide_species_label(label):
            scientific_name = None
            common_name = None
            taxa_id = None
        else:
            scientific_name = scientific_name or label

        # Re-check blocked list against taxonomy-resolved canonical names so that
        # blocking by scientific name catches models that output common names and vice versa.
        extra_block_labels = [UNKNOWN_BIRD_DISPLAY_LABEL] if should_hide_species_label(label) else []
        if await self._is_blocked_with_taxonomy(
            label=label,
            scientific_name=scientific_name,
            common_name=common_name,
            taxa_id=taxa_id,
            extra_labels=extra_block_labels,
        ):
            log.debug(
                "Filtered blocked species via taxonomy",
                label=label,
                scientific_name=scientific_name,
                event_id=frigate_event,
            )
            return False, False

        # 2. Determine display name based on user preference
        display_name = label
        if should_hide_species_label(label):
            display_name = UNKNOWN_BIRD_DISPLAY_LABEL
        else:
            # Try localized name first if notification_language is non-English
            display_lang = getattr(settings.notifications, "notification_language", None)
            localized_name = None
            if display_lang and display_lang != "en" and taxa_id:
                try:
                    localized_name = await taxonomy_service.get_localized_common_name(taxa_id, display_lang)
                except Exception as exc:
                    log.debug(
                        "Localized display name lookup failed", taxa_id=taxa_id, lang=display_lang, error=str(exc)
                    )

            if localized_name:
                display_name = localized_name
            elif settings.classification.display_common_names and common_name:
                display_name = common_name
            elif not settings.classification.display_common_names and scientific_name:
                display_name = scientific_name

        shadow = await _catalog_shadow_resolution(classification, scientific_name, frigate_event)

        async with get_db() as db:
            repo = DetectionRepository(db)

            score = float(classification["score"])
            if not math.isfinite(score):
                log.warning("Refusing to save detection with non-finite score", event_id=frigate_event, score=score)
                return False, False
            category_name = classification["label"]
            timestamp = utc_naive_from_timestamp(start_time)

            detection = Detection(
                detection_time=timestamp,
                detection_index=classification["index"],
                species_id=shadow.species_id,
                model_artifact_id=shadow.model_artifact_id,
                model_output_index=shadow.model_output_index,
                score=score,
                display_name=display_name,
                category_name=category_name,
                frigate_event=frigate_event,
                camera_name=camera,
                frigate_score=frigate_score,
                sub_label=sub_label,
                audio_confirmed=audio_confirmed,
                audio_species=audio_species,
                audio_score=audio_score,
                temperature=temperature,
                weather_condition=weather_condition,
                weather_cloud_cover=weather_cloud_cover,
                weather_wind_speed=weather_wind_speed,
                weather_wind_direction=weather_wind_direction,
                weather_precipitation=weather_precipitation,
                weather_rain=weather_rain,
                weather_snowfall=weather_snowfall,
                scientific_name=scientific_name,
                common_name=common_name,
                taxa_id=taxa_id,
            )

            # Atomic upsert: insert or update only if score is higher
            was_inserted, was_updated = await repo.upsert_if_higher_score(detection)
            changed = was_inserted or was_updated

            if changed:
                persisted = await repo.get_by_frigate_event(frigate_event)
                log.info(
                    "Saved detection",
                    event_id=frigate_event,
                    species=display_name,
                    scientific=scientific_name,
                    score=score,
                    frigate_score=frigate_score,
                    audio_confirmed=audio_confirmed,
                    weather=weather_condition,
                )

                public_species = user_facing_species_fields(
                    display_name=display_name,
                    category_name=category_name,
                    scientific_name=scientific_name,
                    common_name=common_name,
                    taxa_id=taxa_id,
                )
                # NOTE: audio_species and common_name in this SSE payload are raw stored values
                # (potentially non-English from BirdNET-Go). Per-client localization is not
                # possible here — the broadcast is language-agnostic. Clients should re-fetch
                # via GET /events for localized names.
                await self.broadcaster.broadcast(
                    {
                        "type": "detection",
                        "data": {
                            "frigate_event": frigate_event,
                            "display_name": public_species["display_name"],
                            "category_name": public_species["category_name"],
                            "scientific_name": public_species["scientific_name"],
                            "common_name": public_species["common_name"],
                            "taxa_id": public_species["taxa_id"],
                            "score": score,
                            "timestamp": serialize_api_datetime(timestamp),
                            "camera": camera,
                            "is_favorite": persisted.is_favorite if persisted else detection.is_favorite,
                            "frigate_score": frigate_score,
                            "sub_label": sub_label,
                            "manual_tagged": persisted.manual_tagged if persisted else detection.manual_tagged,
                            "audio_confirmed": audio_confirmed,
                            "audio_species": audio_species,
                            "audio_score": audio_score,
                            "temperature": temperature,
                            "weather_condition": weather_condition,
                            "weather_cloud_cover": weather_cloud_cover,
                            "weather_wind_speed": weather_wind_speed,
                            "weather_wind_direction": weather_wind_direction,
                            "weather_precipitation": weather_precipitation,
                            "weather_rain": weather_rain,
                            "weather_snowfall": weather_snowfall,
                        },
                    }
                )

                # 3. Report to BirdWeather (if enabled)
                if scientific_name and scientific_name != "Unknown Bird":
                    # Run in background to not block the main loop
                    create_background_task(
                        birdweather_service.report_detection(
                            scientific_name=scientific_name,
                            common_name=common_name,
                            confidence=score,
                            timestamp=timestamp,
                        ),
                        name=f"birdweather_report:{frigate_event}",
                    )

            return changed, was_inserted

    async def get_detection_by_frigate_event(self, frigate_event: str) -> Detection | None:
        """Fetch a detection by Frigate event ID."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            return await repo.get_by_frigate_event(frigate_event)

    async def apply_video_result(
        self,
        frigate_event: str,
        video_label: str,
        video_score: float,
        video_index: int,
        manual_tagged: bool = False,
        video_provider: str | None = None,
        video_backend: str | None = None,
        video_model_id: str | None = None,
        video_input_source: str | None = None,
        persist_video_result: bool = True,
    ):
        """
        Process a trustworthy asynchronous classification result.

        ``persist_video_result`` is false for HQ crop consensus so refinement cannot mark a
        concurrently running deep-video job complete or replace its provenance columns.

        Override the primary ID when:
        - the action is an explicit/manual reclassification, or
        - the existing primary ID is an unknown-bird label, or
        - the video score clears a reliability gate for automated promotion.
        """
        async with get_db() as db:
            repo = DetectionRepository(db)
            existing = await repo.get_by_frigate_event(frigate_event)
            if not existing:
                log.warning("Cannot apply video result: event not found", event_id=frigate_event)
                return

            # Check whether the video result is a blocked species. Resolve taxonomy
            # (from the cache) so a species blocked by scientific name or taxa_id is still
            # caught when video analysis promotes it under a different name variant — the
            # raw label alone can't be bridged to the blocked entry. Parenthetical-stripped
            # forms (e.g. "Cassin's Finch (Adult Male)") are handled by the matcher.
            is_blocked = await self._is_blocked_with_taxonomy(
                label=video_label,
                extra_labels=[UNKNOWN_BIRD_DISPLAY_LABEL] if should_hide_species_label(video_label) else [],
                repo=repo,
            )

            normalized_video_label = normalize_classifier_label(video_label)
            hidden_video_label = should_hide_species_label(normalized_video_label)

            # 1. Video analysis updates its dedicated columns even when the result is blocked.
            # This marks the job as 'completed' so the stale watchdog and re-queue logic
            # don't pick it up again. HQ crop refinement deliberately leaves that state alone.
            if persist_video_result:
                await repo.update_video_classification(
                    frigate_event=frigate_event,
                    label=None if hidden_video_label and not manual_tagged else normalized_video_label,
                    score=video_score,
                    index=video_index,
                    status="completed",
                    provider=video_provider,
                    backend=video_backend,
                    model_id=video_model_id,
                    input_source=video_input_source,
                    blocked=is_blocked,
                )

            if is_blocked:
                log.debug(
                    "Video result is a blocked species; recorded but not promoted",
                    label=video_label,
                    event_id=frigate_event,
                )
                return False

            if getattr(existing, "manual_tagged", False) is True and not manual_tagged:
                log.info(
                    "Recorded automatic refinement without replacing manual identification",
                    event_id=frigate_event,
                    video_label=normalized_video_label,
                    video_score=video_score,
                )
                return False

            if hidden_video_label and not manual_tagged:
                log.debug(
                    "Video analysis produced Unknown; recording completion without promotion",
                    event_id=frigate_event,
                    video_score=video_score,
                )
                return False

            # 2. Only promote video results when they are trustworthy enough, but
            # always allow explicit/manual reclassifications and unknown-bird upgrades.
            existing_is_unknown = any(
                should_hide_species_label(candidate, extra_unknown_labels=unknown_species_labels())
                for candidate in (
                    getattr(existing, "display_name", None),
                    getattr(existing, "category_name", None),
                    getattr(existing, "scientific_name", None),
                    getattr(existing, "common_name", None),
                )
            )
            current_score = float(existing.score or 0.0)
            threshold = float(settings.classification.threshold or 0.0)
            min_confidence = float(getattr(settings.classification, "min_confidence", 0.0) or 0.0)
            effective_floor = min(min_confidence, threshold)
            # Allow auto video to rescue low-confidence primary IDs without
            # requiring the full promotion threshold when the existing label
            # never cleared that threshold in the first place.
            baseline_gate = threshold if current_score >= threshold else effective_floor
            base_required_score = max(current_score, baseline_gate)

            normalized_video_label = str(normalized_video_label or "").strip().casefold()
            normalized_sub_label = normalize_sub_label(getattr(existing, "sub_label", None))
            normalized_sub_label = normalized_sub_label.casefold() if normalized_sub_label else None
            sublabel_disagrees = bool(
                normalized_sub_label and normalized_video_label and normalized_sub_label != normalized_video_label
            )

            required_score = base_required_score
            override_reason = "score_gate_passed"
            if sublabel_disagrees:
                disagreement_min_score = min(0.95, threshold + 0.20)
                required_score = max(required_score, disagreement_min_score)
                override_reason = "score_gate_passed_with_sublabel_disagreement"

            # Minimum confidence required to promote a video result onto an
            # Unknown-Bird detection.  Deliberately permissive (much lower than
            # the main threshold) so genuine identifications still get through,
            # but high enough to block noise-level scores (e.g. 0.05 from a
            # blank or corrupt frame) from replacing the Unknown label with an
            # implausible species.
            _UNKNOWN_UPGRADE_MIN_SCORE = 0.10

            if manual_tagged:
                should_override = True
                override_reason = "manual_tagged"
            elif existing_is_unknown:
                required_score = max(_UNKNOWN_UPGRADE_MIN_SCORE, effective_floor)
                should_override = video_score >= required_score
                override_reason = "existing_unknown"
            else:
                should_override = bool(video_score >= required_score)

            if should_override:
                new_species = rewrite_label(normalize_classifier_label(video_label))
                # Relabel unknown birds consistently
                if hidden_video_label or new_species in settings.classification.unknown_bird_labels:
                    new_species = "Unknown Bird"

                if hidden_video_label and not existing_is_unknown:
                    log.debug(
                        "Video analysis produced noncanonical label; refusing to downgrade known species",
                        event_id=frigate_event,
                        old_species=existing.display_name,
                        video_label=video_label,
                    )
                    return False

                log.info(
                    "Video analysis overriding primary identification",
                    event_id=frigate_event,
                    old_species=existing.display_name,
                    old_score=existing.score,
                    new_species=new_species,
                    new_score=video_score,
                    required_score=required_score,
                    reason=override_reason,
                )

                # Get taxonomy for new label
                taxonomy = await taxonomy_service.get_names(new_species)
                scientific_name = taxonomy.get("scientific_name")
                common_name = taxonomy.get("common_name")
                taxa_id = taxonomy.get("taxa_id")

                if new_species == UNKNOWN_BIRD_DISPLAY_LABEL:
                    scientific_name = None
                    common_name = None
                    taxa_id = None
                else:
                    scientific_name = scientific_name or new_species

                # Determine display name with localized lookup
                localized_name = None
                if taxa_id and settings.notifications.notification_language != "en":
                    try:
                        localized_name = await taxonomy_service.get_localized_common_name(
                            taxa_id, settings.notifications.notification_language
                        )
                    except Exception as exc:
                        log.debug(
                            "Localized display name lookup failed during reclassify", taxa_id=taxa_id, error=str(exc)
                        )

                if new_species == UNKNOWN_BIRD_DISPLAY_LABEL:
                    display_name = UNKNOWN_BIRD_DISPLAY_LABEL
                elif localized_name:
                    display_name = localized_name
                elif settings.classification.display_common_names and common_name:
                    display_name = common_name
                elif not settings.classification.display_common_names and scientific_name:
                    display_name = scientific_name
                else:
                    display_name = new_species

                # Re-evaluate audio confirmation against new species (robustly)
                from app.services.audio.audio_service import audio_service

                if scientific_name:
                    audio_confirmed, audio_species, audio_score = await audio_service.correlate_species(
                        target_time=existing.detection_time,
                        species_name=scientific_name,
                        camera_name=existing.camera_name,
                    )
                else:
                    audio_confirmed, audio_species, audio_score = False, None, None

                shadow = await _catalog_identity_for_refinement(
                    video_model_id, video_index, scientific_name, frigate_event
                )

                primary_updated = await repo.update_primary_classification(
                    frigate_event=frigate_event,
                    display_name=display_name,
                    category_name=new_species,
                    score=video_score,
                    detection_index=video_index,
                    scientific_name=scientific_name,
                    common_name=common_name,
                    taxa_id=taxa_id,
                    audio_confirmed=audio_confirmed,
                    audio_species=audio_species,
                    audio_score=audio_score,
                    manual_override=manual_tagged,
                    species_id=shadow.species_id,
                    model_artifact_id=shadow.model_artifact_id,
                    model_output_index=shadow.model_output_index,
                )
                if not primary_updated:
                    log.info(
                        "Primary refinement skipped because identification became manual",
                        event_id=frigate_event,
                        video_label=new_species,
                    )
                    return False

                # Broadcast the update
                updated = await repo.get_by_frigate_event(frigate_event)
                if updated:
                    # NOTE: same SSE raw-name limitation as the detection broadcast above.
                    public_species = user_facing_species_fields(
                        display_name=updated.display_name,
                        category_name=updated.category_name,
                        scientific_name=updated.scientific_name,
                        common_name=updated.common_name,
                        taxa_id=updated.taxa_id,
                    )
                    await self.broadcaster.broadcast(
                        {
                            "type": "detection_updated",
                            "data": {
                                "frigate_event": frigate_event,
                                "display_name": public_species["display_name"],
                                "category_name": public_species["category_name"],
                                "score": updated.score,
                                "timestamp": serialize_api_datetime(updated.detection_time),
                                "camera": updated.camera_name,
                                "is_hidden": updated.is_hidden,
                                "is_favorite": updated.is_favorite,
                                "manual_tagged": updated.manual_tagged,
                                "audio_confirmed": updated.audio_confirmed,
                                "audio_species": updated.audio_species,
                                "audio_score": updated.audio_score,
                                "scientific_name": public_species["scientific_name"],
                                "common_name": public_species["common_name"],
                                "taxa_id": public_species["taxa_id"],
                                "video_classification_label": updated.video_classification_label,
                                "video_classification_score": updated.video_classification_score,
                                "video_classification_status": updated.video_classification_status,
                                "video_classification_provider": updated.video_classification_provider,
                                "video_classification_backend": updated.video_classification_backend,
                                "video_classification_model_id": updated.video_classification_model_id,
                                "video_classification_input_source": updated.video_classification_input_source,
                                "video_classification_timestamp": serialize_api_datetime(
                                    updated.video_classification_timestamp
                                ),
                            },
                        }
                    )
                return True
            else:
                log.debug(
                    "Video analysis completed but did not override primary ID",
                    event_id=frigate_event,
                    current_score=current_score,
                    required_score=required_score,
                    threshold=threshold,
                    existing_is_unknown=existing_is_unknown,
                    sublabel_disagrees=sublabel_disagrees,
                    sub_label=normalized_sub_label,
                    video_label=normalized_video_label,
                    manual_tagged=manual_tagged,
                    video_score=video_score,
                )
                return False
