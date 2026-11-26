# GYST companion (Fedora / Linux)

Lock screen for Firefox desktop. Free time comes from the GYST sync server. Runs as a user service, no sudo.

## Setup
1. Server running (see `server/README.md`). Create an account in the add-on popup (Konto erstellen) and keep the token.
2. Config `~/.config/gyst-companion/config.json` (created on first start, then edit):

```json
{
  "server": "https://<your-service>.onrender.com",
  "token": "<account token>",
  "lock_seconds": 10,
  "max_lock_seconds": 120,
  "message": "Get your shit together. Diese Seite ist gesperrt."
}
```

3. Input access for the evdev grab: `sudo usermod -aG input $USER`, then log out and in.
4. Service:

```bash
mkdir -p ~/.config/systemd/user
cp companion/gyst-companion.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gyst-companion.service
```

5. Firefox native host: `companion/native/gyst_companion.json` goes to `~/.mozilla/native-messaging-hosts/` with `path` set to `companion/gyst_native_host.py`.

## Behaviour
- Polls the server every 10 s and keeps the last state in `~/.local/state/gyst-companion/state.json`.
- No server or no state yet: nothing is free, so the lock always shows.
- A grant arriving during a lock ends it at once.

## Tests
```bash
cd companion && python3 -m unittest test_companion
```
