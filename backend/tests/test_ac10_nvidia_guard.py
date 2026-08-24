import pytest
from providers.registry import ProviderRegistry


def test_ac10_backend_nim_client_raises_importerror():
    """Verify that importing backend.nim_client raises an explicit ImportError."""
    with pytest.raises(ImportError) as exc_info:
        import nim_client  # noqa: F401
    assert "NVIDIA NIM is a TOTAL NO-GO" in str(exc_info.value)


def test_ac10_app_services_nim_client_raises_importerror():
    """Verify that importing app.services.nim_client raises an explicit ImportError."""
    with pytest.raises(ImportError) as exc_info:
        from app.services import nim_client  # noqa: F401
    assert "NVIDIA NIM is a TOTAL NO-GO" in str(exc_info.value)


def test_ac10_provider_registry_rejects_nvidia():
    """Verify that ProviderRegistry hard-blocks any attempt to register an nvidia adapter."""
    registry = ProviderRegistry()
    with pytest.raises(ValueError) as exc_info:
        registry.register_factory("nvidia", lambda: None, priority=0, capabilities=("chat",))
    assert "NVIDIA NIM is a TOTAL NO-GO" in str(exc_info.value)


def test_ac10_no_nvidia_in_default_models():
    """Verify that default models contain no nvidia references."""
    from app.core.config import settings
    assert "nvidia" not in settings.DEFAULT_CHAT_MODEL.lower()
    assert "nemotron" not in settings.DEFAULT_CHAT_MODEL.lower()
