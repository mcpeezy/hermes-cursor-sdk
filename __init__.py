"""Experimental provider for the official Cursor Agent SDK."""
from providers import register_provider
from providers.base import ProviderProfile
from .client import CursorSDKClient, CursorSDKError
from . import catalog


def terminal_sdk_error(error, **kwargs):
    return {'reason': 'format_error', 'retryable': False, 'should_fallback': False, 'should_compress': False}


class CursorSDKProfile(ProviderProfile):
    def create_client(self, **kwargs):
        return CursorSDKClient(**kwargs)

    def fetch_models(self, **kwargs):
        return catalog.models()

    # Optional picker extensions: older Hermes releases ignore these hooks.
    def picker_capabilities(self, model):
        return catalog.capabilities(model) if model in catalog.selections() else {}

    def fast_mode_overrides(self, model, *, tier=None):
        if tier == 'ultrafast' or not self.picker_capabilities(model).get('fast'):
            return None
        return {'speed': 'fast'}

    def build_api_kwargs_extras(self, *, reasoning_config=None, **context):
        return {}, {'cursor_reasoning': reasoning_config, 'cursor_fast': False}


PROFILE = CursorSDKProfile(
    name='cursor-sdk', aliases=(), api_mode='chat_completions',
    env_vars=('CURSOR_API_KEY',), base_url='cursor-sdk://local',
    auth_type='api_key', supports_health_check=False,
    supports_vision=False, supports_vision_tool_messages=False,
    classify_api_error=terminal_sdk_error,
    fallback_models=tuple(catalog.models()),
)


def register(ctx):
    register_provider(PROFILE)


register_provider(PROFILE)
