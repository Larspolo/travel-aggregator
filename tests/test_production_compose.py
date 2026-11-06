"""The production compose file: the :latest image, the local-only port and the own watchtower scope (#84)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "deploy" / "production" / "docker-compose.yml"


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def test_app_follows_latest_image() -> None:
    app = _compose()["services"]["app"]
    assert app["image"] == "ghcr.io/larspolo/travel-aggregator:latest"


def test_app_publishes_only_on_localhost() -> None:
    ports = _compose()["services"]["app"]["ports"]
    assert len(ports) == 1
    assert ports[0].startswith("127.0.0.1:")
    assert ports[0].endswith(":8000")


def test_all_services_use_production_watchtower_scope() -> None:
    services = _compose()["services"]
    for name in ("app", "db", "updater"):
        labels = services[name].get("labels", [])
        assert "com.centurylinklabs.watchtower.scope=travel-production" in labels, name
    assert services["updater"]["environment"]["WATCHTOWER_SCOPE"] == "travel-production"


def test_database_has_its_own_named_volume() -> None:
    compose = _compose()
    assert "pgdata-production" in compose["volumes"]
    assert "pgdata-production:/var/lib/postgresql/data" in compose["services"]["db"]["volumes"]


def test_no_traefik_labels_or_external_network() -> None:
    compose = _compose()
    assert "networks" not in compose
    for name, service in compose["services"].items():
        for label in service.get("labels", []):
            assert not label.startswith("traefik."), name
