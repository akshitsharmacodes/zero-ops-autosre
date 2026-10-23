"""
Delivery providers: where the fix branch is pushed and the pull request lives.

  * LocalProvider  — a bare git repo on this machine plays the role of GitHub, with
    pull requests stored as small JSON files. Lets the whole loop (including merge
    conflicts) run offline with no token.
  * GitHubProvider — real branches and draft PRs via the GitHub API (PyGithub).

Neither provider has a "merge" that AutoSRE calls. Humans merge (NFR-F1). The local
provider's merge exists only for the human "Merge" button in the dashboard.
"""
from __future__ import annotations

import base64
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from workspace.gitcmd import GitError, git
from workspace.workspace import Workspace

logger = logging.getLogger("autosre.delivery")


class DeliveryError(Exception):
    pass


@dataclass
class PRStatus:
    number: int
    url: str
    state: str  # open | closed | merged
    draft: bool
    mergeable: bool | None  # None = provider still computing
    conflicts: bool
    head_sha: str
    base_branch: str
    head_branch: str


@dataclass
class ChecksStatus:
    state: str  # none | pending | success | failure
    total: int = 0
    failures: list[dict] = field(default_factory=list)  # [{name, summary}]

    def failure_text(self) -> str:
        return "\n".join(f"- {f['name']}: {f.get('summary', '')}" for f in self.failures)


class DeliveryProvider(ABC):
    name: str

    @abstractmethod
    def clone_source(self) -> tuple[str, dict]:
        """(git URL or path, extra git environment for authentication)."""

    def push(self, ws: Workspace) -> None:
        source, env = self.clone_source()
        if ws.branch in ("main", "master", ws.base_branch):
            raise DeliveryError(f"refusing to push to protected branch '{ws.branch}'")
        git("push", "--quiet", "origin", f"HEAD:refs/heads/{ws.branch}", cwd=ws.root, env=env, timeout=120)

    @abstractmethod
    def open_pr(self, head: str, base: str, title: str, body: str, labels: list[str]) -> PRStatus: ...

    @abstractmethod
    def get_pr(self, number: int) -> PRStatus: ...

    @abstractmethod
    def checks(self, pr: PRStatus) -> ChecksStatus: ...

    @abstractmethod
    def mark_ready(self, number: int) -> None: ...

    @abstractmethod
    def comment(self, number: int, body: str) -> None: ...


