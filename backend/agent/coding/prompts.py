"""Instructions given to the coding agent. Everything sent is secret-scrubbed first (NFR-S2)."""
from __future__ import annotations

from guardrails.rules import scrub_secrets

SYSTEM_PROMPT = """You are AutoSRE's coding agent: a careful senior engineer fixing a production incident.
You work ONLY through the provided tools, inside a temporary copy of the repository on a fix branch.

Rules (enforced by code; violations are refused):
- You may modify only these existing files: {allowed_files}
- You may create new test files only matching: {test_globs}
- Keep the change minimal: at most {max_lines} changed lines in source files.
- No shell execution, destructive SQL, dynamic code execution or secrets.
- You have {max_attempts} run_tests attempts in total. Use them wisely.

Project: {language}. Checks: {checks}. Test command: {test_command}.
Be precise: copy old_text for edit_file exactly from read_file output (without the line-number prefix).
Always end by calling a tool; never just describe what you would do."""

FIX_TASK = """INCIDENT {incident_id}: {hypothesis}

Findings:
{findings}

Suspect commit {sha} by {author}: "{message}" (confidence {confidence})
Why it is suspected:
{evidence}

Most likely leaking code: {file} lines {start}-{end} ({function}).

Relevant files (already read for you; line numbers shown, do NOT copy the "NNNN | " prefix into edits):
{files}

Diff of the suspect commit:
```diff
{commit_diff}
```

Your job (be efficient: each turn is slow; you may call several tools in one turn):
1. Use the files above; read or search others only if you really need to.
2. Write a regression test in a NEW file that reproduces the bug — it must FAIL on the current code.
3. Make the smallest correct fix so resources are always released, even on errors.
4. run_tests. If something fails, read the output carefully and fix it.
5. When run_tests passes, call finish with a short summary and a risk rating."""

CONFLICT_TASK = """The fix branch for incident {incident_id} conflicts with the latest {base_branch}.
Teammates changed the same lines. Git has written conflict markers (<<<<<<<, =======, >>>>>>>) into:
{files}

What the fix was: {fix_summary}

What changed on {base_branch} since the fix branch was created:
```
{base_log}
```

Your job: in each conflicted file, combine BOTH sides correctly — keep the teammates' new behaviour AND keep
our fix (resources always released). Remove every conflict marker. Then run_tests, and finish when they pass."""

CI_TASK = """The pull request for incident {incident_id} has failing CI checks:
{failures}

Fix what is needed (within the allowed files), run_tests, and finish when they pass."""


def _clip(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + "\n... (truncated)"


def scrub(text: str, secret_values: list[str]) -> tuple[str, int]:
    return scrub_secrets(text, secret_values)


def system_prompt(profile, policy, max_attempts: int) -> str:
    return SYSTEM_PROMPT.format(
        allowed_files=", ".join(policy.allowed_files) or "(none)",
        test_globs=", ".join(policy.new_file_globs), max_lines=policy.max_changed_lines,
        max_attempts=max_attempts, language=profile.language,
        checks="; ".join(profile.checks) or "none", test_command=profile.test,
    )


def fix_task_prompt(incident_id: str, diagnosis: dict, suspect: dict, files: str = "") -> str:
    loc = suspect.get("location", {})
    commit = suspect.get("commit", {})
    return FIX_TASK.format(
        incident_id=incident_id,
        hypothesis=diagnosis.get("hypothesis", ""),
        findings="\n".join(f"- {f}" for f in diagnosis.get("findings", [])) or "- (none)",
        sha=commit.get("short_sha", "?"), author=commit.get("author", "?"), message=commit.get("message", ""),
        confidence=suspect.get("confidence", "?"),
        evidence="\n".join(f"- {e}" for e in suspect.get("evidence", [])),
        file=loc.get("file", "?"), start=loc.get("start_line", "?"), end=loc.get("end_line", "?"),
        function=loc.get("function") or "code block",
        files=files or f"```\n{_clip(loc.get('snippet', ''), 3000)}\n```",
        commit_diff=_clip(suspect.get("commit_diff", ""), 4000),
    )


def conflict_task_prompt(incident_id: str, base_branch: str, files: list[str], fix_summary: str, base_log: str) -> str:
    return CONFLICT_TASK.format(incident_id=incident_id, base_branch=base_branch,
                                files="\n".join(f"- {f}" for f in files), fix_summary=fix_summary or "(see diff)",
                                base_log=_clip(base_log, 2000))


def ci_task_prompt(incident_id: str, failures: str) -> str:
    return CI_TASK.format(incident_id=incident_id, failures=_clip(failures, 4000))
