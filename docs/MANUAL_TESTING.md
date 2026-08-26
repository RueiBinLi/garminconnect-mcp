# Manual Garmin Verification

This guide verifies Milestone 1 authentication only. Stop after the checks below;
MCP client setup belongs to Milestone 2.

## Safety boundary

These steps only establish a Garmin Connect session. They do not retrieve raw
health data and do not create, modify, schedule, unschedule, or delete workouts.
They make no changes to the watch.

Never paste credentials, MFA codes, token contents, or Garmin responses into a
terminal command, commit, issue, chat, test, or documentation file.

## First login

From the repository root, confirm `.venv` has been installed. Then use zsh's
interactive prompts so the password is hidden and neither credential is stored
in shell history:

```zsh
read -r "GARMIN_EMAIL?Garmin email: "
read -rs "GARMIN_PASSWORD?Garmin password: "; echo
export GARMIN_EMAIL GARMIN_PASSWORD
.venv/bin/garminconnect-mcp login
unset GARMIN_EMAIL GARMIN_PASSWORD GARMIN_MFA_CODE
```

If MFA is enabled, enter the code only at the command's interactive prompt. A
successful check prints `Garmin login ok` and the token-directory location, but
no account or health data.

## Restart and saved-token check

Run a new process after the credential variables have been unset:

```zsh
.venv/bin/garminconnect-mcp login
```

Success proves the new process can reuse the saved session without a password.
The default token directory is `~/.garminconnect`, outside the repository. Do
not configure `GARMINCONNECT_TOKEN_DIR` inside the repository.

Confirm Git does not see local secret files:

```zsh
git status --short
git check-ignore .env
```

The second command should print `.env`. Do not display or inspect token contents
as part of verification.

## Troubleshooting

- `Garmin MFA is required`: run `login` in an interactive terminal. Do not save
  the code in `.env`; MFA codes are one-time secrets.
- Authentication rejected: verify the credentials by signing in to Garmin
  Connect directly, then rerun the first-login flow. Do not share the error if it
  contains account information.
- Saved-token check asks for credentials again: confirm the second command uses
  the same OS account and `GARMINCONNECT_TOKEN_DIR`. Keep that directory outside
  the repository and retry the first login.
- Token or session errors: move the token directory aside to a private backup,
  then authenticate again. Do not delete tokens until the replacement login has
  succeeded.
- Garmin endpoint or rate-limit error: stop and retry later. Do not loop login
  attempts rapidly.

## Acceptance checklist

- [ ] First interactive login succeeds, including MFA if requested.
- [ ] Credential and MFA variables are unset after login.
- [ ] A second process succeeds using saved tokens.
- [ ] Tokens remain outside the repository.
- [ ] `git status --short` shows no credential, token, or private Garmin data.
- [ ] No write-oriented Garmin command or MCP tool was invoked.
