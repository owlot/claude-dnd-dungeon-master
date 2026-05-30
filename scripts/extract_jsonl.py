#!/usr/bin/env python3
"""
extract_jsonl.py — Extract a clean conversation transcript from a Claude project JSONL file.

Usage:
  python3 .claude/scripts/extract_jsonl.py <campaign> [--session N]

  e.g.  python3 .claude/scripts/extract_jsonl.py waterdeep-dragon-heist
        python3 .claude/scripts/extract_jsonl.py waterdeep-dragon-heist --session 8

Selection logic:
  1. Derives the project slug from the current working directory:
       /home/user/Git/d&d/my-project  →  -home-user-Git-d-d-my-project
  2. If --session N is given, searches for the file containing both
     'dm-start-session' and 'session N' (e.g. 'session 8'). If multiple match,
     picks the smallest (most focused) file.
  3. Without --session, searches for 'dm-start-session' and picks the largest match.
  4. Falls back to the largest .jsonl file modified today if no match found.
  5. Exits with an error if no .jsonl files are found.

Output:
  Prints the clean transcript to stdout — for each message, a [ROLE] header
  followed by the text content. Non-text blocks (tool_use, tool_result, etc.)
  are skipped. The selected JSONL path is printed to stderr.
"""

import json
import os
import re
import sys
from datetime import date
from pathlib import Path


def derive_project_slug(cwd: str) -> str:
    """
    Convert an absolute path to a Claude project slug.

    Claude Code replaces every character that is not a letter, digit, or hyphen
    with a hyphen. Example:
      /home/user/Git/d&d/my-project  →  -home-user-Git-d-d-my-project
    """
    return re.sub(r"[^a-zA-Z0-9\-]", "-", cwd)


def find_jsonl_dir(slug: str) -> Path:
    """Return the ~/.claude/projects/<slug>/ directory, or raise if not found."""
    projects_dir = Path.home() / ".claude" / "projects" / slug
    if not projects_dir.is_dir():
        sys.exit(
            f"Error: project directory not found: {projects_dir}\n"
            f"Expected slug derived from cwd: {slug}"
        )
    return projects_dir


def collect_jsonl_files(jsonl_dir: Path) -> list[Path]:
    """Return all .jsonl files in the directory, sorted largest-first."""
    files = sorted(
        jsonl_dir.glob("*.jsonl"), key=lambda p: p.stat().st_size, reverse=True
    )
    if not files:
        sys.exit(f"Error: no .jsonl files found in {jsonl_dir}")
    return files


def file_contains(path: Path, needle: str) -> bool:
    """Return True if any line in the file contains the needle string."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if needle in line:
                    return True
    except OSError:
        pass
    return False


def select_jsonl(jsonl_dir: Path, session: int | None = None) -> Path:
    """
    Pick the best .jsonl file:
      - If session N given: file containing 'dm-start-session' AND 'session N'
        (case-insensitive). If multiple match, picks the smallest (most focused).
      - Without session: file containing 'dm-start-session', largest if multiple.
      - Fallback: largest file modified today.
    """
    all_files = collect_jsonl_files(jsonl_dir)

    if session is not None:
        # Narrow by session number.
        #
        # Strategy 1: look for files containing 'dm-start-session' AND an explicit
        # "start session N" phrase (typed by the DM). This works when the DM said
        # something like "let's start session 8" in the conversation.
        needles = ["dm-start-session", f"start session {session}"]
        matches = [
            f for f in all_files if all(file_contains(f, needle) for needle in needles)
        ]
        if matches:
            # Pick smallest — a session-specific file won't be the largest
            return sorted(matches, key=lambda p: p.stat().st_size)[0]

        # Strategy 2: find files where dm-start-session was actually invoked as a
        # command — either via the new <command-name> tag or the old skill body
        # format ("Base directory for this skill: .../dm-start-session"). These
        # are the true session files. Rank them chronologically and pick the Nth.
        def is_session_invocation(path: Path) -> bool:
            return file_contains(
                path, "<command-name>dm-start-session"
            ) or file_contains(path, "skills/dm-start-session")

        command_files = sorted(
            [f for f in all_files if is_session_invocation(f)],
            key=lambda p: p.stat().st_mtime,
        )
        if len(command_files) >= session:
            candidate = command_files[session - 1]
            print(
                f"Note: matched session {session} by chronological order of "
                f"dm-start-session invocations "
                f"(file {session} of {len(command_files)}).",
                file=sys.stderr,
            )
            return candidate

        print(
            f"Warning: could not match session {session} by text or invocation order. "
            "Falling back to largest file containing 'dm-start-session'.",
            file=sys.stderr,
        )

    # Primary: contains 'dm-start-session', largest match
    matches = [f for f in all_files if file_contains(f, "dm-start-session")]
    if matches:
        return matches[0]  # all_files sorted largest-first

    # Fallback: largest file modified today
    today = date.today()
    today_files = [
        f for f in all_files if date.fromtimestamp(f.stat().st_mtime) == today
    ]
    if today_files:
        return today_files[0]

    # Last resort: just the largest file overall
    print(
        "Warning: no file contains 'dm-start-session' and none were modified today. "
        "Using the largest .jsonl file.",
        file=sys.stderr,
    )
    return all_files[0]


def extract_transcript(path: Path) -> None:
    """Parse the JSONL and print a clean [ROLE] / text transcript to stdout."""
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            msg = obj.get("message", {})
            if not isinstance(msg, dict):
                continue

            role = msg.get("role", "unknown").upper()
            contents = msg.get("content", [])

            # content can be a plain string (older format) or a list of blocks
            if isinstance(contents, str):
                contents = [{"type": "text", "text": contents}]

            text_parts: list[str] = []
            for block in contents:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)

            if not text_parts:
                continue

            print(f"[{role}]")
            for part in text_parts:
                print(part)
            print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    # campaign argument is accepted but not used directly in path logic;
    # the project is identified by cwd → slug, matching how Claude Code works.
    _campaign = sys.argv[1]

    # Parse optional arguments
    session: int | None = None
    explicit_file: Path | None = None
    args = sys.argv[2:]

    if "--file" in args:
        idx = args.index("--file")
        try:
            explicit_file = Path(args[idx + 1])
            if not explicit_file.is_file():
                sys.exit(f"Error: --file path not found: {explicit_file}")
        except IndexError:
            sys.exit("Error: --file requires a path argument")

    if "--session" in args:
        idx = args.index("--session")
        try:
            session = int(args[idx + 1])
        except (IndexError, ValueError):
            sys.exit("Error: --session requires an integer argument, e.g. --session 8")

    if explicit_file is not None:
        print(f"[extract_jsonl] using: {explicit_file}", file=sys.stderr)
        extract_transcript(explicit_file)
        return

    cwd = os.getcwd()
    slug = derive_project_slug(cwd)
    jsonl_dir = find_jsonl_dir(slug)
    selected = select_jsonl(jsonl_dir, session=session)

    print(f"[extract_jsonl] using: {selected}", file=sys.stderr)

    extract_transcript(selected)


if __name__ == "__main__":
    main()
