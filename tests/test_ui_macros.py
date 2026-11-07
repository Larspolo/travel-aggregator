"""The macros of ui.html render the components of DESIGN.md version 2 (#623)."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ENV = Environment(loader=FileSystemLoader("app/web/templates"), autoescape=select_autoescape())


def render(src):
    return ENV.from_string('{% import "ui.html" as ui %}' + src).render()


def test_page_header_has_one_h1_back_link_and_actions_in_toolbar():
    html = render('{% call ui.page_header("Trip <x>", "A to B", ("/", "Trips")) %}<a class="btn">Edit</a>{% endcall %}')
    assert html.count("<h1>") == 1 and "Trip &lt;x&gt;" in html
    assert 'class="page-header"' in html and '<p class="subtitle">A to B</p>' in html
    assert '<a class="back" href="/">← Trips</a>' in html
    assert '<div class="toolbar"><a class="btn">Edit</a></div>' in html


def test_page_header_without_caller_has_no_toolbar():
    html = render('{{ ui.page_header("Settings") }}')
    assert "<h1>Settings</h1>" in html and "toolbar" not in html and "back" not in html


def test_card_has_title_and_body():
    html = render('{% call ui.card("Weights") %}<p>body</p>{% endcall %}')
    assert '<section class="card">' in html and "<h2>Weights</h2>" in html and "<p>body</p>" in html


def test_empty_state_has_text_and_action():
    html = render('{% call ui.empty_state("No trips yet.") %}<a class="btn btn-primary">New trip</a>{% endcall %}')
    assert 'class="empty"' in html and "No trips yet." in html and "btn-primary" in html


def test_css_has_the_component_classes_and_reduced_motion():
    css = Path("app/web/static/app.css").read_text()
    for cls in [".btn ", ".btn-primary", ".btn-ghost", ".btn-danger", ".field ", ".form-grid", ".form-actions",
                ".card ", ".page-header", ".toolbar", ".chip", ".empty", ".field .help", ".field .error"]:
        assert cls in css, cls
    assert "prefers-reduced-motion: reduce" in css
    for section in ["Base", "App bar", "Page header", "Cards", "Forms", "Tables", "Trip page", "Trips list",
                    "Login", "Phone"]:
        assert f"/* == {section} == */" in css, section
