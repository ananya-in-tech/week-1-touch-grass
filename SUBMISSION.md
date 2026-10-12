---
title: Side Quest: A Local AI That Sends You Outside (and Then Gets Out of the Way)
published: false
tags: devchallenge, hf26challenge, ai, opensource
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge: Week 1 — Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05).*

## What I Built

I know I should go outside more. What usually stops me isn't time, it's not having a reason. I'd open my laptop 'for five minutes' and look up an hour later.

**Side Quest** gives you that reason. You tell it how long you have and where you are, and a local AI gives you one small quest:

- **three things to find** (like "a bird you can hear but not see")
- **a two-minute sit spot** (stop and listen)
- **a time to turn back**

Then the screen goes dark and says **"Phone away."** When you're back, you snap your finds, the AI checks your photos, and it writes a short journal entry about your walk.

The only number it shows you at the end is **minutes outside vs minutes on screen.**

## Demo

**Live demo:** [side-quest-vpar.onrender.com](https://side-quest-vpar.onrender.com)

The live demo runs on Render's free tier, which doesn't have enough memory for Gemma, so it serves quests from the built-in offline deck. The full experience, with Gemma writing quests and checking photos, runs locally and is shown in the screenshots below. If the demo takes a minute to load, the free server is waking up.

![Side Quest screenshot 1](https://raw.githubusercontent.com/ananya-in-tech/week-1-touch-grass/main/imgs/Screenshot%202026-10-12%20134555.png)
![Side Quest screenshot 2](https://raw.githubusercontent.com/ananya-in-tech/week-1-touch-grass/main/imgs/Screenshot%202026-10-12%20134601.png)
![Side Quest screenshot 3](https://raw.githubusercontent.com/ananya-in-tech/week-1-touch-grass/main/imgs/Screenshot%202026-10-12%20134943.png)

## Code

{% github ananya-in-tech/week-1-touch-grass %}

## How I Built It

- **Model:** Gemma 4 (E2B), running locally through Ollama. No cloud API.
- **Backend:** Python + FastAPI, SQLite for storage.
- **Frontend:** a small mobile-friendly web page with no build step.

Gemma does three jobs:

1. **Writes the quest.** It returns structured JSON that the app validates. A small rules layer keeps quests safe (no eating, touching animals, climbing or going near water) and makes sure there's always a real time limit.
2. **Checks your photos.** Gemma's vision looks at each photo and says whether it matches the find. Before that, the app removes all location data from the photo.
3. **Writes your journal.** It uses only what you actually found and noticed, so it doesn't make things up.

If the AI is off, Side Quest still works using a built-in set of quests.

## Why Open Innovation Matters Here

- **Privacy:** photos from a walk reveal where you live and where you go. With a local model they never leave my computer, and the location data is stripped before the model even sees them.
- **Free to use:** no API key and no per-photo cost, so there's no reason to ration walks.
- **I can shape it:** with an open model I could tune it for where I live. For example, my first quests said "autumn leaves", but October in India is post-monsoon, so I made the seasons region-aware.

## What Went Wrong

- Early quests used the wrong season for India. I fixed it with region-aware seasons.
- The AI sometimes gave vague turn-back times like "when the shadows lengthen". The app now always sets a real time limit.
- On a laptop with no GPU, the first photo check took about 2.5 minutes while the model loaded. The app now loads the model when it starts.

## Prize Category

**Best Use of Gemma:** Gemma 4 runs locally and powers quest writing, photo checking (vision) and the journal.
