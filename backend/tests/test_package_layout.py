from __future__ import annotations

import importlib


def test_standard_package_modules_are_importable() -> None:
    module_names = [
        "chat_ui_builder",
        "chat_ui_builder.api.app",
        "chat_ui_builder.api.schemas",
        "chat_ui_builder.core.logging",
        "chat_ui_builder.core.model_config",
        "chat_ui_builder.core.settings",
        "chat_ui_builder.planning.models",
        "chat_ui_builder.planning.parser",
        "chat_ui_builder.planning.prompting",
        "chat_ui_builder.planning.service",
        "chat_ui_builder.compiler.frame",
        "chat_ui_builder.compiler.region_archetypes",
        "chat_ui_builder.compiler.skeleton",
        "chat_ui_builder.streaming.compiler",
        "chat_ui_builder.streaming.json_extractor",
        "chat_ui_builder.streaming.models",
        "chat_ui_builder.streaming.prompting",
        "chat_ui_builder.streaming.runtime",
        "chat_ui_builder.streaming.service",
    ]

    for module_name in module_names:
        assert importlib.import_module(module_name) is not None


def test_package_exposes_fastapi_application() -> None:
    from chat_ui_builder.api.app import app

    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/api/chat/stream" in paths
