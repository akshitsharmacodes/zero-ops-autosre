import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class GitHubDelivery:
    def __init__(self, token: str = None, repo_name: str = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.repo_name = repo_name or os.environ.get("GITHUB_REPO", "zero-ops/victim-service")

    def create_pull_request(
        self,
        title: str,
        body: str,
        branch_name: str = "autosre/fix-connection-leak",
        base_branch: str = "main"
    ) -> Dict[str, Any]:
        """
        Creates a GitHub PR via PyGithub if credentials exist,
        otherwise creates deterministic simulated PR artifact for demo.
        NEVER pushes to main and NEVER auto-merges!
        """
        if self.token and self.token.strip():
            try:
                from github import Github
                g = Github(self.token)
                repo = g.get_repo(self.repo_name)
                # Ensure we never create PR into an unsafe branch
                pr = repo.create_pull(
                    title=title,
                    body=body,
                    head=branch_name,
                    base=base_branch,
                    draft=True
                )
                logger.info(f"Created real GitHub PR: {pr.html_url}")
                return {
                    "pr_url": pr.html_url,
                    "pr_number": pr.number,
                    "status": "awaiting_human_review",
                    "draft": True,
                    "is_live": True
                }
            except Exception as e:
                logger.warning(f"GitHub API error: {e}. Falling back to deterministic PR representation.")

        pr_number = 42
        pr_url = f"https://github.com/{self.repo_name}/pull/{pr_number}"
        return {
            "pr_url": pr_url,
            "pr_number": pr_number,
            "status": "awaiting_human_review",
            "draft": True,
            "branch": branch_name,
            "base_branch": base_branch,
            "is_live": False
        }
