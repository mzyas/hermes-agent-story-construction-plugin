# Hermes Story Construction Plugin

This unified plugin provides the backend and native Desktop halves of the story
construction workspace. The Desktop half contributes a project-first page in
the left navigation: it creates and selects projects, lists only the selected
project's writing sessions, opens chapters in the editor, and keeps manual
focused-session binding as a secondary action. Renderer code never scans or
writes the Vault.

## Install and configure

The plugin installs as a Git repository subdirectory into two places: the
default home hosts the Dashboard API half, and each writing Profile hosts its
Agent half. Both installs are full copies of the same subdirectory, because each
half needs the `story_construction_plugin/` package: the Dashboard API loads it
from the default home as its backend library, and the Gateway loads it from the
Profile to register the Story tools. If the writing Profile is `default`, one
install serves both halves. The Git installer must support subdirectory
installs.

```text
hermes -p default plugins install <owner>/hermes-agent-story-construction-plugin/story-construction-plugin --enable
hermes -p writer plugins install <owner>/hermes-agent-story-construction-plugin/story-construction-plugin --enable
```

The two copies must be identical. Selecting or resolving a writing Profile is
rejected with `version_mismatch` when the two `plugin.yaml` versions differ, or
when the package sources differ: a SHA-256 over the paths and contents of
`story_construction_plugin/**/*.py` and `story_construction_plugin/skills/**/SKILL.md`
(`__pycache__` and CRLF versus LF line endings are ignored). Other files, such
as `dashboard/` and `desktop/`, are not part of that comparison. A copy whose
`story_construction_plugin/` folder is missing, empty, or unreadable is rejected
with `agent_not_installed`; two missing copies never count as identical. The
digest is cached per copy and recomputed only when a file's size or
modification time changes.

This check compares the copies **on disk**. It does not prove that the running
Dashboard or Gateway executes that code: both load the package once, so after
an update they keep running the old code until they are restarted (see below).

#### Updating the plugin

Update both copies every time, then restart the Dashboard:

1. Update the default home copy: `hermes -p default plugins update story-construction`
   (or reinstall it with the command above).
2. Update each writing Profile copy the same way, with `-p <profile>`.
3. Restart the Dashboard. Hermes mounts the Dashboard API only at startup, so a
   running Dashboard keeps serving the old code and a frontend retry cannot pick
   up the new one.
4. Start a new chat session so the Agent registers the updated tools.

`hermes plugins update` exists in the Hermes CLI, but it has not been run against
a subdirectory install of this plugin; if it fails or reports nothing to update,
reinstall with the install command instead.

Updating only one copy makes the next status call return `version_mismatch`
until the other one is brought up to the same code. The reverse is not true: a
passing check after updating both copies does not mean the running Dashboard
already uses the new code, so the restart in step 3 is still required. Check the installed version
in `plugin.yaml` if you are unsure which copy is behind.

The shared Vault path must be a path that the backend process can read and
write, for the operating system that backend runs on. It can be changed later by submitting a new `vault_root` to
`PUT /settings` (Desktop: "Change Vault path" in the project library); the new
path replaces the old one and existing session-to-project bindings are cleared,
because they refer to projects of the previous Vault. The first Dashboard API mount and the first Agent tool
registration may need the normal dashboard reload or a new chat session to pick
up the plugin; switching between already prepared Profiles does not.

#### Windows and WSL Vault paths

Windows and WSL each have their own Hermes home and `config.yaml`, so a backend
stores the Vault path in its own native spelling. A drive path written by the
other side is translated when it is read: on Windows `/mnt/e/Vault` is opened as
`E:/Vault`, and in WSL `E:/Vault` or `E:\Vault` is opened as `/mnt/e/Vault`. This
covers drive-letter paths only; UNC paths such as `\\wsl.localhost\...` are not
translated. `locked_hermes_home` is deliberately not translated, so a home
written by the other side is still rejected with `hermes_home_mismatch`.

