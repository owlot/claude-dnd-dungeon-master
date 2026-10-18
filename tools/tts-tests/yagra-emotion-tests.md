# Yagra Stonefist: TTS emotion tests

Test texts for comparing TTS engines (Qwen3-TTS, dots.tts, Chatterbox, VoxCPM2) with the same cloned Yagra voice.
Written for evaluation, not canon: the facts only echo what the campaign already says (Yawning Portal brawl, Xanathar
Guild, Candle Lane safehouse, Muleskull Tavern, the 1,000 gp still owed).

How to run each text:
- **plain**: no markup. Every engine gets this. Vocal sounds are spelled out ("Ha!", "Heh.", "Ahem."), which shows
  whether an engine turns written laughter or coughs into sound or just reads the letters.
- **tagged**: Chatterbox only. Inline tags `[laugh]`, `[chuckle]`, `[cough]` (per a third-party guide; verify on
  the engine's own page).
- **breeze**: Breeze TTS 2 only. Its tags are written in parentheses: `(laugh)`, `(cough)`, `(clears throat)`, `(sigh)`
  (from the model page, huggingface.co/BreezeBlue/Breeze-TTS-2).
- **direction**: how to steer engines that take instructions. Put it in the voice-design / instruct field
  (Qwen3 `instruct`, VoxCPM `(description)` prefix); engines with neither just get the plain text.

Score each take on: voice still Yagra, emotion lands, sounds like the cue (laugh/cough) and not a word, clean start and
end, no loudness drift, generation time.

---

## T1 Baseline: five flat sentences

Her normal register, no emotion cues. Every engine's reference point.

**plain**
Corrin hired me at the Yawning Portal, and I take the job seriously. Those Guild bandits had it coming, and I don't lose sleep over them. Candle Lane is a Zhentarim safehouse, so stay out of it. If you need me, ask for Yagra at the Muleskull Tavern in the Dock Ward. And bring the thousand gold you still owe me.

**direction**: Blunt, level, unhurried. No warmth, not cruel.

---

## T2 Laughter

**plain**
You walked into the Yawning Portal and picked a fight with the Xanathar Guild on your first night? Ha! Ha ha ha! Gods, that's the funniest thing I've heard all month. Heh. Brave or stupid, I haven't decided, and I like it that way.

**tagged**
You walked into the Yawning Portal and picked a fight with the Xanathar Guild on your first night? [laugh] Gods, that's the funniest thing I've heard all month. [chuckle] Brave or stupid, I haven't decided, and I like it that way.

**breeze**
You walked into the Yawning Portal and picked a fight with the Xanathar Guild on your first night? (laugh) Gods, that's the funniest thing I've heard all month. (laugh) Brave or stupid, I haven't decided, and I like it that way.

**direction**: A rough, grudging laugh: a short bark first, then a low chuckle. Genuinely amused, still gravelly.

---

## T3 Cough

**plain**
The smoke in here is thick enough to chew. Ahem. Too many pipes and not enough windows. Hrm, sorry. Where was I? Right, you were asking who sent the bandits.

**tagged**
The smoke in here is thick enough to chew. [cough] Too many pipes and not enough windows. [cough] Sorry. Where was I? Right, you were asking who sent the bandits.

**breeze**
The smoke in here is thick enough to chew. (cough) Too many pipes and not enough windows. (clears throat) Sorry. Where was I? Right, you were asking who sent the bandits.

**direction**: Dry, hoarse cough in the middle of a sentence, then she picks the thread up again without fuss.

---

## T4 Anger

**plain**
You gave them my name? I told you once, and I will not say it twice. Keep my name out of your mouth, and keep your sloppy talk away from the Guild! If it gets me killed, I will find you before they do. Do you understand me?

**tagged**: same as plain (Chatterbox has no anger tag; test its delivery as written).

**direction**: Barely controlled fury. The voice drops lower and harder instead of getting louder, then one sentence breaks into a shout ("Keep my name out of your mouth").

---

## T5 Mixed (stress test, only if T2 to T4 went well)

**plain**
Corrin, you absolute fool! Ha! Ha ha ha. Ahem. Sorry, sorry. No, I mean it: you gave the Guild my name, and I am furious. Next time, ask first.

**tagged**
Corrin, you absolute fool! [laugh] [cough] Sorry, sorry. No, I mean it: you gave the Guild my name, and I am furious. Next time, ask first.

**breeze**
Corrin, you absolute fool! (laugh) (cough) Sorry, sorry. No, I mean it: you gave the Guild my name, and I am furious. Next time, ask first.

**direction**: Starts as an angry shout, breaks into a laugh, coughs, then goes flat and cold.
