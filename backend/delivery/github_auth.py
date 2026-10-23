"""
How AutoSRE proves who it is to GitHub.

  * AppCredentials (recommended): AutoSRE is a GitHub App — its own robot identity
    (`<app-slug>[bot]`), installed only on the repositories you choose, with only the
    permissions you ticked. With its private key it signs a short-lived JWT, exchanges it
    for an installation token that expires after 1 hour, and quietly renews it.
  * TokenCredentials (fallback): a personal access token pasted into .env.

Neither the private key nor any token is ever logged or sent to the LLM.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("autosre.github")

# Exactly what AutoSRE needs; installation tokens are down-scoped to this list.
REQUIRED_PERMISSIONS = {
    "contents": "write",        # push the fix branch
    "pull_requests": "write",   # open the PR, mark it ready, comment, label
    "checks": "read",           # read CI check runs
    "statuses": "read",         # read commit statuses
    "metadata": "read",         # mandatory for every GitHub App
}
RENEW_BEFORE_SECONDS = 300


class GitHubAuthError(Exception):
    pass


class TokenCredentials:
    mode = "token"

    def __init__(self, token: str):
        if not token:
            raise GitHubAuthError("GITHUB_TOKEN is empty")
        self._token = token

    def token(self) -> str:
        return self._token

    def identity(self) -> tuple[str, str] | None:
        return None  # commits use the generic "AutoSRE Bot" identity

    def describe(self) -> dict:
        return {"mode": self.mode}


class AppCredentials:
    mode = "app"

    def __init__(self, app_id: str | int, private_key: str, repo: str, installation_id: int | None = None,
                 integration=None, clock=time.time, http_get=None):
        if not app_id or not private_key:
            raise GitHubAuthError("GitHub App ID and private key are required")
        if "/" not in repo:
            raise GitHubAuthError("GITHUB_REPO must look like 'owner/name'")
        if integration is None:
            from github import Auth, GithubIntegration

            integration = GithubIntegration(auth=Auth.AppAuth(app_id, private_key))
        self.app_id = str(app_id)
        self.repo = repo
        self._integration = integration
        self._installation_id = int(installation_id) if installation_id else None
        self._clock = clock
        self._http_get = http_get
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at = 0.0
        self._app: dict | None = None
        self._identity: tuple[str, str] | None = None

    # -- app + installation -----------------------------------------------------------
    def app_info(self) -> dict:
        if self._app is None:
            try:
                app = self._integration.get_app()
            except Exception as exc:
                raise GitHubAuthError(f"GitHub rejected the App credentials (check App ID and private key): {exc}") from exc
            self._app = {"id": str(app.id), "slug": app.slug, "name": app.name, "html_url": app.html_url}
        return self._app

    def installation_id(self) -> int:
        if self._installation_id is None:
            owner, name = self.repo.split("/", 1)
            try:
                self._installation_id = int(self._integration.get_repo_installation(owner, name).id)
            except Exception as exc:
                raise GitHubAuthError(
                    f"the GitHub App is not installed on {self.repo}; click 'Connect GitHub' and pick that repository"
                ) from exc
        return self._installation_id

    def verify_installation(self, installation_id: int) -> dict:
        """Check an installation id (from the install callback) belongs to THIS app."""
        try:
            inst = self._integration.get_app_installation(int(installation_id))
        except Exception as exc:
            raise GitHubAuthError(f"installation {installation_id} not found for this App") from exc
        if str(inst.app_id) != self.app_id:
            raise GitHubAuthError("installation belongs to a different GitHub App")
        account = getattr(inst.account, "login", "") if inst.account else ""
        return {"installation_id": int(inst.id), "account": account,
                "repository_selection": getattr(inst, "repository_selection", "")}

    # -- tokens --------------------------------------------------------------------------
    def token(self) -> str:
        with self._lock:
            if self._token and self._expires_at - self._clock() > RENEW_BEFORE_SECONDS:
                return self._token
            inst = self.installation_id()
            try:
                auth = self._integration.get_access_token(inst, permissions=REQUIRED_PERMISSIONS)
            except Exception as exc:
                logger.warning("down-scoped token request failed (%s); retrying with the App's own permissions", exc)
                try:
                    auth = self._integration.get_access_token(inst)
                except Exception as exc2:
                    raise GitHubAuthError(f"could not get an installation token: {exc2}") from exc2
            expires = auth.expires_at
            if isinstance(expires, datetime):
                expires = (expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)).timestamp()
            self._token, self._expires_at = auth.token, float(expires or self._clock() + 3600)
            logger.info("obtained GitHub App installation token (valid %.0f min)",
                        (self._expires_at - self._clock()) / 60)
            return self._token

    def token_expires_in(self) -> float | None:
        return (self._expires_at - self._clock()) if self._token else None

    # -- commit identity ------------------------------------------------------------------
    def identity(self) -> tuple[str, str] | None:
        """Commits are authored by the bot itself, so GitHub shows them as `<slug>[bot]`."""
        if self._identity is None:
            slug = self.app_info()["slug"]
            login = f"{slug}[bot]"
            email = f"{login}@users.noreply.github.com"
            try:
                get = self._http_get or _default_get
                user_id = get(f"https://api.github.com/users/{login}")["id"]
                email = f"{user_id}+{login}@users.noreply.github.com"
            except Exception:
                pass
            self._identity = (login, email)
        return self._identity

    def describe(self) -> dict:
        info = self.app_info()
        return {"mode": self.mode, "app_slug": info["slug"], "app_name": info["name"],
                "bot_login": f"{info['slug']}[bot]",
                "install_url": f"https://github.com/apps/{info['slug']}/installations/new"}


def _default_get(url: str) -> dict:
    import requests

    resp = requests.get(url, timeout=10, headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    return resp.json()


def load_private_key(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise GitHubAuthError(f"GitHub App private key not found at {p}")
    text = p.read_text(encoding="utf-8")
    if "PRIVATE KEY" not in text:
        raise GitHubAuthError(f"{p} does not look like a PEM private key")
    return text


def build_credentials(cfg: dict, installation_id: int | None = None):
    """App credentials when an App ID + key are configured, else the personal token fallback."""
    if cfg.get("GITHUB_APP_ID"):
        key = load_private_key(cfg["GITHUB_APP_PRIVATE_KEY_PATH"])
        return AppCredentials(cfg["GITHUB_APP_ID"], key, cfg["GITHUB_REPO"],
                              installation_id or cfg.get("GITHUB_APP_INSTALLATION_ID") or None)
    if cfg.get("GITHUB_TOKEN"):
        return TokenCredentials(cfg["GITHUB_TOKEN"])
    raise GitHubAuthError("GitHub is not configured: set GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY_PATH "
                          "(recommended) or GITHUB_TOKEN")
