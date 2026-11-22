- **Unraid Community Applications template validation:** Removed the stray hardcoded
  `apps/ui/public/sitemap.xml` (and its `robots.txt` / nginx references) that caused
  Unraid Community Applications to report `Template could not be read` when scanning the
  repository's `.xml` files, and added a deployment-contract check so only
  `ca_profile.xml` and `unraid/yawamf.xml` exist as tracked `.xml` files.