Limits of the translation:

- Only absolute drive paths (`E:`, `E:/...`, `E:\...`) are translated. A
  drive-relative path such as `E:Vault` is left unchanged and is not a usable
  Vault path in WSL; always write the Vault path with a slash after the colon.
- WSL drives are assumed to be mounted under `/mnt/<letter>`. A custom
  `automount.root` in `/etc/wsl.conf` (for example drives under `/`) is not
  recognised.
- The saved path is the resolved path. On Windows, resolving a mapped network
  drive yields its UNC form (`\\server\share\...`) and a `subst` drive yields
  its target drive, so the stored value may not be a drive-letter path that
  the other side can translate. Re-enter the Vault path with `PUT /settings`
  after moving sides in that case.

Locks: `sessions.json` keeps its file lock because the Dashboard API and the
Gateway are separate processes on one home. The Vault has no file lock. A lock
taken on Windows and one taken in WSL do not see each other on a shared drive,
so the Vault relies on atomic `os.replace` writes and version-checked saves
(`SaveConflict`).

Install and run exactly one backend. Do not install or enable this plugin in both
Windows and WSL, and never let two backends write the same Vault: the Vault has
no cross-system lock, so concurrent writes from both sides are unsupported and
may lose data. If you move to the other side, remove or disable the plugin on
the old side first, then run `PUT /settings` on the new one. The path
translation above exists so a single backend can accept a path typed in the
other spelling, not to support two backends at once.

Verification status:

- Verified: the `/mnt/e/...` to `E:/...` and native-path cases in `tests/test_paths.py`,
  and the full suite (197 passed, 1 skipped) on Windows, including the code-drift
  check between the two installed copies (setup and per-request paths, missing
  and unreadable packages, digest caching) and a `/mnt/<drive>/...` Vault path
  stored in config being accepted by `resolve_story_target` and the runtime.
- Not yet verified: the Windows-to-WSL translation test is skipped on Windows and
  has not run in WSL; a Vault reached through `\\wsl.localhost\...`. Two backends
  writing one Vault is prohibited, so it is not a case to verify.

### Story setup and status API

Setup goes through the Dashboard API under `/api/plugins/story-construction/`:

```text
PUT  /settings                                      select Profile and shared Vault
GET  /status                                        readiness and diagnostics (never the Vault path)
POST /projects                                      create a project in the shared Vault
POST /projects/{project_id}/sessions                bind a Hermes session to the project
GET  /projects/{project_id}/sessions                list the project's bindings
DELETE /projects/{project_id}/sessions/{stored_session_id}    remove a binding
POST /projects/{project_id}/chapters/{chapter_id}/save        confirmed chapter save
```

`PUT /settings` is the only configuration write. It runs the scoped selection
transaction and updates only the Story settings keys shown below; requests
never supply a Hermes home path. Chapter saves keep the confirmed-save rules
from “Draft and save behavior”: explicit `confirmed: true` plus the chapter's
`expected_version`, rechecked immediately before the atomic Obsidian
replacement.

Actionable codes from setup and status:

| Code | Meaning |
| --- | --- |
| `profile_not_selected` | Nothing selected yet; call `PUT /settings` first. |
| `profile_invalid` / `profile_not_found` | The Profile name is invalid or not a prepared Hermes Profile. |
| `configuration_incomplete` | A partial selection; provide the missing settings field. |
| `managed_config` | Hermes manages this config; Story will not write it. |
| `config_invalid` / `config_write_failed` | The target `config.yaml` cannot be read or written. |
| `agent_not_installed` / `agent_name_mismatch` / `version_mismatch` | A plugin copy (or its `story_construction_plugin/` package) is missing or unreadable, misnamed, or its `plugin.yaml` version or package sources differ from the default copy. |
| `agent_not_enabled` | The target Profile does not have `story-construction` enabled. |
| `vault_not_directory` / `vault_unwritable` / `vault_mismatch` | The shared Vault path is not a directory, is read-only, or the stored target and shared Vault settings disagree and no new `vault_root` was submitted. |
| `vault_unavailable` | The Vault could not be opened as a Story repository. |
| `hermes_home_mismatch` / `runtime_home_unavailable` | The process home does not match `locked_hermes_home`. |
| `profile_switched` | The selection changed during a write; retry the request. |
| `binding_state_invalid` | `sessions.json` is malformed or alias-conflicting; repair or remove it to recover. |
| `profile_lock_mismatch` / `permission_denied` | The request scope leaves the locked Profile or the bound session's project. |

