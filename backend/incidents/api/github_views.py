"""
"Connect GitHub" flow for the AutoSRE GitHub App.

  1. GET  /github/connect   -> redirects the browser to GitHub's install page (with a
                               one-time `state` value to block forged callbacks)
  2. the user picks the repository on GitHub
  3. GET  /github/callback  -> GitHub sends the browser back here with installation_id;
                               we verify it belongs to OUR app and can see GITHUB_REPO,
                               save it, and redirect to the dashboard
  GET  /github/status       -> what is configured / connected (for the dashboard)
  POST /github/disconnect   -> forget the installation (uninstall it on GitHub to revoke)
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework.decorators import api_view

from delivery.github_auth import AppCredentials, GitHubAuthError, build_credentials

from ..models import AuditLog, RuntimeConfig
from .envelope import fail, ok

STATE_TTL = timedelta(minutes=15)


def _app_credentials(installation_id=None) -> AppCredentials:
    cfg = settings.DELIVERY
    if not cfg["GITHUB_APP_ID"]:
        raise GitHubAuthError("GITHUB_APP_ID is not set (see docs/GITHUB_APP_SETUP.md)")
    creds = build_credentials(cfg, installation_id)
    assert isinstance(creds, AppCredentials)
    return creds


def _back_to_dashboard(**params) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{settings.FRONTEND_URL.rstrip('/')}/?{urlencode(params)}")


@api_view(["GET"])
def github_status(request):
    cfg = settings.DELIVERY
    config = RuntimeConfig.load()
    data = {
        "provider": cfg["PROVIDER"],
        "repo": cfg["GITHUB_REPO"],
        "auth_mode": "app" if cfg["GITHUB_APP_ID"] else "token" if cfg["GITHUB_TOKEN"] else "none",
        "connected": False,
        "installation_id": config.github_installation_id,
        "account": config.github_account,
        "app": None,
        "token_expires_in_seconds": None,
        "error": None,
    }
    if data["auth_mode"] == "token":
        data["connected"] = bool(cfg["GITHUB_REPO"])
        return ok(data)
    if data["auth_mode"] == "none":
        data["error"] = "GitHub is not configured (see docs/GITHUB_APP_SETUP.md)"
        return ok(data)
    try:
        creds = _app_credentials(config.github_installation_id)
        data["app"] = creds.describe()
        if cfg["GITHUB_REPO"]:
            creds.token()  # proves the installation exists and can mint a token
            data["installation_id"] = creds.installation_id()
            data["connected"] = True
            data["token_expires_in_seconds"] = round(creds.token_expires_in() or 0)
    except GitHubAuthError as exc:
        data["error"] = str(exc)
    return ok(data)


@api_view(["GET"])
def github_connect(request):
    try:
        creds = _app_credentials()
        install_url = creds.describe()["install_url"]
    except GitHubAuthError as exc:
        return fail("GITHUB_APP_NOT_CONFIGURED", str(exc), 409)
    state = secrets.token_urlsafe(24)
    RuntimeConfig.objects.filter(pk=RuntimeConfig.load().pk).update(
        github_install_state=state, github_install_state_at=timezone.now())
    return HttpResponseRedirect(f"{install_url}?{urlencode({'state': state})}")


@api_view(["GET"])
def github_callback(request):
    config = RuntimeConfig.load()
    state = request.GET.get("state", "")
    fresh = config.github_install_state_at and timezone.now() - config.github_install_state_at < STATE_TTL
    if not state or not config.github_install_state or not secrets.compare_digest(state, config.github_install_state) or not fresh:
        return _back_to_dashboard(github="error", reason="invalid or expired connect request; click Connect GitHub again")
    try:
        installation_id = int(request.GET.get("installation_id", ""))
    except ValueError:
        return _back_to_dashboard(github="error", reason="GitHub did not send an installation id")
    try:
        creds = _app_credentials(installation_id)
        info = creds.verify_installation(installation_id)
        creds.token()  # can we mint a token for it?
        if settings.DELIVERY["GITHUB_REPO"]:
            owner, name = settings.DELIVERY["GITHUB_REPO"].split("/", 1)
            from github import Auth, Github

            Github(auth=Auth.Token(creds.token()), timeout=20).get_repo(f"{owner}/{name}").full_name
    except GitHubAuthError as exc:
        return _back_to_dashboard(github="error", reason=str(exc))
    except Exception as exc:  # repo not included in the installation
        return _back_to_dashboard(github="error", reason=f"the installation cannot access {settings.DELIVERY['GITHUB_REPO']}: {exc}")

    RuntimeConfig.objects.filter(pk=config.pk).update(
        github_installation_id=info["installation_id"], github_account=info["account"],
        github_install_state="", github_install_state_at=None)
    AuditLog.objects.create(kind="config", payload={"github_app_connected": info})
    return _back_to_dashboard(github="connected")


@api_view(["POST"])
def github_disconnect(request):
    config = RuntimeConfig.load()
    RuntimeConfig.objects.filter(pk=config.pk).update(github_installation_id=None, github_account="")
    AuditLog.objects.create(kind="config", payload={"github_app_disconnected": config.github_installation_id})
    return ok({"disconnected": True,
               "note": "To fully revoke access, uninstall the app on GitHub (Settings -> Applications)."})
