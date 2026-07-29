# Changelog

This file records user-visible project changes. The audited repository history
contains no release tag, so no historical version is presented as a published
release.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version links and release dates will be added only for an actual release.

## Unreleased

### Added

- Closed-state contribution and governance policies that do not invite
  unlicensed external contributions.
- A license decision matrix and a factual public-release checklist.
- A release process with fail-closed legal, evidence, security, and artifact
  gates.
- GitHub issue forms for bugs, feature requests, and compatibility evidence,
  plus a pull-request review template.
- Citation metadata for the repository's current development state.
- An exact, versioned release-file allowlist and CI audit for Python source
  distributions and wheels.
- Public package metadata for repository, documentation, and issue links,
  plus EDA-focused classifiers without a premature license classifier.

### Clarified

- The absence of a project-wide `LICENSE` is a release blocker.
- The repository must not be described as open source until an accountable
  owner selects and commits an OSI-approved license.
- No community size, adoption, sponsorship, vendor endorsement, signed binary,
  package-index release, or support-program acceptance is asserted.
- Python wheels intentionally contain the MCP server and eight packaged
  skills, while Windows bridge installation scripts and settings remain
  separate source/release assets.

`pyproject.toml` contains development version `0.1.0`. That value is not a
published release without an approved tag, artifacts, and provenance record.
