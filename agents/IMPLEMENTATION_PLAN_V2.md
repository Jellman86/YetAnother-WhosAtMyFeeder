# Implementation Plan: Audio & Context Intelligence

## Phase 1: Dynamic Model Market (Completed)
- [x] **Model Manager Service**: Created backend service to manage TFLite models.
- [x] **API Endpoints**: Added endpoints to list, download, and activate models.
- [x] **Dynamic Loading**: Refactored `ClassifierService` to load the active model from persistent storage.
- [x] **UI**: Implemented "Model Manager" in Settings to browse and install models (MobileNet, EfficientNet, etc.).

## Phase 2: Audio Integration (In Progress)
**Goal**: Integrate BirdNET-Go to correlate visual detections with audio confirmation.

### 1. Infrastructure (Done)
- [x] Add `birdnet-go` to `docker-compose.yml` (commented out for user to enable).
- [x] Create `AudioService` to buffer and search audio detections.
- [x] Update Database Schema: Added `audio_confirmed`, `audio_species`, `audio_score` columns.
- [x] Update Data Models: Updated `Detection` dataclass and Pydantic models.

### 2. Ingestion & Correlation (Next Steps)
- [ ] **MQTT Routing**: Update `MQTTService` to subscribe to BirdNET topics (e.g., `birdnet/text` or `birdnet/json`).
- [ ] **Audio Ingestion**: Wire `MQTTService` to pass audio payloads to `AudioService.add_detection()`.
- [ ] **Correlation Logic**:
    - Modify `EventProcessor.process_mqtt_message`.
    - Before saving a visual detection, call `audio_service.find_match(timestamp)`.
    - If match found:
        - If Visual = "Unknown" & Audio = High Confidence Species → **Override Visual Label**.
        - If Visual = Species A & Audio = Species A → **Boost Confidence / Mark Confirmed**.
        - Log correlation in `audio_*` database fields.

### 3. User Interface
- [ ] **Detection Card**: Add an icon (e.g., microphone or music note) to detections that are audio-confirmed.
- [ ] **Details Modal**: Show "Audio Species" and "Audio Score" if available.

## Phase 3: Contextual Intelligence (Future)
**Goal**: Add environmental data and LLM-based descriptions.

### 1. Weather Integration
- [ ] Service to fetch local weather (OpenMeteo) based on IP/Location.
- [ ] Store `temperature`, `condition` (Rain/Sun) with detection.
- [ ] UI: Show weather icon next to timestamp.

### 2. LLM "Naturalist"
- [ ] Add "Ask AI" button to detection details.
- [ ] Send crop image + metadata (species, confidence, time, weather) to LLM (Gemini/OpenAI).
- [ ] Prompt: "Describe the bird's behavior and appearance."
- [ ] Display response in UI.
