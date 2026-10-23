"""
Guardrails: rules the AI cannot break, enforced by plain code (Section 8 of the SRS).

They are used in two places:
  * inside the coding agent's tools — a forbidden edit is refused immediately and the
    agent is told why, so it must find another way;
  * as a full gate on the final change before it is tested and delivered.
"""
from __future__ import annotations

import ast
import fnmatch
import re
from dataclasses import asdict, dataclass, field

from workspace.gitcmd import FileDiff

# --- secrets (NFR-S2, TC-14) -------------------------------------------------------
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b")),
    ("GitHub token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Groq API key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("NVIDIA API key", re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    ("credentials in URL", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:/@]+:[^\s@/]+@")),
    ("password/secret assignment", re.compile(
        r"""(?i)\b(password|passwd|pwd|secret|api_?key|access_?token|auth_?token)\b(\s*[:=]\s*)(["'])[^"'\n]{6,}\3""")),
]


def scrub_secrets(text: str, extra_values: list[str] | None = None) -> tuple[str, int]:
    """Replace anything that looks like a secret with [REDACTED]. Returns (text, count)."""
    count = 0
    for value in extra_values or []:
        if value and len(value) >= 6 and value in text:
            count += text.count(value)
            text = text.replace(value, "[REDACTED]")
    for _, pattern in SECRET_PATTERNS:
        def _sub(m):
            nonlocal count
            count += 1
            if m.lastindex and m.lastindex >= 3:  # keep the variable name for readability
                return f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(3)}"
            return "[REDACTED]"
        text = pattern.sub(_sub, text)
    return text, count


# --- personal data (AI ethics: minimise what leaves the machine) -----------------------------
PII_PATTERNS = [
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    ("IP address", re.compile(r"\b(?!127\.0\.0\.1\b)(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b"), "[IP]"),
    ("card-like number", re.compile(r"\b(?:\d[ -]?){13,16}\b"), "[NUMBER]"),
]


def scrub_pii(text: str) -> tuple[str, int]:
    """Replace personal data (emails, IPs, card-like numbers) before text is sent to an LLM."""
    count = 0
    for _, pattern, placeholder in PII_PATTERNS:
        text, n = pattern.subn(placeholder, text)
        count += n
    return text, count


def find_secrets(text: str) -> list[str]:
    return [label for label, pattern in SECRET_PATTERNS if pattern.search(text)]


# --- dangerous code (TC-11) --------------------------------------------------------
DANGEROUS_PATTERNS = [
    ("shell execution (os.system)", re.compile(r"\bos\.(system|popen|exec[lv]p?e?)\s*\(")),
    ("subprocess execution", re.compile(r"\bsubprocess\b")),
    ("child process (Node)", re.compile(r"\bchild_process\b")),
    ("os/exec (Go)", re.compile(r'"os/exec"')),
    ("dynamic code execution", re.compile(r"(?<![\w.])(eval|exec)\s*\(")),
    ("dynamic import", re.compile(r"\b__import__\s*\(")),
    ("recursive delete", re.compile(r"\bshutil\.rmtree\b|\brm\s+-rf\b")),
    ("DROP statement", re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|INDEX|USER|ROLE)\b", re.I)),
    ("DELETE statement", re.compile(r"\bDELETE\s+FROM\b", re.I)),
    ("TRUNCATE statement", re.compile(r"\bTRUNCATE\s+(TABLE\s+)?\w", re.I)),
    ("privilege change", re.compile(r"\b(GRANT|REVOKE)\s+\w+.*\bON\b", re.I)),
    ("unsafe deserialization", re.compile(r"\bpickle\.loads?\b|\byaml\.load\s*\((?![^)]*Loader=yaml\.SafeLoader)")),
    ("world-writable permissions", re.compile(r"\bchmod\s+777\b|0o?777\b")),
]


def find_dangerous(added_lines: list[str]) -> list[str]:
    text = "\n".join(added_lines)
    return [label for label, pattern in DANGEROUS_PATTERNS if pattern.search(text)]


# --- policy ------------------------------------------------------------------------
@dataclass
class GuardrailPolicy:
    allowed_files: list[str]  # existing files the agent may modify (from correlation)
    new_file_globs: list[str]  # where NEW files (regression tests) may be created
    max_changed_lines: int = 50  # in source files (NFR-F2)
    max_new_test_lines: int = 150
    protected_branches: tuple[str, ...] = ("main", "master")
    secret_values: list[str] = field(default_factory=list)

    def is_allowed_existing(self, path: str) -> bool:
        return path in self.allowed_files

    def is_allowed_new(self, path: str) -> bool:
        return any(fnmatch.fnmatch(path, g) for g in self.new_file_globs)


