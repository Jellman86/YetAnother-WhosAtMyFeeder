- **Home Assistant HACS / Marketplace updates (#1067):** Added the required root
  `hacs.json` manifest (with `render_readme: true`) so HACS and Home Assistant Marketplace
  can install and update the `yawamf` custom integration from release tags, and added a
  deployment-contract test to keep it present and aligned with
  `custom_components/yawamf/manifest.json`.
