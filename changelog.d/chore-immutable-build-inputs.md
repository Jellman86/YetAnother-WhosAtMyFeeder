- Image builds and checks use the exact Action revisions from verified successful runs, with
  a CI policy that rejects moving references. Dependency automation can still propose updates.
- Local environment files stay out of image build contexts, and the standalone frontend uses
  the committed dependency lockfile for strict installation.
