"""Deployment preparation (Prompt 9): the hosting configuration files must stay consistent with the code.

Nothing here deploys anything or contacts a host.
"""

import json
import re
from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app

from .speech_fakes import FakeModel, transcriber_with

REPO = Path(__file__).resolve().parents[2]
RENDER = yaml.safe_load((REPO / "render.yaml").read_text(encoding="utf-8"))
SERVICE = RENDER["services"][0]
ENV = {item["key"]: item for item in SERVICE["envVars"]}
SECRETS = ("SUPABASE_SERVICE_ROLE_KEY", "HF_TOKEN", "SUPABASE_URL", "BACKEND_CORS_ORIGINS")


def test_render_builds_and_starts_the_backend_on_the_port_render_provides():
    assert SERVICE["rootDir"] == "backend"
    assert SERVICE["runtime"] == "python"
    assert SERVICE["buildCommand"].startswith("pip install -r requirements.txt")
    assert "python -m app.speech.prefetch" in SERVICE["buildCommand"]
    assert SERVICE["startCommand"] == "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    assert (REPO / "backend" / "requirements.txt").is_file()


def test_render_health_check_is_a_real_route():
    paths = create_app(Settings(), transcriber=transcriber_with(FakeModel([]))).openapi()["paths"]

    assert SERVICE["healthCheckPath"] in paths


def test_secrets_are_declared_but_never_given_values_in_the_blueprint():
    text = (REPO / "render.yaml").read_text(encoding="utf-8")

    for key in SECRETS:
        assert ENV[key] == {"key": key, "sync": False}, key
    assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{10,}", text)


def test_every_variable_the_blueprint_sets_is_one_the_backend_reads():
    config = (REPO / "backend" / "app" / "config.py").read_text(encoding="utf-8")

    for key in ENV:
        if key != "PYTHON_VERSION":  # read by Render itself
            assert f'"{key}"' in config, key


def test_the_model_downloaded_at_build_time_is_where_the_service_looks_for_it():
    assert ENV["WHISPER_DOWNLOAD_ROOT"]["value"] == "models"
    assert ENV["WHISPER_MODEL"]["value"] == "base"
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "backend/models/" in ignored


def test_vercel_serves_the_single_page_app_for_every_route():
    config = json.loads((REPO / "frontend" / "vercel.json").read_text(encoding="utf-8"))

    assert config["buildCommand"] == "npm run build"
    assert config["outputDirectory"] == "dist"
    assert {"source": "/(.*)", "destination": "/index.html"} in config["rewrites"]
    package = json.loads((REPO / "frontend" / "package.json").read_text(encoding="utf-8"))
    assert "build" in package["scripts"]


def test_production_needs_an_explicit_cors_origin():
    """The default allows only local development origins, so a deployed frontend must be listed explicitly."""
    assert all("localhost" in origin or "127.0.0.1" in origin for origin in Settings().cors_origins)


def test_the_deployment_guide_says_nothing_is_deployed_yet_and_names_every_setting():
    guide = (REPO / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "Not deployed" in guide
    for key in [*ENV, "VITE_API_BASE_URL"]:
        assert key in guide, key