### Config.yaml ownership

The selection transaction writes Story settings in exactly two homes:

```yaml
# default home config.yaml (Dashboard API side)
plugins:
  entries:
    story-construction:
      settings:
        selected_profile: "writer"
        vault_root: "D:/Obsidian/NovelVault"
```

```yaml
# target Profile home config.yaml (Agent side), e.g. profiles/writer
plugins:
  enabled:
    - story-construction
  entries:
    story-construction:
      settings:
        locked_profile: "writer"
        locked_hermes_home: "C:/Users/you/.hermes/profiles/writer"
        vault_root: "D:/Obsidian/NovelVault"
```

`locked_hermes_home` must be the canonical path returned by Hermes
`get_hermes_home()` within the selected Profile's bound scope. It identifies
the Story runtime's Profile home, not an exclusive Gateway process; do not
guess it from the display name. Every Story API and tool
scope must also exactly match `locked_profile`; a mismatch is rejected with
`profile_lock_mismatch`. The backend process must be able to read and write
the configured shared Vault.

### Durable session bindings

Durable binding state lives at
`<Profile home>/plugin-data/story-construction/sessions.json` in the selected
Profile's home — for example `profiles/writer/plugin-data/story-construction/sessions.json`
— not in the plugin installation tree. Every tool call re-reads this file: a
bind or unbind from the Dashboard API is effective for the very next Gateway
tool call without re-registering anything, and deleting or corrupting the file
denies the next call instead of falling back to stale state. Normal sessions do
not receive Story tools when the runtime is incomplete, and every tool and save
still requires the backend-authorized session-to-project binding.

### Writing Profile scope and Gateway deployment

Use Hermes' existing multi-profile Gateway deployment; a selected writing
Profile does not require a separate single-profile Gateway. Installation and
enablement in the writing Profile are separate from Gateway process ownership.
`locked_profile` and `locked_hermes_home` constrain the Story runtime and its
session bindings, not every Profile served by the Gateway. The YAML profile
label alone is not proof of authorization.

Full multiplex compatibility still requires real integration verification of
Profile-scoped plugin loading, tool dispatch, and A → B → A session isolation.
This deployment statement is not a claim that those checks have passed.

Enable the Desktop half separately in Capabilities → Plugins. The Desktop API
is mounted under `/api/plugins/story-construction/` and is reached only through
the namespace-scoped `ctx.rest` door. The Dashboard API has no trusted current
profile request context in this temporary arrangement: request `profile` values
must match `locked_profile` and any existing backend session binding, but are
not accepted as proof of identity. It rejects an uninitialized or invalid
runtime and exposes only non-sensitive status fields; the only configuration
it ever writes are the Story settings keys above, through the scoped setup
transaction.

The Desktop half uses the selected writing Profile's Hermes sessions without
requiring a dedicated Gateway process. Its normal project-first workflow is:

```text
Create project → initialize Obsidian skeleton → create and bind Hermes session
→ submit visible first writing task → choose chapter/goal in chat → continue the bound session
```

Project creation does not require a focused chat. The backend initializes the
Obsidian project, world, first volume, and first chapter; “New writing session”
then creates a Hermes session that follows the locked Profile configuration,
binds it on the backend, submits the visible kickoff task, and opens it in the
main chat. If kickoff submission fails after binding, use “Retry first task”;
it reuses the same stored/runtime session IDs and does not create another
session. If a durable binding points to a deleted Hermes session, “Continue”
shows “Remove stale binding”; removal occurs only after that explicit action.

