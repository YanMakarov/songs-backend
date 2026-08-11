# Songs backend

FastAPI service that powers the Songs editor.

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
| `BACKEND_SSH_HOST` | `223.244.23.233` | Public IP / hostname of the server |
| `BACKEND_SSH_PORT` | `22` | Optional; omit for port 22 |
| `BACKEND_SSH_USER` | `songs` | Must own `/srv/apps/songs-backend` and restart the service (passwordless sudo for `systemctl restart songs-backend`) |
| `BACKEND_SSH_KEY` | *(PEM private key)* | Private key granting SSH access for the user above |
| *(none)* |  |  |

Generate the SSH key pair locally (`ssh-keygen -t ed25519 -f songs-backend-deploy`), add the **public** part to `~songs/.ssh/authorized_keys`, and store the **private** part verbatim (including `-----BEGIN`/`END-----`) in the `BACKEND_SSH_KEY` secret.

## What happens on every push

1. `backend-ci` job installs the package in editable mode and runs `python -m compileall app`.
2. `deploy` job (only on `main`) SSHes into `/srv/apps/songs-backend`, runs `git fetch --prune origin main && git reset --hard origin/main`, ensures `/srv/apps/songs-backend/.venv` exists, upgrades `pip`, reinstalls the backend, and calls `sudo systemctl restart songs-backend` (after `daemon-reload`).
3. `systemctl status songs-backend` output is streamed into the Actions logs, so failures are visible immediately.

Trigger it manually via the *Run workflow* button if you need an ad-hoc redeploy without a git push.
