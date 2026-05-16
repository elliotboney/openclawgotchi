## Release Overview

This release covers the period from the first Obsidian/Vault integration on **May 5, 2026** through the current `main` state on **May 9, 2026**.

Post-release updates through **May 16, 2026** added a few focused improvements without changing the overall release theme:
- text-based PDF ingestion for Telegram documents
- stronger vault recall / retrieval before answering
- a conservative `dreaming` step before heartbeat to catch missed durable knowledge without doing aggressive vault rewrites

It turns OpenClawGotchi into a much more capable capture-and-automation bot: better knowledge capture into an Obsidian-compatible vault, voice and image understanding through OpenAI, optional Discord inbound support, improved setup/runtime docs, and optional UPS battery monitoring for Raspberry Pi builds.

Full changelog: [CHANGELOG.md](https://github.com/turmyshevd/openclawgotchi/blob/main/CHANGELOG.md)

## Highlights

### 1. Obsidian-compatible knowledge capture
The vault system was upgraded to support Obsidian-style note capture and organization.

What changed:
- added Obsidian-oriented vault support and project structure cleanup
- improved note structure for better compatibility with Obsidian workflows
- switched new vault notes to human-readable filenames instead of timestamp-heavy noise
- improved attachment naming so image captures are easier to browse
- cleaned up `INDEX.md` behavior so it no longer acts as a noisy graph hub
- removed fake fallback links like `topics/inbox` that created broken or misleading graph relationships

Result:
- better graph readability in Obsidian
- more human-friendly note and attachment names
- cleaner long-term knowledge organization

### 1b. Vault recall and conservative memory maintenance
After the original vault rollout, the memory layer was tightened in two pragmatic ways.

What changed:
- the bot now pulls relevant facts and vault snippets into the prompt before answering
- retrieval is no longer exact-substring only; it now uses lightweight token scoring
- heartbeat now runs a narrow `dreaming` pass that reviews only messages since the last run
- dreaming can capture a very small number of clearly missing notes and log integrity warnings, but does not rename, merge, or mass-rewrite vault content

Result:
- better chance of recalling previously saved testing, project, and strategy notes during normal chat
- safer autonomous upkeep without letting the bot obsessively refactor the vault

### 2. Voice transcription with OpenAI Whisper
Telegram voice handling was added through OpenAI Whisper.

What changed:
- Telegram voice messages can now be transcribed
- voice transcription is integrated into the normal bot interaction flow
- runtime and setup docs were updated to reflect the new media requirements

Result:
- the bot can now be used more naturally from mobile without typing
- voice input becomes part of the same capture / reasoning flow as text

### 3. Image understanding with OpenAI Vision
The bot now supports image analysis for Telegram photos and image documents.

What changed:
- Telegram photos and image documents are analyzed via OpenAI Vision
- image output is routed directly through the OpenAI media path instead of the generic LiteLLM multimodal path
- image capture now preserves visible text more faithfully, including OCR-like extraction and structured output for text-heavy screenshots and tables
- image attachments are saved to the vault with readable names derived from the content instead of temp filenames

Result:
- screenshots, diagrams, and text-heavy images are much more useful as captured knowledge
- image-driven vault entries are cleaner and easier to browse later

### 3b. Text PDF ingestion
The document pipeline now supports text-based PDFs in Telegram.

What changed:
- `.pdf` / `application/pdf` documents are accepted in the same inline reading flow as other text documents
- extracted text is passed into the normal reasoning path
- scanned/image-only PDFs are detected and reported instead of being treated as empty text

Result:
- reports, research notes, and exported docs can be ingested directly from Telegram without manual copy-paste

### 4. Optional Discord inbound support
OpenClawGotchi can now run with an optional Discord inbound adapter alongside Telegram.

What changed:
- added Discord inbound support for text messages
- added Discord attachment handling for audio and images
- documented the transport model more clearly: Telegram remains primary, Discord is optional

Result:
- the bot is no longer Telegram-only for inbound interaction
- Discord users can interact with the same bot without a separate code path for core reasoning

### 5. Twitter/X writing skill
A dedicated Twitter writing skill was added.

What changed:
- introduced a `twitter-writer` skill
- the bot now produces **3 alternative tweet/X post drafts by default**
- output is formatted for quick selection and reuse

Result:
- easier social/media drafting directly from chat
- more consistent short-form writing behavior

### 6. Raspberry Pi battery monitoring
Optional UPS HAT battery support was added for Pi builds.

What changed:
- added UPS HAT (C) monitoring
- added `/battery` command
- integrated battery status into system stats
- added compact battery display in the E-Ink UI header

Result:
- portable Pi builds now expose battery state directly through the bot and UI
- hardware status is more visible without extra manual checks

## Operational and Setup Improvements

This release also tightened the install/runtime experience.

What changed:
- `setup.sh` now installs from `requirements.txt`
- setup/docs now describe optional OpenAI and Discord configuration more clearly
- Syncthing `/syncvault` support was made configurable via environment variables
- hardcoded Syncthing credentials were removed
- `.env.example`, `README.md`, and bot instructions were updated to match the current runtime model

Result:
- easier setup for new users
- fewer hidden assumptions in the runtime environment
- safer default configuration handling

## Documentation and Maintainer Workflow

The docs were updated to better match the real system behavior.

What changed:
- updated contributor guidance around PR scope and branch drift
- clarified that large stale branches may be manually integrated instead of merged directly
- removed misleading “hard safety guarantee” language from README
- replaced it with more honest guidance about secrets, external model calls, and local automation risk

Result:
- clearer expectations for contributors
- more accurate security and operations documentation
- less confusion around what the bot can and cannot guarantee

## Contributor Credit

This release also includes work that originated from external PRs by [@Smilez1985](https://github.com/Smilez1985).

Included or adapted from contributor work:
- the `auto_mood` footer cleanup, removing duplicated live metrics from the E-Ink status text
- the UPS HAT battery monitoring direction, which was integrated into a fresh branch based on current `main`
- maintainer workflow improvements that came out of reviewing stale or overlapping PRs and tightening contribution rules

Some of these changes were merged directly, while others were manually integrated or refreshed on top of the current codebase to avoid stale branch history and release conflicts.

## Summary

From May 5 to May 9, this release expands OpenClawGotchi in three major directions:

- better **knowledge capture** into an Obsidian-friendly vault
- better **media understanding** through voice and image support
- better **runtime flexibility** through Discord inbound support, optional battery monitoring, and cleaner setup/docs

If you want the short version: this is the release where OpenClawGotchi becomes much better at capturing, understanding, and organizing real-world input across text, voice, screenshots, and portable Pi usage.
