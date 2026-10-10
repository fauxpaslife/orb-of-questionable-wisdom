"""Build and audit a portable source ZIP; never zip the working directory wholesale."""
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PACKAGE = "Orb_of_Questionable_Wisdom"
FILES = (
    "README.md", "requirements.txt", "requirements-dev.txt", ".gitignore",
    "install.bat", "install.py", "start.bat", "launch.py", "config.py",
    "server.py", "oracle_client.py", "voice_client.py", "db.py", "discovery.py", "quips.py",
    "static/index.html", "static/style.css", "static/ui.js", "static/shake.js", "static/orb-fx.js", "static/share-card.js", "static/sound.js",
    "test_core.py", "test_install.py", "browser_check.py", "build_release.py",
    "docs/images/settings.png", "docs/images/ask-later.png", "docs/images/definitely.png",
)
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,})\b"),
    "OpenAI-style secret": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "credential assignment": re.compile(r'''(?im)^\s*["']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["'][^"'\r\n]{8,}["']'''),
    "credential in URL": re.compile(r"https?://[^\s/@:]+:[^\s/@]+@"),
    "personal Windows path": re.compile(r"(?i)\b[A-Z]:[/\\](?:Users|Documents and Settings)[/\\][^\s\"']+"),
    "private workspace path": re.compile(r"(?i)\b[A-Z]:[/\\]Ollama[/\\]"),
}


def audit(contents):
    findings = []
    for name, data in contents.items():
        if name.endswith('.png'):
            if not data.startswith(b'\x89PNG\r\n\x1a\n'):
                raise RuntimeError(f"Invalid PNG asset: {name}")
            continue
        text = data.decode("utf-8")
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                # Report locations, never copy credential values into console output or reports.
                findings.append({"file": name, "line": text.count("\n", 0, match.start()) + 1, "kind": kind})
    return findings


def build(root=ROOT, output=None):
    root = Path(root)
    output = Path(output) if output else root / "dist" / (PACKAGE + "-P2.zip")
    contents = {}
    for name in FILES:
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"Release source is missing or a symbolic link: {name}")
        contents[name] = source.read_bytes()
    findings = audit(contents)
    if findings:
        raise RuntimeError("Release audit needs review: " + json.dumps(findings))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in contents.items():
            archive.writestr(PACKAGE + "/" + name, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("The generated ZIP failed its integrity check.")
        expected = {PACKAGE + "/" + name for name in FILES}
        if set(archive.namelist()) != expected:
            raise RuntimeError("Unexpected release archive contents.")
        if audit({name: archive.read(name) for name in archive.namelist()}):
            raise RuntimeError("The generated ZIP failed its content audit.")
    report = {"archive": output.name, "file_count": len(contents), "bytes": output.stat().st_size, "credential_findings": [], "personal_path_findings": [], "excluded": [".venv", "data", "__pycache__", "test-artifacts", "benchmark reports/results", "logs", ".env files", "key files"]}
    output.with_suffix(".audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return output, report


if __name__ == "__main__":
    path, report = build()
    print(json.dumps(report, indent=2))
    print("Release ZIP ready in dist/.")
