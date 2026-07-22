# BirdWeather Integration

YA-WAMF allows you to contribute your bird sightings to the [BirdWeather](https://www.birdweather.com/) community science project.

## How it works
Every time a bird is identified with a specific species (i.e., not "Unknown Bird"), YA-WAMF will automatically upload the detection to your BirdWeather station if configured.

## Setup
1. Log in to your BirdWeather account.
2. Find your **Station Token** in your station settings.
3. In YA-WAMF, go to **Settings > Integrations**.
4. Enable **BirdWeather** and paste your token.
5. Click **Apply Settings**.

## Testing
Click **Test connection** in the BirdWeather settings section. This sends a mock
"House Sparrow" detection to your station. A token already saved by YA-WAMF can be
tested without entering it again; typing a replacement tests the value currently in
the form. The staged dialog reports the real provider response and keeps failures
visible until you close or retry it.
