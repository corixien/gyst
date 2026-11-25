# GYST companion (Linux)

Full-screen lock with a system-wide keyboard and mouse grab. The Firefox addon asks it on every blocked navigation.

## Install

No sudo needed when your user is in group `input` (check: `id -nG | grep -w input`).

```bash
mkdir -p ~/.config/gyst-companion ~/.config/systemd/user ~/.mozilla/native-messaging-hosts
chmod +x ~/gyst/companion/gyst_native_host.py
sed "s#__HOST__#$HOME/gyst/companion/gyst_native_host.py#" ~/gyst/companion/native/gyst_companion.json > ~/.mozilla/native-messaging-hosts/gyst_companion.json
cp ~/gyst/companion/gyst-companion.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gyst-companion.service
```

The first start creates `~/.config/gyst-companion/config.json`.

## Config

`~/.config/gyst-companion/config.json`:

- `lock_seconds`: countdown on the lock screen (default 10).
- `max_lock_seconds`: hard cap, the lock always ends after this (default 120).
- `message`: text on the lock screen.
- `free_windows`: daily unlocked windows, e.g. `[{"from": "20:00", "to": "22:00"}]`.
- `partner_secrets`: one hex key per partner, see below.

## Partner codes

Partner grants 30 min, 1 h or a full day. Codes are HMAC of tier and 5-minute window, so no server is needed.

1. Partner generates a key: `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. Key goes into `partner_secrets` in the config (daemon side) and into the partner page on the partner's device.
3. Partner opens `companion/partner/index.html` (e.g. on the phone), enters the key once, taps a tier, reads out the 8-digit code.
4. User types the code on the lock screen and presses Enter.

Limitation: the key sits in a file the user can read. A real barrier needs an asymmetric key (signature on the partner device, public key only on the machine). Planned as next step.

## Test first

Set `lock_seconds` to 3 and `max_lock_seconds` to 15 before the first real lock. Run `systemctl --user status gyst-companion` and `journalctl --user -u gyst-companion -f` during the test.

## Tests

`python3 -m unittest -q test_companion` (from this folder).