## Project Markdown contract

The backend recognizes Markdown files with YAML frontmatter records:

```text
Project → WorldInfo (0..1) → WorldInfoEntry (0..many)
        → Character (0..many)
        → NoteCategory (0..many; at most two levels) → Note (0..many)
        → Volume (at least one) → Chapter (0..many)
```

IDs and relationship fields are authoritative. A chapter stores both
`project_id` and `volume_id`; its `source_ref` and content hash provide the
optimistic version used during save. Worldbook, character, note, and chapter
bodies are loaded through project-scoped repository methods and Story tools,
not from arbitrary paths supplied by the model.

## Agent and prompt boundaries

The normal Hermes loop is preserved:

```text
Session input
  → Hermes stable system prompt + StoryConstructionAgentPrompt v1
  → canonical Session history + current turn
  → LLM call
  → story.* / skill_view tool call
  → session/project permission check
  → scoped Markdown query
  → ToolMessage
  → next LLM call
  → chapter draft
```

The main template is registered through Hermes'
`register_system_prompt_section()` seam. It is rendered once when a bound Story
session is created and remains byte-stable across requests. Request assembly
still includes that stable System Prompt on every LLM request so Hermes and the
provider can reuse their prompt-cache prefix. Neither template is written back
to Session history. Live project records and Skill bodies arrive through the
normal tool-result path.

`StoryWorkerPrompt v1` is a separate fresh child context. A child receives only
the explicit project/chapter goal, selected Skill guidance, and validated source
references; it is read-only and has no chapter-save operation. The main Agent is
the only synthesizer.

## Draft and save behavior

Generated chapter output is a local Draft first. Saving requires an explicit
confirmation checkbox and sends the session/profile/connection, project/chapter
IDs, and expected content version. The backend rechecks Desktop permission and
the version immediately before the atomic Obsidian replacement. A conflict
returns both the current chapter and generated draft for review; it never
silently retargets or overwrites the newer file.

## Boundaries and non-goals

- No arbitrary filesystem access from the model or Renderer.
- No automatic chapter save after an Agent response.
- No cross-machine Vault synchronization in the first version.
- Writing Profile bindings do not require a single-profile Gateway. Full multiplex integration remains to be verified; do not treat this declaration as a compatibility test result.
- A project switch should start or bind a new Story session; a chapter switch is
  dynamic turn context and does not mutate the stable prompt.
- The plugin uses Hermes built-in `skill_view`, plugin Skills, tool dispatch,
  `ToolMessage` continuation, and Desktop SDK REST/query primitives; it does
  not add a story-specific core tool or prompt-cache invalidation path.

## Verification

From this package directory:

```powershell
$env:UV_CACHE_DIR = "..\\.uv-cache"
.venv\Scripts\python.exe -m pytest -q
node --test desktop/*.test.mjs
```

To run the tests through uv, pass `--frozen` so uv uses `uv.lock` as written and
does not re-resolve or rewrite it:

```powershell
uv run --frozen --with pytest --with ruamel.yaml pytest tests -q
```

`pyproject.toml` sets `[tool.uv] exclude-newer = "14 days"`, so dependency
versions published in the last 14 days are not selected when the lock is
regenerated with `uv lock`.

The end-to-end test uses a temporary Vault and exercises the retrieval result,
ToolMessage-shaped continuation, prompt placement, confirmed save, frontmatter
preservation, and version update. The cross-process acceptance tests
(`tests/test_story_profile_processes.py`) additionally prove API-to-Gateway
binding propagation, A→B→A Profile isolation, restart durability, concurrent
API writers, and installer discovery — they spawn real worker processes
against temp homes and need the read-only Hermes source checkout pointed to by
`HERMES_SOURCE`. All tests create their own temporary Hermes homes and Vaults;
nothing here reads or writes a live installation.
