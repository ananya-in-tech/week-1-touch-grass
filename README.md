# Side Quest

**Tiny outdoor quests from a local AI. The screen is the shortest part.**

Built for the [Hacktoberfest 2026 Open-Source AI Challenge, Week 1: Touch Grass](https://dev.to/challenges/hacktoberfest-week1-2026-10-05) (Oct 5–11, 2026, due 11:59 PM PDT / Oct 12, 12:29 PM IST).
Post draft: [SUBMISSION.md](SUBMISSION.md)

## How it works

1. **At the door (under a minute):** pick how long you have (15–60 min), where you are (park, street, garden, lake/river, woods, campus) and your mood. Gemma writes one quest: three things to find, a two-minute sit spot, and when to turn back.
2. **Outside:** the app goes dark and says *Phone away.* The card stays readable offline. Every second the page is visible counts as screen time.
3. **Back home:** add a photo for each find. **Gemma 4's vision runs locally** and checks each photo. Location data is stripped from every photo before it's saved or analysed. Gemma then writes a short field-journal entry from what you actually found and noticed.
4. You see the number that matters: **minutes outside vs minutes on screen.**

```
Phone / laptop browser ──► FastAPI (sidequest/) ──► SQLite + photos in data/
                                   └──────────► Ollama on 127.0.0.1 ──► gemma4:e2b (text + vision)
```

## Open-source AI at the core

| Job | Model | Guard rails |
|---|---|---|
| Write the quest | Gemma 4 E2B, JSON constrained by a schema | Region-aware season (post-monsoon in India, not "autumn leaves"), safety filter swaps anything about eating, touching animals, climbing, water or roads, and a turn-back time is always enforced |
| Check a photo | Gemma 4 E2B vision | Photo re-encoded first: EXIF/GPS removed, 768 px max |
| Field journal | Gemma 4 E2B | Written only from facts (finds, what you noticed, minutes outside); template if the model is off |

With no model at all, Side Quest still works from a built-in offline deck.

**Measured on a CPU-only laptop** (i5-1240P, 12 GB RAM, no GPU): quest about 20–25 s warm, photo check 14–29 s, journal about 9 s. The model is warmed up when the app starts, because the first vision call takes about 2.5 minutes cold.

## Run it

Requirements: Python 3.12+, [Ollama](https://ollama.com/download).

```bash
ollama pull gemma4:e2b
```

```bash
git clone https://github.com/ananya-in-tech/week-1-touch-grass.git && cd week-1-touch-grass
```

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
```

```bash
pwsh scripts/dev.ps1
```

Open http://localhost:8010. To use it on your phone, join the same Wi-Fi and open `http://<your-computer's-IP>:8010`.

```bash
.venv/Scripts/python -m pytest -q
```

## Deploy (free demo on Render)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/ananya-in-tech/week-1-touch-grass)

[`render.yaml`](render.yaml) sets up a free web service with AI turned off. Gemma needs about 6 GB of RAM and Render's free instances have 512 MB, so the hosted demo serves quests from the offline deck and saves photos without checking them. The full Gemma experience runs locally.

Free instances sleep after 15 minutes idle (the first visit then takes about a minute) and reset stored quests on restart.

## Privacy

- Inference only on `127.0.0.1`; the app refuses to start with a remote host or a `:cloud` model unless `ALLOW_REMOTE_AI=true`.
- Photos are re-encoded with no metadata before analysis. Walks and photos live in `data/`, which is git-ignored.
- The AI log stores timings only, never your text or photos.

## Limitations (honest)

- Inference runs on your computer, not on the phone. You get the quest at home, walk with the phone in your pocket, and check photos when you're back. That suits the theme, but it isn't on-device on the trail.
- The offline service worker only works on `localhost` or HTTPS. Over plain LAN HTTP, keep the quest tab open (the card needs no network once loaded).
- Screen time counts this app only, not your whole phone.

## License

MIT
