## Resolved Issues
- **Dating for detections is incorrect**:
  - **Resolution**: Fixed by ensuring consistent timestamp formatting (`isoformat(sep=' ')`) in SQLite queries. The issue was caused by a mismatch between space-separated timestamps in the DB and 'T'-separated timestamps in queries.
- **Frigate sublabels and metadata usage**:
  - **Resolution**: Added `frigate_score` and `sub_label` columns to the database. Updated `EventProcessor` to capture this data from MQTT events and persist it.
- **Difference between system detections and Frigate detections**:
  - **Resolution**: Clarified the distinction by storing and displaying the Frigate detection score separately. The UI now shows the Frigate score ("F: XX%") alongside the YA-WAMF classification score, making it clear that one is object detection confidence and the other is species classification confidence.

## Historical Issues (Closed)
- dating for detections is incorrect, im seeing this a couple of ways, the amounts of detections for today is zero but i can clearly see the timestamp in the snapshot shows today. I also know the detection was today. It seems that this logic is incorrect.
- Please assess weather the system is actually using the frigate sublables and meta information from frigate.
- Why are the detections from this system different to the detections from frigate? I can see that the bounding box match persentage is different to the detection percentage in the application.

## Errors Seen By Scott (not resolved):
- I manually tagged some birds and then I went back to the live detections tab, the old names were still present with the live detections view. Im assuming we need to refresh data when changing views?

## Fix Implemented: Trust Frigate Sublabel Fallback (Jan 2, 2026)

**Issue**: Frigate is more accurate than YA-WAMF classification. When Frigate has identified a bird (via sublabel like "Eurasian Blue Tit"), but YA-WAMF's classifier returns low confidence, the detection is discarded entirely.

**Example from logs (Jan 2, 2026)**:
```
Event 1767359126.280292-ck2qum:
- Frigate sublabel: "Eurasian Blue Tit" (from Frigate+ or manual tag)
- YA-WAMF classification: "background" → relabeled to "Unknown Bird"
- YA-WAMF score: 51.6% (below 60% threshold)
- Result: SKIPPED - detection not saved
```

**Root Cause**: `detection_service.py:filter_and_label()` only considers YA-WAMF classification score. It ignores the Frigate sublabel passed later to `save_detection()`.

**Proposed Fix**:

### 1. Add config option (`backend/app/config.py`)
```python
class ClassificationSettings(BaseModel):
    # ... existing fields ...
    trust_frigate_sublabel: bool = True  # Fall back to Frigate sublabel when YA-WAMF fails
```

### 2. Modify `filter_and_label()` signature (`backend/app/services/detection_service.py`)
```python
def filter_and_label(self, classification: dict, frigate_event: str,
                     frigate_sub_label: str = None) -> dict | None:
```

### 3. Add fallback logic in `filter_and_label()`
After the threshold checks fail, before returning None:
```python
# If YA-WAMF classification fails but Frigate has a sublabel, use it
if settings.classification.trust_frigate_sublabel and frigate_sub_label:
    # Frigate sublabel is a species name (not just "bird")
    log.info("Using Frigate sublabel as fallback",
             frigate_label=frigate_sub_label,
             yawamf_label=label,
             yawamf_score=score,
             event_id=frigate_event)
    return {
        'label': frigate_sub_label,
        'score': 0.0,  # Mark as Frigate-sourced (score=0 indicates fallback)
        'index': -1,   # No YA-WAMF model index
        'source': 'frigate'  # Track source for UI display
    }
```

### 4. Update callers to pass sublabel

**event_processor.py** (`process_mqtt_message`):
```python
# Before:
top = self.detection_service.filter_and_label(results[0], frigate_event)

# After:
sub_label = after.get('sub_label')
top = self.detection_service.filter_and_label(results[0], frigate_event, sub_label)
```

**backfill_service.py** (`process_historical_event`):
```python
# Before:
top = self.detection_service.filter_and_label(results[0], frigate_event)

# After:
sub_label = event.get('sub_label')
top = self.detection_service.filter_and_label(results[0], frigate_event, sub_label)
```

### 5. UI consideration
Detections with `source: 'frigate'` or `score: 0` could display differently:
- Show "ID by Frigate" badge instead of confidence percentage
- Or show "F: Eurasian Blue Tit" to indicate Frigate source

### Files to modify:
1. `backend/app/config.py` - Add `trust_frigate_sublabel` setting
2. `backend/app/services/detection_service.py` - Add fallback logic
3. `backend/app/services/event_processor.py` - Pass sublabel to filter_and_label
4. `backend/app/services/backfill_service.py` - Pass sublabel to filter_and_label

**
