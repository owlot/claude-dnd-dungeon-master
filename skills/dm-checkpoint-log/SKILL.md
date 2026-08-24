---
description: Flush the current session conversation to the log file. Captures everything discussed since the last checkpoint. Use mid-session on long sessions or before a break.
argument-hint: "[campaign]"
---

Write the session conversation log directly from the active conversation context. Do NOT delegate to any agent — agents cannot access the raw conversation and will hallucinate content.

## This is not purely on-demand — it has mandatory automatic triggers

This skill is not just something to run when the DM asks or at the end of a session. Per CLAUDE.md, it MUST be invoked automatically, without waiting for the DM to ask, at **every one** of these points:

- **Before every named-NPC conversation begins** — not just the first one of the session. If three different NPCs get talked to in one session, that's three separate triggers (before Vajra, before Noska, before Xanathar — each one, every time, even if you already flushed once earlier).
- **Before combat starts**, every time combat starts — before handing off to `combat-tracker`.
- **At end-session**, as part of `/dm-end-session`.

**Why this matters**: skipping intermediate flushes lets unflushed content pile up across an entire session. When the final flush arrives carrying hours of dense, multi-scene backlog instead of one scene's worth, the temptation to compress into lossy bracketed summaries instead of full verbatim transcription becomes much stronger — and summarizing here directly contradicts Step 5 below. A session with 4 NPC conversations and 1 combat should produce at least 5 checkpoint-log invocations before the final end-session one, not 1.

**Self-check before treating any checkpoint as "done" for the session**: ask "has a new named-NPC conversation started, or has combat started, since my last flush?" If yes and you haven't flushed for it yet, that flush is already overdue — do it now, don't fold it into a future summary.

## Steps

1. Read `campaigns/$ARGUMENTS/party/state.md` to confirm the current session number N.

2. Check where the existing log leaves off, without reading the whole file — it grows all session and this skill runs repeatedly while the table waits:

   ```bash
   tail -n 40 "campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md"
   ```

   That is enough to see the last scene heading. If the file does not exist yet, this flush creates it.

3. Write directly from the active conversation context — everything the DM said and Claude responded since the last checkpoint (or since session start if this is the first flush).

4. **Append** to `campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md` — never rewrite it. Use a quoted heredoc so dialogue containing backticks, `$`, or quotes is written literally:

   ```bash
   cat >> "campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md" <<'FLUSH'

   ### [Time of Day] — [Location] — [Scene Name]

   [scene content, verbatim]
   FLUSH
   ```

   Use scene headings, DM/Claude speaker labels, and NPC dialogue quoted faithfully, matching the format already in the file (or the heading shape above if starting fresh).

   Do **not** reproduce the existing log in order to add to it. This skill fires before every NPC conversation and every combat, so a full rewrite costs the table a pause that grows longer with every scene already logged.

5. Quote DM inputs and NPC dialogue **exactly as they appeared in the conversation** — do not paraphrase, interpret, or reconstruct. If Caelith said "Hi, I'm Caelith Moorn" that is what goes in the log. **This rule does not relax as the unflushed backlog grows.** A large amount of unwritten material is a sign a trigger was missed earlier (see above), not a license to summarize now — writing "[the party then did X, Y, and Z]" as a bracketed summary in place of the actual exchanges is exactly the failure mode this skill exists to prevent, and it is *most* likely to happen precisely when there's the most content to transcribe. If the backlog feels large enough that summarizing is tempting, that is the moment to slow down and write it out in full, not the moment to compress.

6. Print one confirmation line:
   > "Conversation log updated: campaigns/$ARGUMENTS/party/session-[N]/session-[N]-conversation.md (Manual checkpoint)"
