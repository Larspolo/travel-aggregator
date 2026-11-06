"""The GitHub login of a Claude account: `agent_config.login` (#4243)."""
import agent_config

CONFIG = {
    "owner": "owner-login",
    "accounts": {"first": {"login": "first-login"}, "second": {"login": "second-login"}},
}


def test_login_of_an_account_is_its_table_login():
    assert agent_config.login("second", config=CONFIG) == "second-login"


def test_login_of_no_account_is_the_owner():
    assert agent_config.login(None, config=CONFIG) == "owner-login"


def test_login_of_an_unknown_account_is_the_owner():
    assert agent_config.login("third", config=CONFIG) == "owner-login"


def test_login_with_no_accounts_table_is_the_owner():
    assert agent_config.login("first", config={"owner": "owner-login"}) == "owner-login"