# ---------------------------------------------------------------------------------------
class LocalProvider(DeliveryProvider):
    name = "local"
    _lock = threading.Lock()

    def __init__(self, origin_path: str | Path, store_dir: str | Path):
        self.origin = Path(origin_path)
        self.store = Path(store_dir)
        self.store.mkdir(parents=True, exist_ok=True)
        if not (self.origin / "HEAD").exists():
            raise DeliveryError(f"local origin repo not found at {self.origin} (run scripts/seed_victim_repo.py)")

    def clone_source(self) -> tuple[str, dict]:
        return str(self.origin), {}

    def _path(self, number: int) -> Path:
        return self.store / f"pr-{number}.json"

    def _load(self, number: int) -> dict:
        p = self._path(number)
        if not p.exists():
            raise DeliveryError(f"local PR #{number} not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def _save(self, data: dict) -> None:
        self._path(data["number"]).write_text(json.dumps(data, indent=2), encoding="utf-8")

    def open_pr(self, head, base, title, body, labels) -> PRStatus:
        with self._lock:
            existing = [json.loads(p.read_text(encoding="utf-8")) for p in self.store.glob("pr-*.json")]
            for pr in existing:
                if pr["head"] == head and pr["state"] == "open":
                    return self.get_pr(pr["number"])
            number = max((pr["number"] for pr in existing), default=0) + 1
            self._save({"number": number, "head": head, "base": base, "title": title, "body": body,
                        "labels": labels, "draft": True, "state": "open", "comments": [],
                        "created_at": datetime.now(timezone.utc).isoformat()})
        return self.get_pr(number)

    def get_pr(self, number) -> PRStatus:
        data = self._load(number)
        head_sha = self._rev(data["head"])
        conflicts = False
        if data["state"] == "open":
            # Would merging the branch into base conflict? Computed without touching any files.
            out = git("merge-tree", "--write-tree", "--name-only", "--no-messages", data["base"], data["head"],
                      cwd=self.origin, check=False)
            conflicts = len(out.strip().splitlines()) > 1
        return PRStatus(
            number=number, url=f"local://{self.origin.name}/pull/{number}", state=data["state"],
            draft=data["draft"], mergeable=None if data["state"] != "open" else not conflicts, conflicts=conflicts,
            head_sha=head_sha, base_branch=data["base"], head_branch=data["head"],
        )

    def checks(self, pr: PRStatus) -> ChecksStatus:
        return ChecksStatus(state="none")  # no external CI locally; AutoSRE's sandbox is the gate

    def mark_ready(self, number) -> None:
        data = self._load(number)
        data["draft"] = False
        self._save(data)

    def comment(self, number, body) -> None:
        data = self._load(number)
        data["comments"].append({"body": body, "at": datetime.now(timezone.utc).isoformat()})
        self._save(data)

    def human_merge(self, number: int, merged_by: str = "human reviewer") -> str:
        """Only for the dashboard's human 'Merge' button. AutoSRE itself never calls this."""
        data = self._load(number)
        status = self.get_pr(number)
        if status.state != "open" or status.conflicts:
            raise DeliveryError("PR is not open or has conflicts")
        tree = git("merge-tree", "--write-tree", data["base"], data["head"], cwd=self.origin).split()[0]
        base_sha, head_sha = self._rev(data["base"]), self._rev(data["head"])
        env = {"GIT_AUTHOR_NAME": merged_by, "GIT_AUTHOR_EMAIL": "reviewer@zero-ops.dev",
               "GIT_COMMITTER_NAME": merged_by, "GIT_COMMITTER_EMAIL": "reviewer@zero-ops.dev"}
        commit = git("commit-tree", tree, "-p", base_sha, "-p", head_sha, "-m",
                     f"Merge pull request #{number} from {data['head']}\n\n{data['title']}",
                     cwd=self.origin, env=env).strip()
        git("update-ref", f"refs/heads/{data['base']}", commit, base_sha, cwd=self.origin)
        data["state"], data["merged_by"] = "merged", merged_by
        self._save(data)
        return commit

    def _rev(self, ref: str) -> str:
        return git("rev-parse", ref, cwd=self.origin).strip()


# ---------------------------------------------------------------------------------------
class GitHubProvider(DeliveryProvider):
    name = "github"

    def __init__(self, token: str, repo: str, timeout: int = 20):
        if not token or not repo:
            raise DeliveryError("GITHUB_TOKEN and GITHUB_REPO must be set for GitHub delivery")
        from github import Auth, Github

        self.token = token
        self.repo_name = repo
        self.gh = Github(auth=Auth.Token(token), timeout=timeout, retry=2)
        self._repo = None

    @property
    def repo(self):
        if self._repo is None:
            self._repo = self.gh.get_repo(self.repo_name)
        return self._repo

    def clone_source(self) -> tuple[str, dict]:
        # The token travels in an HTTP header via environment config, never in the URL or
        # on the command line, so it can't leak into logs or `ps` output.
        basic = base64.b64encode(f"x-access-token:{self.token}".encode()).decode()
        env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
               "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}"}
        return f"https://github.com/{self.repo_name}.git", env

    def open_pr(self, head, base, title, body, labels) -> PRStatus:
        from github import GithubException

        try:
            for pr in self.repo.get_pulls(state="open", head=f"{self.repo.owner.login}:{head}"):
                return self.get_pr(pr.number)
            try:
                pr = self.repo.create_pull(title=title, body=body, head=head, base=base, draft=True)
            except GithubException as exc:
                if exc.status == 422 and "draft" in str(exc).lower():
                    pr = self.repo.create_pull(title=title, body=body, head=head, base=base)
                else:
                    raise
            self._label(pr, labels)
            return self.get_pr(pr.number)
        except GithubException as exc:
            raise DeliveryError(f"GitHub API error opening PR: {exc.status} {exc.data}") from exc

    def _label(self, pr, labels):
        from github import GithubException

        for name in labels:
            try:
                try:
                    self.repo.get_label(name)
                except GithubException:
                    self.repo.create_label(name, "0e8a16" if name == "verified" else "5319e7")
                pr.add_to_labels(name)
            except GithubException as exc:
                logger.warning("could not add label %s: %s", name, exc)

    def get_pr(self, number) -> PRStatus:
        from github import GithubException

        try:
            pr = self.repo.get_pull(number)
        except GithubException as exc:
            raise DeliveryError(f"GitHub API error reading PR #{number}: {exc.status}") from exc
        state = "merged" if pr.merged else pr.state
        return PRStatus(
            number=pr.number, url=pr.html_url, state=state, draft=pr.draft, mergeable=pr.mergeable,
            conflicts=pr.mergeable_state == "dirty" or pr.mergeable is False,
            head_sha=pr.head.sha, base_branch=pr.base.ref, head_branch=pr.head.ref,
        )

    def checks(self, pr: PRStatus) -> ChecksStatus:
        from github import GithubException

        try:
            commit = self.repo.get_commit(pr.head_sha)
            runs = list(commit.get_check_runs())
            statuses = list(commit.get_combined_status().statuses)
        except GithubException as exc:
            raise DeliveryError(f"GitHub API error reading checks: {exc.status}") from exc
        total = len(runs) + len(statuses)
        if total == 0:
            return ChecksStatus(state="none")
        failures, pending = [], False
        for run in runs:
            if run.status != "completed":
                pending = True
            elif run.conclusion in ("failure", "timed_out", "cancelled", "action_required"):
                out = run.output
                summary = " ".join(filter(None, [getattr(out, "title", None), getattr(out, "summary", None),
                                                 getattr(out, "text", None)]))[:3000]
                failures.append({"name": run.name, "summary": summary or run.conclusion, "url": run.html_url})
        for st in statuses:
            if st.state == "pending":
                pending = True
            elif st.state in ("failure", "error"):
                failures.append({"name": st.context, "summary": st.description or st.state, "url": st.target_url})
        state = "failure" if failures else "pending" if pending else "success"
        return ChecksStatus(state=state, total=total, failures=failures)

    def mark_ready(self, number) -> None:
        pr = self.repo.get_pull(number)
        if pr.draft:
            pr.mark_ready_for_review()

    def comment(self, number, body) -> None:
        self.repo.get_pull(number).create_issue_comment(body)


def get_provider() -> DeliveryProvider:
    from django.conf import settings

    cfg = settings.DELIVERY
    if cfg["PROVIDER"] == "github":
        return GitHubProvider(cfg["GITHUB_TOKEN"], cfg["GITHUB_REPO"])
    return LocalProvider(cfg["LOCAL_ORIGIN"], settings.VAR_DIR / "local_prs")


__all__ = ["DeliveryProvider", "LocalProvider", "GitHubProvider", "PRStatus", "ChecksStatus",
           "DeliveryError", "GitError", "get_provider", "asdict"]
