"""Dynamic configuration resolution.

API keys are resolved at call time from two sources in priority order:
  1. ApiKeyStore (encrypted DB records) — set via Settings > API Key Store
  2. Environment variables via app.core.config.settings

This means .env keys continue to work as fallback without any migration.
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

# Maps key_name → settings attribute name for env-var fallback
_ENV_VAR_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "apollo": "APOLLO_API_KEY",
    "clearbit": "CLEARBIT_API_KEY",
    "proxycurl": "PROXYCURL_API_KEY",
}


class DynamicConfig:
    async def get_key(self, db: AsyncSession, key_name: str) -> str:
        """Return the key value for key_name, or raise ConfigurationError if not found.

        Tries ApiKeyStore first, then falls back to the corresponding environment variable.
        Never logs the returned value.
        """
        from app.services.api_key_store import get_key as _get_key_from_store

        # 1. ApiKeyStore (encrypted DB)
        value = await _get_key_from_store(db, key_name)
        if value:
            return value

        # 2. Environment variable fallback
        env_attr = _ENV_VAR_MAP.get(key_name)
        if env_attr:
            from app.core.config import settings
            env_value = getattr(settings, env_attr, "")
            if env_value:
                return env_value

        raise ConfigurationError(
            f"No API key configured for '{key_name}'. "
            f"Set it via Settings > API Key Store or in your .env file."
        )

    async def _has_key(self, db: AsyncSession, key_name: str) -> bool:
        """Return True if a value exists for key_name (DB or env var)."""
        try:
            await self.get_key(db, key_name)
            return True
        except ConfigurationError:
            return False

    async def get_ai_provider(self, db: AsyncSession) -> str:
        """Determine which AI provider to use.

        Priority order:
        1. "ai_provider_preference" record in ApiKeyStore (set via Settings UI)
        2. AI_PROVIDER environment variable (default "anthropic")
        3. Whichever provider has a key set, if only one does
        4. ConfigurationError if neither provider has a key
        """
        from app.core.config import settings
        from app.services.api_key_store import get_key as _get_from_store

        # 1. Check DB preference (stored as a plain key in ApiKeyStore)
        preference = await _get_from_store(db, "ai_provider_preference")

        has_anthropic = await self._has_key(db, "anthropic")
        has_openai = await self._has_key(db, "openai")

        if has_anthropic and has_openai:
            return preference or settings.AI_PROVIDER or "anthropic"
        if has_anthropic:
            return "anthropic"
        if has_openai:
            return "openai"

        raise ConfigurationError(
            "No AI provider API key configured. "
            "Set 'anthropic' or 'openai' key in Settings > API Key Store, "
            "or set ANTHROPIC_API_KEY / OPENAI_API_KEY in your .env file."
        )


dynamic_config = DynamicConfig()
