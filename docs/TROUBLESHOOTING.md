# Troubleshooting

Moved out of the README on 2026-10-20. Operational facts for the homelab instance
live in the private homeserver service README.


### Common Issues

**Container won't start**
```bash
docker compose logs status-tracker
# Check for missing env vars or connection errors
```

**Webhooks not received**
```bash
# Check container is on same network as media services
docker network inspect media-net

# Test webhook endpoint
curl -X POST http://localhost:8100/hooks/test -d '{}'
```

**Requests stuck at IMPORTING**
- Regular movies/TV: Check Jellyfin webhook plugin is installed and configured
- Anime movies: Should auto-resolve via fallback checker (30s polling)
- Anime TV: Check Shoko matches and the bounded library-refresh audit; see current testing evidence.

**Database locked error**
```bash
# Stop container
docker compose down

# Check for stale lock
ls -la data/

# Restart
docker compose up -d
```

**SSE not updating**
- Both pages use live updates; reconnection and detail progress are covered by browser acceptance.
- Check browser console for connection errors

**Deletion fails for specific service**

Follow the [permission and retry guide](docs/MEDIA-PERMISSIONS.md). Verify the
movie file is really gone; do not infer success from a missing Radarr record.
TV deletion is currently blocked to preserve sibling seasons.

```bash
# Check deletion logs
curl http://localhost:8100/api/deletion-logs

# Common causes:
# - Service API key missing/invalid in .env
# - ID not captured during initial request (shows "not_needed")
# - Service unreachable (check docker network)
```

**Health endpoint shows service down**
```bash
# Access health dashboard
curl http://localhost:8100/api/health

# Verify service connectivity from container
docker exec status-tracker curl http://sonarr:8989/api/v3/system/status
```

### Debug Mode

Enable verbose logging:
```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker compose up -d --force-recreate
```

### Getting Help

1. Check `issues/` folder for known issues
2. Read `DIARY.md` for recent changes and fixes
3. Check `docs/` for technical deep-dives

