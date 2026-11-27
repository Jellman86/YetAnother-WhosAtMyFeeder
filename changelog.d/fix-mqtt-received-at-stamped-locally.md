- A Frigate MQTT message can no longer set the time YA-WAMF records for its arrival.
  YA-WAMF always stamps that time itself, so a message on the broker can't make a bird
  event look too old to identify live, or keep one looking fresh past the live deadline.
