import structlog
import os
import asyncio
import math
from datetime import datetime
from app.config import settings
from app.repositories.detection_repository import DetectionRepository, Detection
from app.services.classifier_service import ClassifierService
from app.services.broadcaster import broadcaster
from app.services.taxonomy.taxonomy_service import taxonomy_service
from app.services.birdweather_service import birdweather_service
from app.utils.frigate import normalize_sub_label
from app.utils.tasks import create_background_task
from app.database import get_db

log = structlog.get_logger()
TAXONOMY_LOOKUP_TIMEOUT_SECONDS = max(
    0.5, float(os.getenv("TAXONOMY_LOOKUP_TIMEOUT_SECONDS", "3"))
)

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

    def filter_and_label(self, classification: dict, frigate_event: str,
                         frigate_sub_label: str = None, frigate_score: float = None) -> tuple[dict | None, str | None]:
        """
        Apply filtering and relabeling rules to a classification result.
        Returns (result_dict, reason_code).
        reason_code is populated when result is None (skip reason) or informative when result exists.
        """
        frigate_sub_label = normalize_sub_label(frigate_sub_label)
        top = classification
        try:
            score = float(top['score'])
        except (KeyError, TypeError, ValueError):
            log.warning("Invalid classification score", event_id=frigate_event, score=top.get("score"))
            return None, "invalid_score"
        if not math.isfinite(score):
            log.warning("Non-finite classification score", event_id=frigate_event, score=score, label=top.get("label"))
            return None, "invalid_score"
        top = {**top, 'score': score}
        label = top['label']
        original_label = label
        normalized_label = str(label or "").strip().casefold()
        normalized_frigate_sub_label = frigate_sub_label.casefold() if frigate_sub_label else None

        # Relabel unknown bird classifications
        if label in settings.classification.unknown_bird_labels:
            log.info("Relabeled to Unknown Bird", original=label, event_id=frigate_event)
            label = "Unknown Bird"
            top = {**top, 'label': label}

        # Filter out blocked labels
        if label in settings.classification.blocked_labels:
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
            frigate_score_value = float(frigate_score or 0.0)
            if frigate_score_value > 0:
                disagreement_min_score = max(
                    disagreement_min_score,
                    min(0.98, frigate_score_value + 0.15),
                )
            required_threshold = max(required_threshold, disagreement_min_score)
            threshold_reason = "threshold_passed_with_sublabel_disagreement_guard"

        below_threshold = score <= required_threshold

        # If classification passes primary threshold, return it
        # (Implicitly passes min_confidence because threshold >= effective_min)
        if not below_threshold:
            return top, threshold_reason

        # Classification failed primary threshold - check if we can fall back to Frigate sublabel
        if settings.classification.trust_frigate_sublabel and frigate_sub_label:
            # Use Frigate score if available, otherwise boost current score to threshold to ensure visibility
            # but usually Frigate score is reliable.
            final_score = frigate_score if (frigate_score and frigate_score > 0) else max(score, settings.classification.threshold)
            
            # Frigate sublabel exists - use it as fallback regardless of confidence
            log.info("Using Frigate sublabel as fallback",
                     frigate_label=frigate_sub_label,
                     yawamf_label=original_label,
                     yawamf_score=score,
                     final_score=final_score,
                     event_id=frigate_event)
            return {
                'label': frigate_sub_label,
                'score': final_score,
                'index': top.get('index', -1),
                'source': 'frigate_fallback'
            }, "frigate_fallback"

        # Check for "Unknown Bird" catch-all (middle ground between min_confidence and threshold)
        if not below_min_confidence:
            log.info("Low confidence detection, saving as Unknown", 
                     original=original_label, 
                     score=score, 
                     required_threshold=required_threshold,
                     sublabel_disagrees=sublabel_disagrees,
                     event_id=frigate_event)
            return {
                'label': "Unknown Bird",
                'score': score,
                'index': top.get('index', -1),
                'source': 'low_confidence_catchall'
            }, "unknown_catchall"

        # No fallback available or below absolute floor
        if below_min_confidence:
            log.debug("Below minimum confidence", score=score, min=effective_min, event_id=frigate_event)
            return None, "low_confidence"
        else:
            # This branch implies (not below_min and below_threshold) which is handled by catch-all above
            # But just in case logic drifts:
            log.debug("Below threshold", score=score, threshold=settings.classification.threshold, event_id=frigate_event)
            return None, "below_threshold"

    async def save_detection(self, frigate_event: str, camera: str, start_time: float, 
                           classification: dict, frigate_score: float = None, sub_label: str = None,
                           audio_confirmed: bool = False, audio_species: str = None, audio_score: float = None,
                           temperature: float = None, weather_condition: str = None,
                           weather_cloud_cover: float = None, weather_wind_speed: float = None,
                           weather_wind_direction: float = None, weather_precipitation: float = None,
                           weather_rain: float = None, weather_snowfall: float = None) -> tuple[bool, bool]:
        """
        Save or update a detection in the database and broadcast the event.
        Returns (changed, was_inserted).
        """
        sub_label = normalize_sub_label(sub_label)

        # 1. Normalize names (Bidirectional Scientific <-> Common)
        label = classification['label']
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
        
        scientific_name = taxonomy.get("scientific_name") or label
        common_name = taxonomy.get("common_name")
        taxa_id = taxonomy.get("taxa_id")

        # 2. Determine display name based on user preference
        display_name = label
        if settings.classification.display_common_names and common_name:
            display_name = common_name
        elif not settings.classification.display_common_names and scientific_name:
            display_name = scientific_name

        async with get_db() as db:
            repo = DetectionRepository(db)

            score = float(classification['score'])
            if not math.isfinite(score):
                log.warning("Refusing to save detection with non-finite score", event_id=frigate_event, score=score)
                return False, False
            category_name = classification['label']
            timestamp = datetime.fromtimestamp(start_time)

            detection = Detection(
                detection_time=timestamp,
                detection_index=classification['index'],
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
                taxa_id=taxa_id
            )

            # Atomic upsert: insert or update only if score is higher
            was_inserted, was_updated = await repo.upsert_if_higher_score(detection)
            changed = was_inserted or was_updated

            if changed:
                persisted = await repo.get_by_frigate_event(frigate_event)
                log.info("Saved detection", 
                         event_id=frigate_event, 
                         species=display_name, 
                         scientific=scientific_name,
                         score=score,
                         frigate_score=frigate_score,
                         audio_confirmed=audio_confirmed,
                         weather=weather_condition)

                # Broadcast event only when actually saved/updated
                await self.broadcaster.broadcast({
                    "type": "detection",
                    "data": {
                        "frigate_event": frigate_event,
                        "display_name": display_name,
                        "scientific_name": scientific_name,
                        "common_name": common_name,
                        "taxa_id": taxa_id,
                        "score": score,
                        "timestamp": timestamp.isoformat(),
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
                        "weather_snowfall": weather_snowfall
                    }
                })

                # 3. Report to BirdWeather (if enabled)
                if scientific_name and scientific_name != "Unknown Bird":
                    # Run in background to not block the main loop
                    create_background_task(
                        birdweather_service.report_detection(
                            scientific_name=scientific_name,
                            common_name=common_name,
                            confidence=score,
                            timestamp=timestamp
                        ),
                        name=f"birdweather_report:{frigate_event}"
                    )
            
            return changed, was_inserted

    async def get_detection_by_frigate_event(self, frigate_event: str) -> Detection | None:
        """Fetch a detection by Frigate event ID."""
        async with get_db() as db:
            repo = DetectionRepository(db)
            return await repo.get_by_frigate_event(frigate_event)

    async def apply_video_result(self, frigate_event: str, video_label: str, video_score: float, video_index: int, manual_tagged: bool = False):
        """
        Process and save results from background video analysis.

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

            # 1. Update video-specific columns first
            await repo.update_video_classification(
                frigate_event=frigate_event,
                label=video_label,
                score=video_score,
                index=video_index,
                status='completed'
            )

            # 2. Only promote video results when they are trustworthy enough, but
            # always allow explicit/manual reclassifications and unknown-bird upgrades.
            unknown_labels = {
                *(label.lower() for label in settings.classification.unknown_bird_labels),
                "unknown bird",
            }
            existing_labels = {
                str(getattr(existing, "display_name", "") or "").lower(),
                str(getattr(existing, "category_name", "") or "").lower(),
            }
            existing_is_unknown = any(label in unknown_labels for label in existing_labels if label)
            current_score = float(existing.score or 0.0)
            threshold = float(settings.classification.threshold or 0.0)
            base_required_score = max(current_score, threshold)

            normalized_video_label = str(video_label or "").strip().casefold()
            normalized_sub_label = normalize_sub_label(getattr(existing, "sub_label", None))
            normalized_sub_label = normalized_sub_label.casefold() if normalized_sub_label else None
            sublabel_disagrees = bool(
                normalized_sub_label
                and normalized_video_label
                and normalized_sub_label != normalized_video_label
            )

            required_score = base_required_score
            override_reason = "score_gate_passed"
            if sublabel_disagrees:
                frigate_score = float(getattr(existing, "frigate_score", 0.0) or 0.0)
                disagreement_min_score = min(0.95, threshold + 0.20)
                if frigate_score > 0:
                    disagreement_min_score = max(
                        disagreement_min_score,
                        min(0.98, frigate_score + 0.15)
                    )
                required_score = max(required_score, disagreement_min_score)
                override_reason = "score_gate_passed_with_sublabel_disagreement"

            if manual_tagged:
                should_override = True
                override_reason = "manual_tagged"
            elif existing_is_unknown:
                should_override = True
                override_reason = "existing_unknown"
            else:
                should_override = bool(video_score >= required_score)

            if should_override:
                new_species = video_label
                # Relabel unknown birds consistently
                if new_species in settings.classification.unknown_bird_labels:
                    new_species = "Unknown Bird"

                log.info("Video analysis overriding primary identification", 
                         event_id=frigate_event, 
                         old_species=existing.display_name, 
                         old_score=existing.score,
                         new_species=new_species, 
                         new_score=video_score,
                         required_score=required_score,
                         reason=override_reason)

                # Get taxonomy for new label
                taxonomy = await taxonomy_service.get_names(new_species)
                scientific_name = taxonomy.get("scientific_name") or new_species
                common_name = taxonomy.get("common_name")
                taxa_id = taxonomy.get("taxa_id")

                display_name = new_species
                if settings.classification.display_common_names and common_name:
                    display_name = common_name
                elif not settings.classification.display_common_names and scientific_name:
                    display_name = scientific_name

                # Re-evaluate audio confirmation against new species (robustly)
                from app.services.audio.audio_service import audio_service
                audio_confirmed, audio_species, audio_score = await audio_service.correlate_species(
                    target_time=existing.detection_time,
                    species_name=scientific_name,
                    camera_name=existing.camera_name
                )

                # Update primary fields
                await db.execute("""
                    UPDATE detections
                    SET display_name = ?,
                        category_name = ?,
                        score = ?,
                        detection_index = ?,
                        scientific_name = ?,
                        common_name = ?,
                        taxa_id = ?,
                        audio_confirmed = ?,
                        audio_species = ?,
                        audio_score = ?,
                        manual_tagged = CASE WHEN ? = 1 THEN 1 ELSE manual_tagged END
                    WHERE frigate_event = ?
                """, (
                    display_name,
                    new_species,
                    video_score,
                    video_index,
                    scientific_name,
                    common_name,
                    taxa_id,
                    1 if audio_confirmed else 0,
                    audio_species,
                    audio_score,
                    1 if manual_tagged else 0,
                    frigate_event
                ))
                await db.commit()

                # Broadcast the update
                updated = await repo.get_by_frigate_event(frigate_event)
                if updated:
                    await self.broadcaster.broadcast({
                        "type": "detection_updated",
                        "data": {
                            "frigate_event": frigate_event,
                            "display_name": updated.display_name,
                            "score": updated.score,
                            "timestamp": updated.detection_time.isoformat(),
                            "camera": updated.camera_name,
                            "is_hidden": updated.is_hidden,
                            "is_favorite": updated.is_favorite,
                            "manual_tagged": updated.manual_tagged,
                            "audio_confirmed": updated.audio_confirmed,
                            "audio_species": updated.audio_species,
                            "audio_score": updated.audio_score,
                            "scientific_name": updated.scientific_name,
                            "common_name": updated.common_name,
                            "taxa_id": updated.taxa_id,
                            "video_classification_label": updated.video_classification_label,
                            "video_classification_score": updated.video_classification_score,
                            "video_classification_status": updated.video_classification_status,
                            "video_classification_timestamp": updated.video_classification_timestamp.isoformat() if updated.video_classification_timestamp else None
                        }
                    })
            else:
                log.debug("Video analysis completed but did not override primary ID", 
                          event_id=frigate_event, 
                          current_score=current_score,
                          required_score=required_score,
                          threshold=threshold,
                          existing_is_unknown=existing_is_unknown,
                          sublabel_disagrees=sublabel_disagrees,
                          sub_label=normalized_sub_label,
                          video_label=normalized_video_label,
                          manual_tagged=manual_tagged,
                          video_score=video_score)
