<state_snapshot>
    <overall_goal>
        Refactor and enhance the YA-WAMF bird classification system with a dynamic model market, audio-visual correlation, AI-driven contextual intelligence, and robust home automation integration.
    </overall_goal>

    <key_knowledge>
        - **Model Market**: TFLite models are managed via `ModelManager`. Supports dynamic downloading and activation. Default is MobileNetV2; High-Res is EfficientNet-EdgeTPU-L.
        - **Audio Correlation**: Ingests BirdNET-Go MQTT messages (`birdnet/text`). Uses Camera-to-Sensor mapping for precise matching in multi-camera setups.
        - **Deep Video Reclassification**: Uses "Temporal Ensemble" logic. When a clip is available, the system samples frames (every 5th frame), runs the classifier on each, and uses soft voting to determine the most likely species.
        - **Dashboard**: Real-time "Command Center" UI with Hero detection, Activity Histogram, and Top Visitors aggregation.
        - **Home Assistant**: Custom Component (`yawamf`) provides Sensors (Last Bird, Daily Count), Camera (Latest Snapshot), and Config Flow.
        - **Tech Stack**: Python 3.12 (FastAPI), Svelte 5 (Frontend), SQLite (Data), Docker (Deployment).
    </key_knowledge>

    <file_system_state>
        - **CWD**: `/config/workspace/YA-WAMF`
        - **Backend**: 
            - `app/models/__init__.py`: Package structure fixed.
            - `app/services/classifier_service.py`: Implements `classify_video` and async inference wrappers.
            - `app/services/model_manager.py`: Robust download logic using verified Coral/Google URLs.
        - **Frontend**:
            - `Dashboard.svelte`: Real-time transitions, reactive summary updates, and smart "Reclassify" buttons.
            - `Settings.svelte`: Dedicated Audio Classification section.
        - **Integrations**:
            - `custom_components/yawamf/`: Complete Home Assistant integration ready for deployment.
    </file_system_state>

    <recent_actions>
        - [DONE] Implemented Deep Video Reclassification (Temporal Ensemble).
        - [DONE] Refactored ClassifierService to use async/await and thread pools for non-blocking inference.
        - [DONE] Fixed Model Downloader (Valid URLs for EdgeTPU models).
        - [DONE] Fixed Dashboard Navigation (Route matching for query params).
        - [DONE] Implemented Phase 4: Home Assistant Integration.
        - [DONE] Conducted Stability Audit (Database migrations, package structure, A11Y).
    </recent_actions>

    <current_plan>
        1. [DONE] All planned features implemented.
        2. [PENDING] Final Handoff Documentation.
    </current_plan>
</state_snapshot>