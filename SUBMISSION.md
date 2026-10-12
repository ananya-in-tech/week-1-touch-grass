---
title: Side Quest: a local AI that gives you three things to find, then tells you to put your phone away
published: false
tags: devchallenge, hf26challenge, ai, opensource
cover_image:
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge: Week 1 — Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).*

<!-- ✍️ = only you can write this. Everything else is drafted from the build; edit it into your own voice.
     Note: the Week 1 deadline was Oct 11, 11:59 PM PDT (Oct 12, 12:29 PM IST). Check whether late entries are accepted before tagging it. -->

## What I Built

<!-- ✍️ One honest opening line about you and screens. e.g. "I open my phone to check the time and look up 40 minutes later." -->

**Side Quest** turns "I should go outside" into a tiny, specific mission:

1. Tell it how long you have and where you are. It's a 10-second screen.
2. Gemma writes one quest: **three things to find**, a two-minute sit spot, and a time to turn back.
3. The app goes dark: *Phone away.*
4. When you're back, you snap your finds. **Gemma's vision checks them locally**, and Gemma writes a short field-journal entry from what you actually found.

Then it shows the only number it cares about: **minutes outside vs minutes on screen.**
<!-- ✍️ Add your real numbers from a real walk, e.g. "My first quest: 31 minutes outside, 2 on screen." -->

## Demo

<!-- ✍️ Add a GIF or 60–90 s video: pick options → quest card → "Phone away" → photos checked → journal + ratio bar.
     Bonus points from the judges if you take it outside, so add a real walk and real photos. -->

## Code

{% github ananya-in-tech/week-1-touch-grass %}

## How I Built It

```
Phone/laptop browser → FastAPI → SQLite + photos (on disk)
                          └────→ Ollama on 127.0.0.1 → Gemma 4 E2B (text + vision)
```

- **Quest writer:** Gemma 4 E2B returns JSON constrained by a schema, validated with Pydantic. A rules layer then:
  - **gives it the right season.** My first quests in India were all "autumn colour hunts" with red maple leaves. In India, October is post-monsoon. Side Quest now uses Indian seasons for Indian timezones, and the quests switched to lush green, flowers and migrating birds.
  - **keeps it safe.** A filter swaps out anything about eating, picking, touching or feeding animals, climbing, entering water or crossing roads, and tells you what it swapped. Look, listen, photograph.
  - **forces a real time limit.** "When the shadows lengthen" isn't a turn-back time, so if the model doesn't say "30 minutes", code does.
- **Photo checker:** every photo is decoded, rotated and **re-encoded with no metadata** (GPS gone), shrunk to 768 px, then shown to Gemma's vision with the quest item. It answers yes / maybe / no plus what it actually sees. It's told to be generous: the point is that you went and looked.
- **Field journal:** written only from facts: finds, what you noticed at the sit spot, minutes outside, minutes on screen. Text you typed is passed as data, never as instructions.
- **Screen-time counter:** the page counts the seconds it is actually visible during a quest, including glances at the card outside.
- **Works without AI:** if Ollama is off, quests come from a built-in deck and photos are saved unchecked.

**Numbers (CPU-only laptop, i5-1240P, 12 GB RAM, no GPU):** quest 20–25 s, photo check 14–29 s, journal ~9 s once warm. A cold vision load takes ~2.5 minutes, so the app warms the model up at start. 20 automated tests cover the safety filter, location stripping, offline fallback and the full walk flow.

## Why Open Innovation Matters Here

- **Your walks are location data.** A quest app that sends photos to a cloud API sends *where you walk and when*. Here, photos never leave the computer, and location data is removed before the model even sees them.
- **It costs nothing to use every day.** No API key, no per-photo bill, so there's no reason to limit how often you go outside.
- **I could make the model behave for my place.** Prompt rules, a safety layer and region-aware seasons on top of an open model that I run myself. Swapping Gemma sizes is one line in `.env`.
- **It still works when the internet doesn't.** Quests fall back to an offline deck, and the card needs no network once loaded.
<!-- ✍️ Add where open worked better than closed for you, in your own words. -->

## What Went Wrong

- Every quest was "autumn" in October, in India. Fixed with region-aware seasons.
- The model wrote vague turn-back cues. Fixed by enforcing a real time limit in code.
- The journal said "you only *photographed* two minutes of the quest". It misread my screen-time fact. Fixed by rewording the fact so it can't be misread.
- A cold vision load takes ~2.5 minutes on CPU. Fixed with a warm-up at start.
<!-- ✍️ Add what happened on your real walk. -->

## Taking It Outside

<!-- ✍️ Required for bonus points: go on 1–2 real quests. Where, how long, which finds, what Gemma said about your photos, your outside-vs-screen numbers. One honest surprise. -->

## Prize Categories

**Best Use of Gemma:** Gemma 4 E2B runs locally through Ollama and does all three AI jobs: quest writing (structured output), photo checking (vision) and the field journal.
