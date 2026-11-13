"""Re-rank a trip page in the browser with the profile dropdown (#2831): the trip page has no weight inputs."""

from app.models import ScoreProfile
from app.profiles import to_config
from app.ranking import Weights
from tests.browser_wait import wait_js


def add_profiles(session, name="Other", base=None, **weights):
    """Add a default profile "Base" (the weights of `base`) and a profile `name` with `weights`; commit."""
    session.add(ScoreProfile(name="Base", is_default=True, config_json=to_config(Weights(**(base or {})))))
    session.add(ScoreProfile(name=name, config_json=to_config(Weights(**{**(base or {}), **weights}))))
    session.commit()


def pick(page, name):
    """Select the profile `name` in the dropdown of the open panel; htmx ranks the table again."""
    page.evaluate("document.querySelectorAll('details.panel-toggle').forEach(d => d.open = true)")
    page.locator("form.weights select[name=profile]").select_option(label=name)
    wait_js(page, "!document.querySelector('#table').classList.contains('htmx-request')")
