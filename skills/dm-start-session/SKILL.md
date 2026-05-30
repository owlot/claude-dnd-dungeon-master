---
description: Begin a play session — reads campaign state, shows party status, recaps last session, and tells the DM what comes next.
argument-hint: "[campaign name]"
---

Start session $ARGUMENTS

Delegate to the `session-manager` sub-agent to:
1. Read `campaigns/$ARGUMENTS/party/state.md`
2. Show a brief recap of last session
3. Show current party status (HP, resources, conditions)
4. Tell the DM what comes next based on state
5. Ask "Ready to begin?" before proceeding
