# Deployment Notes

## Reference deployment

- Debian 13 unprivileged LXC
- 2 vCPU
- 2 GB RAM
- 512 MB swap
- 12 GB local storage
- systemd-managed Uvicorn/FastAPI
- application root `/opt/jarvis-core`
- persistent state `/var/lib/jarvis-core`
- environment `/etc/jarvis-core/jarvis.env`

## Python environment

```bash
apt install -y python3 python3-venv git curl jq sqlite3
python3 -m venv /opt/jarvis-core/.venv
/opt/jarvis-core/.venv/bin/pip install -r requirements.txt
```

Use the venv Python for maintenance commands. Packages such as `httpx` are installed there; do not assume bare `python3` has the application dependencies.

## Environment

```bash
install -d -m 0750 /etc/jarvis-core
cp examples/jarvis.env.example /etc/jarvis-core/jarvis.env
chmod 0600 /etc/jarvis-core/jarvis.env
```

Fill in the real values locally. Never commit them.

## systemd

Copy `systemd/jarvis-core.service` to `/etc/systemd/system/`, adjust the user/group if required, then:

```bash
systemctl daemon-reload
systemctl enable --now jarvis-core
systemctl status jarvis-core --no-pager
```

## Validation

```bash
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:8000/context/observer | jq
curl -s http://127.0.0.1:8000/observer/status | jq
```

After more than 60 seconds, `cycles_completed` should advance.
