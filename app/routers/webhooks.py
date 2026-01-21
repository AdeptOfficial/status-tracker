"""Dynamic webhook router.

Routes incoming webhooks to the appropriate plugin based on URL path.
URL pattern: POST /hooks/{service}

Example:
  POST /hooks/jellyseerr -> JellyseerrPlugin.handle_webhook()
  POST /hooks/sonarr -> SonarrPlugin.handle_webhook()
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.plugins import get_plugin, get_all_plugins
from app.core.broadcaster import broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hooks", tags=["webhooks"])


@router.post("/{service}")
async def handle_webhook(
    service: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Dynamic webhook handler - routes to appropriate plugin.

    The URL determines which plugin handles the request:
    - POST /hooks/jellyseerr -> JellyseerrPlugin
    - POST /hooks/sonarr -> SonarrPlugin
    - POST /hooks/my-custom-service -> MyCustomServicePlugin (future)

    Returns 404 if no plugin is registered for the service name.
    """
    plugin = get_plugin(service)
    if not plugin:
        logger.warning(f"Webhook received for unknown service: {service}")
        raise HTTPException(
            status_code=404,
            detail=f"Unknown service: {service}. Available: {[p.name for p in get_all_plugins()]}",
        )

    # Parse request body
    try:
        # Try JSON first
        payload = await request.json()
    except Exception:
        # Fall back to form data (for qBittorrent's curl command)
        form = await request.form()
        payload = dict(form)

    logger.info(f"Webhook received: {service} - {payload.get('eventType', payload.get('notification_type', 'unknown'))}")
    logger.debug(f"Payload: {payload}")

    # Process with plugin
    try:
        media_request = await plugin.handle_webhook(payload, db)

        # Commit changes
        await db.commit()

        # Broadcast update if a request was affected
        if media_request:
            await broadcaster.broadcast_update(media_request)

        return {
            "status": "processed",
            "plugin": plugin.name,
            "request_id": media_request.id if media_request else None,
        }

    except Exception as e:
        logger.exception(f"Error processing {service} webhook: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing webhook: {str(e)}",
        )


@router.get("/")
async def list_endpoints():
    """
    List all available webhook endpoints.

    Useful for debugging and service configuration.
    """
    plugins = get_all_plugins()
    return {
        "endpoints": [
            {
                "url": f"/hooks/{p.name}",
                "service": p.display_name,
                "states_provided": [s.value for s in p.states_provided],
                "correlation_fields": p.correlation_fields,
            }
            for p in plugins
        ]
    }
