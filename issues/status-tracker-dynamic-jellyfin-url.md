# Status Tracker: Dynamic Jellyfin URL Based on Connection Type

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** Low

## Problem

The "Watch Now" button currently uses a hardcoded `JELLYFIN_URL` from environment config. This creates issues when users access the dashboard from different networks:

| Access Method | Current Behavior | Expected Behavior |
|---------------|------------------|-------------------|
| LAN (10.0.x.x) | Links to `http://10.0.2.20:8096` | Works |
| Tailscale | Links to `http://10.0.2.20:8096` | Should use Tailscale hostname |
| Cloudflare Tunnel | Links to `http://10.0.2.20:8096` | Should use public domain |
| External (no VPN) | Links to internal IP | Broken - can't reach |

## Proposed Solution

Dynamically determine the appropriate Jellyfin URL based on how the user is accessing status-tracker.

### Option 1: Client-Side Detection (Recommended)

Detect connection type in JavaScript and rewrite links accordingly.

```javascript
// Detect access method from current URL
function getJellyfinUrl(jellyfinId) {
    const host = window.location.hostname;

    // Map dashboard hostnames to Jellyfin URLs
    const urlMap = {
        '10.0.2.20': 'http://10.0.2.20:8096',           // Direct LAN
        'status.dev.adeptlab': 'http://jellyfin.dev.adeptlab',  // Local DNS
        'status.tailnet': 'http://jellyfin.tailnet',     // Tailscale
        'status.example.com': 'https://jellyfin.example.com',   // Cloudflare
    };

    const baseUrl = urlMap[host] || 'http://10.0.2.20:8096';  // Fallback
    return `${baseUrl}/web/index.html#!/details?id=${jellyfinId}`;
}
```

**Pros:**
- No backend changes needed
- Works with existing architecture
- User gets correct link based on their actual access method

**Cons:**
- Requires maintaining URL mapping in JavaScript
- Mapping needs to be updated when network config changes

### Option 2: Multiple Environment Variables

Configure multiple Jellyfin URLs and let the template choose.

```bash
# .env
JELLYFIN_URL_INTERNAL=http://10.0.2.20:8096
JELLYFIN_URL_TAILSCALE=http://jellyfin.tailnet
JELLYFIN_URL_EXTERNAL=https://jellyfin.example.com
```

Pass all URLs to template and select client-side.

### Option 3: Reverse Proxy Header Detection

Use `X-Forwarded-Host` or similar headers to detect access method server-side.

```python
@app.get("/request/{id}")
async def get_request(request: Request, ...):
    forwarded_host = request.headers.get("X-Forwarded-Host", "")

    if "tailscale" in forwarded_host:
        jellyfin_url = settings.JELLYFIN_URL_TAILSCALE
    elif forwarded_host.endswith(".com"):
        jellyfin_url = settings.JELLYFIN_URL_EXTERNAL
    else:
        jellyfin_url = settings.JELLYFIN_URL_INTERNAL
```

## Implementation Steps

1. Add URL mapping configuration (env vars or config file)
2. Implement detection logic (client or server side)
3. Update templates to use dynamic URL
4. Test from all access methods

## Files to Modify

- `app/config.py` - Add multiple Jellyfin URL settings
- `app/templates/detail.html` - Dynamic "Watch Now" link
- `app/templates/components/card.html` - If cards have watch links
- `app/routers/pages.py` - Pass URL mapping to templates (if server-side)

## Edge Cases

1. **User bookmarks a link** - Link will use the URL from when they viewed it
2. **Mixed access** - User on LAN but accessed via external URL (rare)
3. **Jellyfin not exposed externally** - External links should show warning or be hidden

## Related

- Current hardcoded URL: `JELLYFIN_URL` in `.env`
- Cloudflare tunnel config: `services/infra.md`
- Tailscale setup: `services/infra.md`
