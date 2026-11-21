# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Add GitHub Actions CI with ruff, black and pytest
- Add pydantic models and JSON/CSV loaders for transcript and chat
- Add chat-peak candidate generator with reaction points (D10)
- Add LLM judge behind a Judge interface, with Gemini free tier as first provider (D12)
- Add end-to-end CLI and evaluation against hand-provided Twitch clips
- Record the real-VOD acceptance run in the phase 4 session note (0 candidates, 0/10)
- Record an open proposal to review the chat-peak detector after the real-VOD run
- Record decision D15 for the phase 5 detector revision and narrow the open proposal
- Update PROGRESS to open v1 with the detector decided in D15 and phase 5 next
- Record decision D16 for judge pacing and retries against provider limits
- Add a rule banning local-tool prefixes and markers from project artifacts
- Record decision D17 for the activity floor of the mean baseline fallback
- Add sliding-window top-K peak detector and judge-free evaluation harness (D15)
- Add 12 s call pacing and transient-error retries to the Gemini judge (D16)

### Changed

- Resolve SPEC open questions and record decision D5
- Rename MERGE_GAP_S to MIN_PEAK_SEPARATION_S, with no change in behaviour
