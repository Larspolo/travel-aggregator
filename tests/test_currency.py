"""The exchange rates to EUR: the conversion, the stored rates and the migration (#383)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.currency import load_rates, to_eur
from app.db import make_engine
from app.models import CurrencyRate


def test_to_eur_converts_and_rounds_to_cents():
    assert to_eur(Decimal("120"), "CHF", {"CHF": Decimal("1.07")}) == Decimal("128.40")


def test_to_eur_rounds_half_even():
    # 0.125 rounds to 0.12 (half to even), 0.375 rounds to 0.38
    assert to_eur(Decimal("1"), "X", {"X": Decimal("0.125")}) == Decimal("0.12")
    assert to_eur(Decimal("1"), "X", {"X": Decimal("0.375")}) == Decimal("0.38")


def test_to_eur_gives_the_amount_for_eur():
    assert to_eur(Decimal("42.50"), "EUR", {}) == Decimal("42.50")


def test_to_eur_gives_none_without_a_rate():
    assert to_eur(Decimal("10"), "SEK", {"CHF": Decimal("1.07")}) is None


def test_to_eur_returns_decimal_not_float():
    result = to_eur(Decimal("10"), "CHF", {"CHF": Decimal("1.07")})
    assert isinstance(result, Decimal)


def test_load_rates_gives_the_stored_rates(sessions):
    with sessions() as s:
        s.add_all([
            CurrencyRate(code="CHF", eur_per_unit=Decimal("1.070000"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)),
            CurrencyRate(code="GBP", eur_per_unit=Decimal("1.151234"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)),
        ])
        s.commit()
        rates = load_rates(s)
    assert rates == {"CHF": Decimal("1.070000"), "GBP": Decimal("1.151234")}
    assert all(isinstance(v, Decimal) for v in rates.values())


def test_load_rates_is_empty_without_rows(sessions):
    with sessions() as s:
        assert load_rates(s) == {}


def test_rate_must_be_positive(sessions):
    from sqlalchemy.exc import IntegrityError

    with sessions() as s:
        s.add(CurrencyRate(code="ZAR", eur_per_unit=Decimal("0"), updated_at=datetime(2026, 11, 1, tzinfo=UTC)))
        with pytest.raises(IntegrityError):
            s.commit()


def _alembic_config(url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    return cfg


def test_migration_upgrades_and_downgrades(migrated_url):
    cfg = _alembic_config(migrated_url)
    engine = make_engine(migrated_url)
    try:
        assert "currency_rates" in inspect(engine).get_table_names()
        command.downgrade(cfg, "0012")
        assert "currency_rates" not in inspect(engine).get_table_names()
        command.upgrade(cfg, "head")
        assert "currency_rates" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
