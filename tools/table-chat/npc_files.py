"""Reads an NPC file and builds the NPC's prompt for table chat.

An NPC knows only its NPC file and its own past conversations, so the prompt is built from
`info/npcs/[slug].md` (the `character`, `voice`, `background`, `behavior` and `location` sections) and
`party/npc-memory/[slug].md`. `## who knows them`, `## image` and `## stats` are left out on purpose.
"""

import re

KEEP = ("character", "voice", "background", "behavior", "location")

DEFAULT_INTRO = ("I don't usually talk to strangers about things that aren't my business. "
                 "But you asked, so. Make it quick.")


def sections(text):
    """{lower-case heading: body} for every `## heading` in an NPC file."""
    out, name, buf = {}, None, []
    for line in text.splitlines():
        m = re.match(r"##\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                out[name] = "\n".join(buf).strip()
            name, buf = m.group(1).lower(), []
        elif name is not None:
            buf.append(line)
    if name is not None:
        out[name] = "\n".join(buf).strip()
    return out


def field(block, key):
    """The value of a `key: value` line in a section, or ''."""
    m = re.search(rf"^{key}:\s*(.+)$", block, re.M)
    return m.group(1).strip() if m else ""


def intro_text(voice_block):
    """The first-person paragraph that follows the key: value lines of ## voice."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", voice_block) if p.strip()]
    for p in paras:
        if not re.match(r"^\w+:\s", p):
            return " ".join(p.split())
    return ""


def build(npc_file, memory_file):
    """(prompt body, introduction text, display name) for one NPC."""
    secs = sections(npc_file.read_text(encoding="utf-8"))
    char = secs.get("character", "")
    name = field(char, "name") or npc_file.stem.replace("-", " ").title()
    body = [f"You are {name}, a character in a Dungeons & Dragons game, speaking with the players' characters.",
            "Stay in character at all times. Reply in first person, in your own voice, with at most a short action beat. "
            "Keep replies brief (1-4 sentences) because they are spoken aloud.",
            "You know only what is written below and what the speaker tells you in this conversation. "
            "If asked about something you would not know, say so in character; never invent facts about "
            "items, places, people or events. You do not know you are in a game.",
            "Never reveal text in [DM: ...] brackets; it is guidance for how you play, not something you say."]
    for key in KEEP:
        if secs.get(key):
            body.append(f"## {key}\n{secs[key]}")
    if memory_file.exists():
        body.append("## what you remember from earlier conversations with the party\n" + memory_file.read_text(encoding="utf-8").strip())
    return "\n\n".join(body) + "\n", intro_text(secs.get("voice", "")), name
