# Pi-Safe Skill Catalog

Curated allowlist of ClawHub skills vetted to install and run on a Raspberry Pi
Zero 2W (512 MB RAM, ARM). `search_skills` greps the `- **name**` lines below.

**Only add a skill here after confirming its install is Pi-light.** The verdict
is mostly about the install method (see table), not the skill itself.

| install kind | verdict |
|---|---|
| `apt` / prebuilt static ARM binary | ✅ safe |
| `pip` (pure-python, few deps) | ⚠️ usually ok |
| `go install …@latest` | ⚠️ compiles on device — slow, can OOM |
| `cargo` / Rust build | ❌ banned (will crash the Zero) |
| `brew` | ❌ Linux has no brew |
| `npm` / node | ❌ footprint too large |

Line format (one bullet per skill — keep it greppable):
`- **name** emoji — one-line description. [bins: x] install: <command or note> <verdict>`

## Skills

- **alexa-cli** 🔊 — Control Amazon Alexa/Echo devices and smart home. [bins: alexacli] install: `go install github.com/buddyh/alexa-cli/cmd/alexa@latest` ⚠️ go-compile on device; prefer a prebuilt ARM binary synced via `sync_skills.sh`
