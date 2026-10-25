"""Guard against accidentally tracking and publishing secrets.

Only prints matched file paths and signature names, never matched values.
Runs on every ordinary Calendar Integrity Tests PR job.
"""

from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ASSETS = (
    "index.html", "sw.js", "manifest.json", "icon-180.png",
    "icon-192.png", "icon-512.png", "manual-events.js",
    "verified-schedule.js", "events.json", "manual_events.json",
    "verified_schedule.json", "event-policy.json", "update-meta.json",
)
TEXT_EXTENSIONS = frozenset({
    ".html", ".js", ".json", ".py", ".md", ".txt", ".yml", ".yaml",
    ".xml", ".sh", ".ini", ".toml", ".cfg",
})
SENSITIVE_EXTENSIONS = (
    ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore",
    ".kdbx", ".db", ".sqlite", ".sqlite3",
)
SENSITIVE_BASENAMES = {
    "credentials.json", "secrets.json", "id_rsa", "id_rsa.pub",
    "id_ed25519", "id_ed25519.pub",
}
SIGNATURES = {
    "GitHub access token": re.compile(
        r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    ),
    "OpenAI API key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{24,}"),
    "AWS access key ID": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key block": re.compile(
        r"-----BEGIN\s+(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "privileged credential assignment": re.compile(
        r"""\b(?:SERVICE_ROLE_KEY|CLIENT_SECRET|PRIVATE_API_KEY)\b\s*[:=]\s*["'][^"']{12,}["']""",
        re.IGNORECASE,
    ),
}


def tracked_paths():
    result = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [Path(p.decode("utf-8", "surrogateescape")) for p in result.split(b"\0") if p]


def unsafe_filename(path):
    parts = [p.lower() for p in path.parts]
    basename = parts[-1]
    if any(p == ".env" or p.startswith(".env.") or p.endswith(".env")
           or ".env." in p for p in parts):
        return True
    if basename in SENSITIVE_BASENAMES:
        return True
    if "service-account" in basename or "service_account" in basename:
        return True
    if any(basename.endswith(ext) for ext in SENSITIVE_EXTENSIONS):
        return True
    return False


def signature_labels(source):
    return [label for label, regex in SIGNATURES.items() if regex.search(source)]


class RepositoryPublicationSafetyTests(unittest.TestCase):
    def test_no_sensitive_tracked_files_or_key_signatures(self):
        problems = []
        for path in tracked_paths():
            if unsafe_filename(path):
                problems.append(f"{path.as_posix()}: disallowed filename")
            if path.suffix.lower() not in TEXT_EXTENSIONS and path.name != ".gitignore":
                continue
            source = (ROOT / path).read_text(encoding="utf-8")
            for label in signature_labels(source):
                problems.append(f"{path.as_posix()}: {label}")
        self.assertEqual(problems, [], "Sensitive items detected; values are suppressed")

    def test_local_sensitive_artifacts_are_gitignored(self):
        samples = (
            ".env", ".env.production", "config/.env.local",
            "secret.env", "private.pem", "credentials.json",
            "secrets.json", "keys/service-account-prod.json",
            "backup.sqlite3", "node_modules/package/index.js",
            ".venv/lib/module.py", "test-results/results.xml",
        )
        for path in samples:
            with self.subTest(path=path):
                result = subprocess.run(
                    ["git", "check-ignore", "--no-index", "--quiet", "--", path],
                    cwd=ROOT, check=False, capture_output=True,
                )
                self.assertEqual(result.returncode, 0, f"Not ignored: {path}")

    def test_expected_public_app_files_remain_tracked(self):
        names = {path.as_posix() for path in tracked_paths()}
        self.assertEqual(
            set(PUBLIC_ASSETS) - names, set(),
            "Expected public assets are missing from git",
        )

    def test_signature_detection_with_generated_dummy_values(self):
        samples = {
            "GitHub access token": "ghp_" + "A" * 30,
            "OpenAI API key": "sk-" + "A" * 32,
            "AWS access key ID": "AKIA" + "A" * 16,
            "private key block": "-----BEGIN " + "PRIVATE KEY-----",
            "privileged credential assignment":
                "SERVICE_ROLE_KEY" + " = '" + "A" * 20 + "'",
        }
        for kind, sample in samples.items():
            with self.subTest(signature=kind):
                self.assertIn(kind, signature_labels(sample))


if __name__ == "__main__":
    unittest.main()
