# Songs backend

FastAPI service that powers the Songs editor.

## Authentication

Every route is closed unless `app/auth/policy.py` lists it in `PUBLIC_ROUTES`.
That list is the whole answer to "what is reachable without signing in?" — a
router added under `app/api/` is denied by default until somebody opens it on
purpose.

Sessions are opaque tokens in an HttpOnly cookie, with a row per session in
the database. The row stores only the SHA-256 of the token, so a copy of
`songs.db` cannot be replayed as a login, and access is revoked by deleting
rows rather than by waiting for a token to expire.

### Modes

`SONGS_API_AUTH_MODE` picks how hard the API insists on a session:

| value | behaviour |
| --- | --- |
| `required` | **Production.** 401 on everything outside `PUBLIC_ROUTES`. Swagger and `/openapi.json` are switched off. |
| `optional` | The user is attached when a session is present, and no request is ever refused. For the step where part of the app becomes public. |
| `disabled` | No authentication at all. Local development only. |

Anything but `required` logs a warning banner at startup and shows up in
`/health`:

```bash
curl -s https://songs-api.it-slon.ru/health
# {"status":"ok","auth":"required"}
```

### Managing users

There is no registration endpoint and no admin API — accounts are managed from
the server shell:

```bash
cd /srv/apps/songs-backend
sudo -u songs .venv/bin/python -m app.cli user add vasya --display-name "Вася"
sudo -u songs .venv/bin/python -m app.cli user list
sudo -u songs .venv/bin/python -m app.cli user passwd vasya
sudo -u songs .venv/bin/python -m app.cli user disable vasya
```

The password is prompted for, never passed as an argument — an argument would
land in shell history and in the process list.

`disable` is the normal way to take access away: it revokes every session
immediately and keeps the row, so the display names already recorded in
`song.updated_by` and in the revision history still refer to somebody. `delete`
removes the row outright and asks for confirmation first.

### Settings

| variable | default | notes |
| --- | --- | --- |
| `SONGS_API_AUTH_MODE` | `required` | See above. |
| `SONGS_API_SESSION_COOKIE` | `songs_session` | Cookie name. |
| `SONGS_API_SESSION_TTL_DAYS` | `90` | Sliding: refreshed on use, at most once a day. |
| `SONGS_API_SESSION_COOKIE_SECURE` | `1` | Must be `0` for local http, must stay `1` behind https. |

`SONGS_API_CORS_ORIGINS` has to name the frontend origin exactly. Credentialed
requests are rejected by the browser against a wildcard, so a missing origin
here shows up as every request failing CORS rather than as a 401.

## Tests

```bash
pip install -e ".[dev]"
python -m pytest
```

The suite covers the access policy, the sign-in flow and the CLI — the parts
that fail quietly. A route left open answers `200` and nothing looks wrong
until somebody reads it over the internet, so `tests/test_policy.py` walks the
application's own routing table and asserts that everything outside
`PUBLIC_ROUTES` returns 401. That is what would have caught `/openapi.json`
staying reachable: FastAPI serves it as a plain Starlette route, which
application-wide dependencies never run for.

`tests/test_policy.py::test_public_list_is_only_auth_routes_and_health` pins
the public list itself. It fails whenever something is added to
`PUBLIC_ROUTES`, on purpose: opening a route should be a visible decision in
the same commit rather than a line nobody reviewed.

CI runs this before `deploy`, so a failure stops the release.

## Continuous deployment overview

- Source of truth stays in this repo. Any push to `main` (or manual dispatch) fans out to GitHub Actions (`.github/workflows/backend-deploy.yml`).
- CI installs the backend in editable mode and runs a bytecode smoke test to catch syntax regressions before touching the server.
- The `deploy` job SSHes into `/srv/apps/songs-backend`, executes `git fetch && git reset --hard origin/main`, refreshes the virtualenv, and restarts the `songs-backend` systemd unit. Because the server pulls directly from GitHub, host-only files like `.env` or `songs.db` are left untouched.
 
## One-time server setup

