#!/usr/bin/env python3
"""
checkpoint.py — Snapshot or restore campaign state for mid-session recovery.

Usage:
  python scripts/checkpoint.py <campaign>
      Create a timestamped checkpoint of all character files and combat_state.json.

  python scripts/checkpoint.py <campaign> --restore
      Restore from the most recent checkpoint.

  python scripts/checkpoint.py <campaign> --list
      List all available checkpoints.

Checkpoints are stored in campaigns/<campaign>/.checkpoints/<timestamp>/
"""

import json
import os
import shutil
import sys
from datetime import datetime

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")


def campaign_dir(campaign: str) -> str:
    return os.path.join(BASE, campaign)


def checkpoints_dir(campaign: str) -> str:
    return os.path.join(campaign_dir(campaign), ".checkpoints")


def files_to_snapshot(campaign: str) -> list[str]:
    """Return list of file paths to include in a checkpoint."""
    camp_dir = campaign_dir(campaign)
    files = []

    # All character files (not subdirectories like npcs/)
    char_dir = os.path.join(camp_dir, "characters")
    if os.path.isdir(char_dir):
        for fname in os.listdir(char_dir):
            if fname.endswith(".md") and not fname.startswith("_"):
                files.append(os.path.join(char_dir, fname))

    # combat_state.json if it exists
    combat_state = os.path.join(camp_dir, "combat_state.json")
    if os.path.exists(combat_state):
        files.append(combat_state)

    return files


def cmd_create(campaign: str) -> None:
    camp_dir = campaign_dir(campaign)
    if not os.path.isdir(camp_dir):
        sys.exit(f"Error: campaign directory not found: {camp_dir}")

    snapfiles = files_to_snapshot(campaign)
    if not snapfiles:
        sys.exit("Error: no character files or combat_state.json found — nothing to checkpoint.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = os.path.join(checkpoints_dir(campaign), timestamp)
    os.makedirs(snap_dir, exist_ok=True)

    copied = []
    for src in snapfiles:
        # Preserve subdirectory structure relative to campaign root
        rel = os.path.relpath(src, camp_dir)
        dst = os.path.join(snap_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)

    # Write a manifest
    manifest_path = os.path.join(snap_dir, "MANIFEST.json")
    with open(manifest_path, "w") as f:
        json.dump({"timestamp": timestamp, "campaign": campaign, "files": copied}, f, indent=2)

    print(f"CHECKPOINT CREATED — {timestamp}")
    print(f"Location: {snap_dir}")
    print(f"Files saved ({len(copied)}):")
    for rel in sorted(copied):
        print(f"  {rel}")
    print(f"\nUse 'python scripts/checkpoint.py {campaign} --restore' to roll back.")


def cmd_restore(campaign: str) -> None:
    camp_dir = campaign_dir(campaign)
    chk_dir = checkpoints_dir(campaign)

    if not os.path.isdir(chk_dir):
        sys.exit("Error: no checkpoints found. Run without --restore first to create one.")

    snapshots = sorted(
        [d for d in os.listdir(chk_dir) if os.path.isdir(os.path.join(chk_dir, d))],
        reverse=True,
    )
    if not snapshots:
        sys.exit("Error: no checkpoints found.")

    latest = snapshots[0]
    snap_dir = os.path.join(chk_dir, latest)
    manifest_path = os.path.join(snap_dir, "MANIFEST.json")

    if not os.path.exists(manifest_path):
        sys.exit(f"Error: checkpoint manifest missing in {snap_dir}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"RESTORING FROM CHECKPOINT — {latest}")
    print(f"Source: {snap_dir}")

    restored = []
    for rel in manifest["files"]:
        src = os.path.join(snap_dir, rel)
        dst = os.path.join(camp_dir, rel)
        if not os.path.exists(src):
            print(f"  ⚠ {rel} — not found in checkpoint, skipping")
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        restored.append(rel)
        print(f"  ✓ {rel}")

    print(f"\nRestored {len(restored)}/{len(manifest['files'])} files.")


def cmd_list(campaign: str) -> None:
    chk_dir = checkpoints_dir(campaign)
    if not os.path.isdir(chk_dir):
        print("No checkpoints found.")
        return

    snapshots = sorted(
        [d for d in os.listdir(chk_dir) if os.path.isdir(os.path.join(chk_dir, d))],
        reverse=True,
    )
    if not snapshots:
        print("No checkpoints found.")
        return

    print(f"CHECKPOINTS — {campaign} ({len(snapshots)} total)")
    for snap in snapshots:
        manifest_path = os.path.join(chk_dir, snap, "MANIFEST.json")
        file_count = "?"
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                m = json.load(f)
            file_count = str(len(m.get("files", [])))
        marker = " ← most recent" if snap == snapshots[0] else ""
        print(f"  {snap}  ({file_count} files){marker}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    campaign = args[0]
    flag = args[1] if len(args) > 1 else ""

    if flag == "--restore":
        cmd_restore(campaign)
    elif flag == "--list":
        cmd_list(campaign)
    elif flag == "":
        cmd_create(campaign)
    else:
        sys.exit(f"Error: unknown flag '{flag}'. Use --restore or --list.")


if __name__ == "__main__":
    main()
