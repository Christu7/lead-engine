from datetime import datetime, timezone

# Set at application startup; used for uptime calculations.
APP_START_TIME: datetime = datetime.now(timezone.utc)