@dataclass
class CheckResult:
    id: str
    name: str
    passed: bool
    details: str

    def as_dict(self) -> dict:
        return asdict(self)


def check_edit(policy: GuardrailPolicy, path: str, before: str | None, after: str) -> list[str]:
    """Quick check used by the agent's edit/write tools. Returns reasons for refusal."""
    problems = []
    if before is None:
        if not policy.is_allowed_new(path):
            problems.append(f"creating '{path}' is not allowed; new files may only match {policy.new_file_globs}")
    elif not policy.is_allowed_existing(path) and not policy.is_allowed_new(path):
        problems.append(f"'{path}' is outside the allowlist {policy.allowed_files} (files from the suspect commit)")
    before_lines = set((before or "").splitlines())
    added = [line for line in after.splitlines() if line not in before_lines]
    dangerous = find_dangerous(added)
    if dangerous:
        problems.append(f"added code contains blocked patterns: {', '.join(dangerous)}")
    secrets = find_secrets("\n".join(added))
    if secrets:
        problems.append(f"added code contains secret-like values: {', '.join(secrets)}")
    return problems


def evaluate_change(policy: GuardrailPolicy, changes: dict[str, FileDiff], files_after: dict[str, str]) -> list[CheckResult]:
    """Full gate on the complete change (all files) before sandbox and delivery."""
    source = {p: fd for p, fd in changes.items() if not (fd.is_new and policy.is_allowed_new(p))}
    tests = {p: fd for p, fd in changes.items() if p not in source}
    src_lines = sum(fd.changed_lines for fd in source.values())
    test_lines = sum(fd.changed_lines for fd in tests.values())
    added = [t for fd in changes.values() for _, t in fd.added]

    results = [CheckResult(
        "diff_size", f"Diff size (<= {policy.max_changed_lines} changed lines)",
        src_lines <= policy.max_changed_lines and test_lines <= policy.max_new_test_lines,
        f"{src_lines} changed line(s) in source files, {test_lines} in new test files "
        f"(limits {policy.max_changed_lines} / {policy.max_new_test_lines}).",
    )]

    outside = [p for p in source if not policy.is_allowed_existing(p)]
    deleted = [p for p, fd in changes.items() if fd.is_deleted]
    results.append(CheckResult(
        "file_allowlist", "File allowlist (suspect commit scope)", not outside and not deleted,
        f"Touched: {', '.join(sorted(changes)) or 'nothing'}. "
        + (f"Not allowed: {', '.join(outside + deleted)}." if outside or deleted else "All within scope."),
    ))

    secrets = find_secrets("\n".join(added))
    results.append(CheckResult(
        "secret_scan", "No secrets in patch", not secrets,
        f"Found: {', '.join(secrets)}." if secrets else "No credentials or keys found in added lines.",
    ))

    dangerous = find_dangerous(added)
    results.append(CheckResult(
        "dangerous_patterns", "Dangerous pattern blocklist", not dangerous,
        f"Blocked: {', '.join(dangerous)}." if dangerous else "No shell execution, destructive SQL or dynamic code.",
    ))

    syntax_errors = []
    for path, text in files_after.items():
        if path.endswith(".py"):
            try:
                ast.parse(text)
            except SyntaxError as exc:
                syntax_errors.append(f"{path}:{exc.lineno}: {exc.msg}")
    results.append(CheckResult(
        "syntax", "Changed files parse", not syntax_errors,
        "; ".join(syntax_errors) if syntax_errors else "All changed source files parse.",
    ))
    markers = [p for p, text in files_after.items() if CONFLICT_MARKER.search(text)]
    if markers:
        results.append(CheckResult("conflict_markers", "No leftover merge-conflict markers", False,
                                   f"Conflict markers still present in: {', '.join(markers)}."))
    if not changes:
        results.append(CheckResult("non_empty", "Change is not empty", False, "No files were changed."))
    return results


CONFLICT_MARKER = re.compile(r"^(<{7} |>{7} |={7}$)", re.M)


def branch_check(policy: GuardrailPolicy, branch: str) -> CheckResult:
    ok = branch not in policy.protected_branches
    return CheckResult(
        "human_gate", "No direct push to main; human merges", ok,
        f"Changes go to '{branch}' via a draft pull request; AutoSRE never merges." if ok
        else f"Refused: '{branch}' is protected.",
    )
