# Persistent cloudflared Tunnel Setup

## Why this exists

The quick tunnel (`cloudflared tunnel --url http://localhost:3000`) issues a **new random `trycloudflare.com` URL every time the process starts**. Every restart of the main PC, app.py, or cloudflared invalidates the URL — the mobile bookmark breaks, and the user has to re-share it.

A **named tunnel** lives on the Cloudflare account, keeps the same hostname (e.g. `blockflow.yourdomain.com`) across restarts, and supports auto-start on boot via a Windows service. One-time setup, stable URL forever.

## Prerequisites

- A domain on Cloudflare (free plan is fine). If you don't own one, a `.xyz` or `.dev` domain on Cloudflare Registrar is ~$10/year.
- `cloudflared.exe` already installed on the main PC (you're using it for quick tunnels).
- Admin PowerShell for the Windows service install step.

## One-time setup (~15 min)

### 1. Authenticate cloudflared with your Cloudflare account

```powershell
cloudflared tunnel login
```

This opens a browser. Pick your zone (e.g. `example.com`). It writes `~/.cloudflared/cert.pem`.

### 2. Create the named tunnel

```powershell
cloudflared tunnel create blockflow
```

Output tells you the tunnel UUID. Note the credentials file path (something like `~/.cloudflared/<UUID>.json`). That file is the tunnel's secret — treat like a private key.

### 3. Route a DNS hostname to the tunnel

```powershell
cloudflared tunnel route dns blockflow blockflow.example.com
```

Replace `blockflow.example.com` with whatever subdomain you want. Cloudflare creates a CNAME automatically.

### 4. Write the config file

Create `C:\Users\socr0\.cloudflared\config.yml`:

```yaml
tunnel: blockflow
credentials-file: C:\Users\socr0\.cloudflared\<UUID>.json

ingress:
  - hostname: blockflow.example.com
    service: http://localhost:3000
  # Optional: expose staging on a separate subdomain
  - hostname: blockflow-staging.example.com
    service: http://localhost:3100
  # Required catch-all (cloudflared rule)
  - service: http_status:404
```

Replace `<UUID>` and hostnames. No trailing slashes on service URLs.

### 5. Smoke test in the foreground

```powershell
cloudflared tunnel run blockflow
```

Visit `https://blockflow.example.com` from your phone on mobile data (not Wi-Fi — proves it's going through Cloudflare, not your LAN). You should see the BlockFlow UI. Ctrl-C to stop.

### 6. Install as a Windows service (auto-start on boot)

**Admin PowerShell:**

```powershell
cloudflared service install
```

This creates a Windows service named `Cloudflared` that starts automatically. Verify:

```powershell
Get-Service Cloudflared
# Status   Name               DisplayName
# ------   ----               -----------
# Running  Cloudflared        Cloudflared agent
```

Now reboot once and confirm the URL still works before you trust it.

## Day-to-day operations

### Check status

```powershell
Get-Service Cloudflared
# Or live logs:
Get-EventLog -LogName Application -Source Cloudflared -Newest 20
```

### Restart after config change

```powershell
Restart-Service Cloudflared
```

### Add a new hostname (e.g. a second service on port 8000)

1. Edit `C:\Users\socr0\.cloudflared\config.yml` — add another `- hostname:` block before the catch-all.
2. Add the DNS route: `cloudflared tunnel route dns blockflow api.example.com`
3. `Restart-Service Cloudflared`

### Stop exposing BlockFlow temporarily

```powershell
Stop-Service Cloudflared
```

The hostname will serve a 502 until you restart.

### Uninstall the service

```powershell
cloudflared service uninstall
```

## Security notes

- **The credentials JSON is the tunnel's private key.** Don't commit it. Add `*.cloudflared/*.json` to `.gitignore` if you ever keep the config in a repo.
- **Cloudflare Access** can gate the tunnel with Google/GitHub SSO in a few clicks. Highly recommended before exposing to the public internet — otherwise anyone who guesses the hostname can see your generations. Setup: Cloudflare Zero Trust dashboard → Access → Applications → Add application → Self-hosted → pick hostname → add policy (e.g. "Email equals sosato587@gmail.com"). Free tier covers up to 50 users.
- **Do not expose `:8000` (backend)** directly without Access in front of it. The FastAPI endpoints have no auth — anyone hitting `/api/blocks/*/run` can spend your RunPod credits.

## Migration from quick tunnel

Current workflow:

```powershell
# One terminal:
uv run app.py
# Another terminal:
cloudflared tunnel --url http://localhost:3000
```

New workflow after this setup:

```powershell
# One terminal:
uv run app.py
# (cloudflared is already running as a Windows service)
```

The URL is now `https://blockflow.example.com` every time. Bookmark it on the phone once, never touch it again.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `502 Bad Gateway` after reboot | `app.py` not running yet | Start BlockFlow, wait ~30s, retry |
| `Error 1033` on the hostname | Tunnel not connected to Cloudflare edge | `Restart-Service Cloudflared` |
| Service won't start | Config yaml parse error | `cloudflared tunnel ingress validate` |
| Works from phone on Wi-Fi, not mobile data | You're hitting LAN, not tunnel | Rename `localhost` refs to the tunnel hostname |
| New URL issued every restart | Still using `--url` quick tunnel | You didn't install the service; redo step 6 |

## Cost

- Cloudflare Tunnel: free forever, unlimited bandwidth.
- Cloudflare Access (Zero Trust): free tier up to 50 users.
- Domain: ~$10/year if you don't already have one.

Total: one $10 bill per year, and the URL never changes.
