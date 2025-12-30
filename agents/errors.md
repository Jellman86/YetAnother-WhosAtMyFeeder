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
- Frigate is still more accurate than our suggestions, please investigate this, when frigate has a bird sublable and we have unknown or background please use the frigate sublabel.
- I manually tagged some birds and then I went back to the live detections tab, the old names were still present with the live detections view. Im assuming we need to refresh data when changing views?

**