1. **Provision packages**
   ```bash
   sudo apt update && sudo apt install -y python3.11 python3.11-venv git
   ```
2. **Create service user and directories**
   ```bash
   sudo useradd --system --home /srv/apps --shell /bin/bash songs || true
   sudo mkdir -p /srv/apps/songs-backend
   sudo chown -R songs:songs /srv/apps/songs-backend
   ```
3. **Populate the repo once** (allows the first workflow run to succeed)
   ```bash
   sudo -u songs git clone git@github.com:<your-account>/songs.git /srv/apps/songs-backend
   ```
   Inside `/srv/apps/songs-backend`, configure SSH deploy keys so that `git fetch origin main` works without prompts (see below).
4. **Create the production env file** (never commit secrets)
   ```bash
   sudo -u songs cp .env.example .env
   sudo -u songs nano /srv/apps/songs-backend/.env  # adjust DATABASE_URL, CORS, etc.
   ```
5. **Create the virtualenv**
   ```bash
   sudo -u songs python3.11 -m venv /srv/apps/songs-backend/.venv
   sudo -u songs /srv/apps/songs-backend/.venv/bin/pip install --upgrade pip
   sudo -u songs /srv/apps/songs-backend/.venv/bin/pip install -e /srv/apps/songs-backend
   ```
6. **Install the systemd unit**
   ```bash
   sudo cp deploy/songs-backend.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now songs-backend
   sudo systemctl status songs-backend
   ```
   Tune the `User=`, `WorkingDirectory`, or `ExecStart` paths inside `deploy/songs-backend.service` if your layout differs.

7. **Give the server read-only access to GitHub**
   ```bash
   sudo -u songs ssh-keygen -t ed25519 -f /srv/apps/songs-backend/.ssh/id_ed25519
   sudo -u songs cat /srv/apps/songs-backend/.ssh/id_ed25519.pub
   ```
   Add the public key as a **Deploy key** (read-only) in GitHub → Repository → Settings → Deploy keys, and ensure `ssh -T git@github.com` succeeds from the server.

## GitHub secrets required by the workflow

| secret | example | notes |
| --- | --- | --- |
| `BACKEND_SSH_HOST` | `223.244.23.234` | Public IP / hostname of the server |
| `BACKEND_SSH_PORT` | `22` | Optional; omit for port 22 | 
| `BACKEND_SSH_USER` | `songs` | Must own `/srv/apps/songs-backend` and have passwordless sudo for `systemctl` and `cp` (see below) |
| `BACKEND_SSH_KEY` | *(PEM private key)* | Private key granting SSH access for the user above |
 
Generate the SSH key pair locally (`ssh-keygen -t ed25519 -f songs-backend-deploy`), add the **public** part to `~songs/.ssh/authorized_keys`, and store the **private** part verbatim (including `-----BEGIN`/`END-----`) in the `BACKEND_SSH_KEY` secret.

The deploy user needs passwordless sudo for these commands (create `/etc/sudoers.d/songs-backend`):
```bash
echo "songs ALL=(ALL) NOPASSWD: /usr/bin/cp /srv/apps/songs-backend/deploy/songs-backend.service /etc/systemd/system/, /bin/systemctl daemon-reload, /bin/systemctl restart songs-backend, /bin/systemctl status songs-backend" | sudo tee /etc/sudoers.d/songs-backend
sudo visudo -c
```

## What happens on every push

1. `backend-ci` job installs the package in editable mode and runs `python -m compileall app`.
2. `deploy` job (only on `main`) SSHes into `/srv/apps/songs-backend`, runs `git fetch --prune origin main && git reset --hard origin/main`, ensures `/srv/apps/songs-backend/.venv` exists (created with `python3.11`), upgrades `pip`, reinstalls the backend, re-copies the service unit to `/etc/systemd/system/`, and calls `sudo systemctl restart songs-backend` (after `daemon-reload`).
3. `systemctl status songs-backend` output is streamed into the Actions logs, so failures are visible immediately.

Trigger it manually via the *Run workflow* button if you need an ad-hoc redeploy without a git push.
