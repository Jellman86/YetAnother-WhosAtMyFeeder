# Writing a YA-WAMF release

Release notes should help someone answer three questions quickly:

1. What will I notice at my feeder?
2. Is the update safer or easier for me?
3. Do I need to do anything before or after updating?

They are not a dump of commits. `CHANGELOG.md` remains the complete technical
record; the GitHub Release is the clear, human introduction to it.

## Start with evidence

Write from the versioned changelog and the checks completed for the exact tag.
Every claim must describe behaviour that is present in the released image. Do not
turn roadmap work, an open pull request, or an unverified host test into a release
promise.

Before writing, collect:

- the previous and new tags;
- the matching `CHANGELOG.md` section;
- the green tag build, test, migration checks, container build, and image publication;
- any migration, configuration, downtime, hardware, model, or compatibility action;
- any privacy, retention, or public-access boundary affected by the release.

## Write for the update decision

Start from [the release-notes template](../../.github/RELEASE_NOTES_TEMPLATE.md).
Delete its comments and any section that has nothing useful to say.

Choose three to six changes a person will actually notice. Lead with the outcome:

> **Cleaner species names as detections arrive.** YA-WAMF now normalises model
> labels before they reach your history, so taxonomy-style paths no longer appear
> in detection cards or notifications.

Avoid leading with the implementation:

> Refactored taxonomy normalisation in the classifier pipeline.

The implementation belongs in the changelog. Release notes should still be
specific—“faster classification” is not useful unless they say where it is
faster, on which hardware, and whether accuracy or power use changes.

## Voice and structure

- Use a warm, calm tone. Write to `you`, not to “users”.
- Prefer short sentences and one idea per bullet.
- Use exact UI labels and familiar feeder, camera, and species language.
- Put the benefit in bold at the start of each bullet.
- Explain model, hardware, privacy, and retention limits honestly.
- Put required action under **Before you update**, where it cannot be missed.
- Say **No special steps** when a normal image update is genuinely sufficient.
- Avoid hype such as “massive”, “game-changing”, and “best ever”.
- Avoid “we”; name YA-WAMF or speak directly to `you`.

## Publish checklist

- [ ] The release title and tag match the application version.
- [ ] The exact tag's CI, migration checks, image build, and publication are green.
- [ ] Every statement is supported by shipped code, tests, or verified operation.
- [ ] The opening summary makes sense without reading the changelog.
- [ ] Bullets describe feeder-owner outcomes rather than internal components.
- [ ] **Before you update** states every required action—or says none is needed.
- [ ] Defaults, opt-in features, model/hardware limits, privacy, and retention are honest.
- [ ] No token, private hostname, camera URL, location, or other secret appears.
- [ ] The full changelog link points at the released tag.
- [ ] Empty template sections and all HTML comments are removed.
- [ ] The rendered GitHub preview has been read from top to bottom.

