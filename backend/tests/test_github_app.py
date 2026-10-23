"""GitHub App authentication + Connect flow, with a fake GitHub (no network)."""
import base64
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client

from delivery.github_auth import AppCredentials, GitHubAuthError, TokenCredentials, load_private_key
from delivery.providers import GitHubProvider
from guardrails.rules import scrub_secrets
from incidents.api import github_views
from incidents.models import RuntimeConfig


class FakeIntegration:
    """Stands in for github.GithubIntegration."""

    def __init__(self, installed=True, app_id="12345", downscope_ok=True):
        self.installed, self.app_id, self.downscope_ok = installed, app_id, downscope_ok
        self.issued = 0
        self.now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    def get_app(self):
        return SimpleNamespace(id=self.app_id, slug="autosre-zero-ops", name="AutoSRE Zero-Ops",
                               html_url="https://github.com/apps/autosre-zero-ops")

    def get_repo_installation(self, owner, name):
        if not self.installed:
            raise RuntimeError("404 Not Found")
        return SimpleNamespace(id=777)

    def get_app_installation(self, installation_id):
        return SimpleNamespace(id=installation_id, app_id=self.app_id, account=SimpleNamespace(login="zero-ops"),
                               repository_selection="selected")

    def get_access_token(self, installation_id, permissions=None):
        if permissions and not self.downscope_ok:
            raise RuntimeError("422 permissions not granted")
        self.issued += 1
        return SimpleNamespace(token=f"ghs_{'x' * 30}{self.issued}", expires_at=self.now + timedelta(hours=1))


class Clock:
    def __init__(self, start):
        self.t = start

    def __call__(self):
        return self.t


def make_creds(integration=None, installation_id=None):
    integ = integration or FakeIntegration()
    clock = Clock(integ.now.timestamp())
    creds = AppCredentials("12345", "-----BEGIN RSA PRIVATE KEY-----\nx\n-----END RSA PRIVATE KEY-----",
                           "zero-ops/victim-service", installation_id, integration=integ, clock=clock,
                           http_get=lambda url: {"id": 4242})
    return creds, integ, clock


def test_installation_token_is_cached_and_renewed_before_expiry():
    creds, integ, clock = make_creds()
    first = creds.token()
    assert first.startswith("ghs_") and integ.issued == 1
    clock.t += 30 * 60
    assert creds.token() == first and integ.issued == 1  # still valid, reused
    clock.t += 26 * 60  # 4 minutes left -> renew early
    assert creds.token() != first and integ.issued == 2
    assert creds.installation_id() == 777  # discovered from the repo


def test_falls_back_when_downscoping_is_rejected():
    creds, integ, _ = make_creds(FakeIntegration(downscope_ok=False))
    assert creds.token().startswith("ghs_")


def test_not_installed_gives_actionable_error():
    creds, _, _ = make_creds(FakeIntegration(installed=False))
    with pytest.raises(GitHubAuthError, match="not installed on zero-ops/victim-service"):
        creds.token()


def test_bot_identity_and_description():
    creds, _, _ = make_creds()
    assert creds.identity() == ("autosre-zero-ops[bot]", "4242+autosre-zero-ops[bot]@users.noreply.github.com")
    d = creds.describe()
    assert d["bot_login"] == "autosre-zero-ops[bot]"
    assert d["install_url"] == "https://github.com/apps/autosre-zero-ops/installations/new"


def test_installation_of_another_app_is_rejected():
    creds, integ, _ = make_creds()
    integ_other = FakeIntegration(app_id="99999")
    creds._integration = integ_other
    with pytest.raises(GitHubAuthError, match="different GitHub App"):
        creds.verify_installation(5)


def test_provider_pushes_with_a_fresh_token_in_a_header_not_the_url():
    creds, integ, clock = make_creds()
    provider = GitHubProvider(creds, "zero-ops/victim-service")
    url, env = provider.clone_source()
    assert url == "https://github.com/zero-ops/victim-service.git" and "ghs_" not in url
    header = env["GIT_CONFIG_VALUE_0"].split("basic ")[1]
    assert base64.b64decode(header).decode() == f"x-access-token:{creds.token()}"
    clock.t += 2 * 3600  # token expired -> next push uses a new one
    _, env2 = provider.clone_source()
    assert env2["GIT_CONFIG_VALUE_0"] != env["GIT_CONFIG_VALUE_0"]
    assert provider.commit_identity()[0] == "autosre-zero-ops[bot]"


def test_installation_tokens_are_scrubbed_from_prompts():
    token = make_creds()[0].token()
    assert token not in scrub_secrets(f"oops {token}")[0]


def test_private_key_loader_validates(tmp_path):
    with pytest.raises(GitHubAuthError, match="not found"):
        load_private_key(str(tmp_path / "missing.pem"))
    bad = tmp_path / "bad.pem"
    bad.write_text("hello")
    with pytest.raises(GitHubAuthError, match="does not look like"):
        load_private_key(str(bad))


def test_token_fallback_has_no_bot_identity():
    assert TokenCredentials("github_pat_abc").identity() is None
    with pytest.raises(GitHubAuthError):
        TokenCredentials("")


# --- Connect flow (API) ----------------------------------------------------------------------

@pytest.fixture
def app_configured(settings, monkeypatch):
    settings.DELIVERY = {**settings.DELIVERY, "PROVIDER": "github", "GITHUB_APP_ID": "12345", "GITHUB_REPO": ""}
    settings.FRONTEND_URL = "http://127.0.0.1:5173"
    creds, _, _ = make_creds(installation_id=None)
    monkeypatch.setattr(github_views, "_app_credentials", lambda installation_id=None: creds)
    return creds


@pytest.mark.django_db
def test_connect_redirects_to_github_with_one_time_state(app_configured):
    resp = Client().get("/api/v1/github/connect")
    assert resp.status_code == 302
    loc = urlparse(resp["Location"])
    assert loc.netloc == "github.com" and loc.path == "/apps/autosre-zero-ops/installations/new"
    assert parse_qs(loc.query)["state"][0] == RuntimeConfig.load().github_install_state


@pytest.mark.django_db
def test_callback_rejects_forged_state_and_accepts_real_one(app_configured):
    c = Client()
    c.get("/api/v1/github/connect")
    forged = c.get("/api/v1/github/callback?installation_id=777&state=forged")
    assert "github=error" in forged["Location"]
    assert RuntimeConfig.load().github_installation_id is None

    state = RuntimeConfig.load().github_install_state
    good = c.get(f"/api/v1/github/callback?installation_id=777&setup_action=install&state={state}")
    assert good["Location"] == "http://127.0.0.1:5173/?github=connected"
    cfg = RuntimeConfig.load()
    assert (cfg.github_installation_id, cfg.github_account, cfg.github_install_state) == (777, "zero-ops", "")
    # state is single-use
    again = c.get(f"/api/v1/github/callback?installation_id=777&state={state}")
    assert "github=error" in again["Location"]


@pytest.mark.django_db
def test_status_reports_not_configured(settings):
    settings.DELIVERY = {**settings.DELIVERY, "PROVIDER": "github", "GITHUB_APP_ID": "", "GITHUB_TOKEN": ""}
    data = Client().get("/api/v1/github/status").json()["data"]
    assert data["auth_mode"] == "none" and data["connected"] is False and "GITHUB_APP_SETUP" in data["error"]
