- **Hiding BirdNET-Go calls in Audio History works again (#1075).** Clicking **Hide in YA-WAMF**
  on an audio detection now sends `Content-Type: application/json` on `PATCH /api/audio/history/{id}`,
  fixing the validation error (`Input should be a valid dictionary or object to extract fields from`).
  A unit test now guards every `apiFetch` JSON body across the API client against missing
  `Content-Type` headers.
