# Manual Codex MCP Verification

This guide verifies Milestone 2 only: Codex can load the local stdio server,
discover its tools, and run one connection-safe authentication check. Stop after
the acceptance checklist and report the result before Milestone 3 begins.

## Safety boundary

The allowed live tools for this milestone are:

- `garmin_connection_status`
- `garmin_ping`

Run only one of them. Do not invoke profile, activity, health, recovery, or
workout tools. Do not create, schedule, modify, unschedule, or delete workouts.
These connection checks return only `{"ok": true}` and do not affect the watch.

Never paste credentials, MFA codes, token contents, session files, or Garmin
responses into a command, commit, issue, chat, test, or documentation file. The
saved token directory must remain outside this repository.

## Prerequisites

Milestone 1 must already be complete:

- `.venv` is installed in the repository.
- Saved-token authentication succeeds without credential environment variables.
- Tokens remain in the external default `~/.garminconnect` directory, or another
  explicitly configured external directory.

The repository includes `.codex/config.toml`. It supplies project-specific
approval policy and contains no secret values. The server must also be registered
in the local Codex host configuration so the desktop app can discover it:

```bash
codex mcp add garmin -- \
  /absolute/path/to/garminconnect-mcp/.venv/bin/garminconnect-mcp serve
```

Use this repository's real absolute path. Do not add credentials, MFA codes,
token values, or token-directory contents to the command.

## Codex verification

1. Confirm `codex mcp get garmin` shows an enabled host-level stdio server even
   when run outside this repository.
2. Fully quit and reopen the ChatGPT desktop app, or restart the Codex IDE
   extension/CLI.
3. Open this repository as a trusted Codex project and create a new task. An
   already-running task retains its original tool inventory.
4. In the composer or Codex terminal UI, enter `/mcp`.
5. Confirm the `garmin` server is enabled and the Garmin tools are discoverable.
6. Send this exact request:

   ```text
   Use only the garmin_connection_status tool. Do not call any other Garmin tool.
   Tell me whether the connection is working without retrieving Garmin data.
   ```

7. Confirm the tool returns `{"ok": true}` and no private Garmin payload.
8. Stop. Do not test any other Garmin tool during Milestone 2.

## Read-only command-line checks

These commands show the configured server without contacting Garmin:

```bash
codex mcp list
codex mcp get garmin
```

Run `codex mcp get garmin` once outside the repository to confirm the host-level
entry, then again from the repository root to confirm the project policy. Both
should show an enabled stdio server with the `serve` argument. Do not display or
inspect the external token directory.

## Troubleshooting

- `garmin` is absent from desktop settings: run the host-level `codex mcp add`
  command above, fully quit the local client, reopen it, and create a new task.
- `garmin` appears only inside the repository when using `codex mcp get`: only
  the project entry is loaded. Add the host-level entry before retrying desktop.
- Server startup fails: from the repository root, confirm
  `.venv/bin/garminconnect-mcp` exists and the Milestone 1 environment is still
  installed. Do not reinstall or change dependencies until the documented checks
  identify that as necessary.
- Connection check fails only in a restricted shell: local MCP status checks need
  outbound access to Garmin Connect. Retry from the local Codex client rather
  than exposing tokens or credentials to the restricted environment.
- Authentication fails in local Codex too: stop and repeat the Milestone 1
  saved-token check from an interactive terminal. Do not paste the resulting
  error if it contains account information.
- Codex proposes a private-data or workout tool: reject the call and restate the
  exact safe request above.

## Acceptance checklist

- [ ] `codex mcp get garmin` finds the host-level entry outside the repository.
- [ ] A fully restarted local Codex client and new task show `garmin` enabled.
- [ ] The Garmin MCP tool names are discoverable.
- [ ] Exactly one allowed status tool returns `{"ok": true}`.
- [ ] No profile, activity, health, recovery, or workout data was requested.
- [ ] No workout create, schedule, modify, unschedule, or delete tool was used.
- [ ] Tokens remain outside the repository.
- [ ] `git status --short` shows no credential, token, session, or private Garmin
      data.
- [ ] Manual result has been reported before Milestone 3 starts.
