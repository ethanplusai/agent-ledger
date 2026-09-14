#!/usr/bin/env python3
"""Fail on common private artifacts/secrets in the prospective Git publication set."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'personal absolute path': re.compile(rb'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'Windows personal path': re.compile(rb'[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+\\'),
    'API key-shaped value': re.compile(rb'\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b'),
    'GitHub token-shaped value': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
}


def main():
    result = subprocess.run(['git','ls-files','-z','--cached','--others','--exclude-standard'], cwd=ROOT, capture_output=True, check=True)
    failures=[]; count=0
    for raw in set(result.stdout.split(b'\0')):
        if not raw: continue
        relative=raw.decode('utf-8');path=ROOT/relative
        if not path.is_file(): continue
        count+=1
        if path.is_symlink():
            failures.append((relative,'symlink requires review'));continue
        if path.suffix in ('.jsonl','.sqlite','.sqlite3','.db','.log') or path.name.startswith('.env'):
            failures.append((relative,'private artifact file type'));continue
        if path.suffix in ('.png','.gif') and relative.startswith('docs/screenshots/demo-'):
            continue  # Only manually inspected synthetic screenshots and recordings are allowed.
        data=path.read_bytes()
        if b'\0' in data:
            failures.append((relative,'unexpected binary'));continue
        for label,pattern in PATTERNS.items():
            if pattern.search(data):failures.append((relative,label))
    for path,label in failures:print(f'REVIEW: {path}: {label}')  # Never echo a suspected secret.
    print(f'Checked {count} prospective publication files; {len(failures)} findings.')
    return bool(failures)


if __name__=='__main__':raise SystemExit(main())
