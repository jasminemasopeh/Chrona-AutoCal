# Chrona — Calendar Scheduling Agent

Python FastAPI app that uses an **OpenAI tool-calling agent** to turn a plain-text task list into a conflict-free Google Calendar schedule, learn preferences from accept/reject/edit feedback, and recolor events from an image or aesthetic description.

Built for CIS5930 (LLM Agents) term project — implementation option.

## Features

1. **Schedule tab** — chip-based task list; agent auto-detects which calendar (Personal/Work/School/…) and free slot each task fits
2. **Preference memory** — local JSON store updated from accept/reject/edit feedback
3. **Color palettes tab** (optional, separate) — restyle whole calendars from an aesthetic/image plus style prefs (e.g. black text, mobile parity)
4. **Local web UI** — two tabs; remove a task chip to delete its calendar event too

## Requirements

- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/keys) (routes to OpenAI models)
- A Google Cloud project with the **Google Calendar API** enabled and an **OAuth Desktop** client

## 1. Clone / enter the project

```bash
cd /home/jasmine/TPF
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Configure OpenRouter

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
TIMEZONE=America/New_York
```

The app talks to OpenRouter’s OpenAI-compatible endpoint (`https://openrouter.ai/api/v1`) using the official `openai` Python SDK. Model ids must use OpenRouter’s format (e.g. `openai/gpt-4o-mini`).

## 3. Set up Google Calendar OAuth (from scratch)

### 3a. Create a Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g. `chrona-calendar-agent`)
3. Select that project

### 3b. Enable the Calendar API

1. Go to **APIs & Services → Library**
2. Search for **Google Calendar API**
3. Click **Enable**

### 3c. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**
2. Choose **External** (unless you have a Google Workspace org)
3. Fill in App name (e.g. `Chrona`), support email, and developer contact
4. Add scope: `https://www.googleapis.com/auth/calendar`
5. Add your Google account as a **Test user** (required while the app is in Testing)

### 3d. Create a Web OAuth client

1. Go to **APIs & Services → Credentials**
2. **Create Credentials → OAuth client ID**
3. Application type: **Web application**
4. Name it (e.g. `Chrona Web`)
5. Add **Authorized JavaScript origins**:
   - `http://127.0.0.1:8000`
   - your public origin (e.g. `https://chrona-autocal.onrender.com`)
6. Add **Authorized redirect URIs**:
   - `http://127.0.0.1:8000/api/auth/google/callback`
   - `https://YOUR-HOST/api/auth/google/callback`
7. Download the JSON file and save it as:

```text
credentials/client_secret.json
```

The filename can vary when downloaded from Google; rename/move it to exactly `credentials/client_secret.json`.

Set `GOOGLE_REDIRECT_URI` in `.env` to the redirect URI you are using (local or production).

### 3e. First-time sign-in

Start the app (next section), then click **Connect Google** in the UI (or open `GET /api/auth/google`).

Your browser is redirected to Google for consent, then back to `/api/auth/google/callback`. After approval, a token is saved to `credentials/token.json` (gitignored).

## 4. Run the app

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Demo walkthrough

1. **Connect Google** (once).
2. Enter a **target day** and a task list, for example:

   ```text
   - Deep work on term project (90m) before 3pm
   - Gym (45m)
   - Grocery run (30m)
   - Reply to emails (20m)
   ```

3. Optionally upload a **palette image** and/or type an aesthetic description (e.g. `moss green and soft clay`).
4. Keep **Write proposed events to Google Calendar** checked and click **Plan schedule**.
5. Review the proposal and palette. For each slot choose **Accept**, **Reject**, or **Edit**, then **Save feedback**.
6. Check Google Calendar — events should appear with category-mapped colors.
7. Run again on another day: preference memory (`data/preferences.json`) should bias future slot choices (e.g. health in the morning).

## Project layout

```text
TPF/
  app/
    main.py              # FastAPI routes + UI
    config.py            # env / paths
    agent/               # OpenAI tool-calling loop
    calendar_api/        # OAuth + Calendar tools
    memory/              # preferences.json helpers
    palette/             # image → palette → colorId
    web/                 # templates + static assets
  data/preferences.json  # local preference memory
  credentials/           # client_secret.json + token.json (local only)
  requirements.txt
  .env.example
```

## Agent tools

| Tool | Purpose |
|------|---------|
| `get_preferences` | Read local scheduling memory |
| `update_preferences` | Merge preference updates |
| `get_events` | List events for a day |
| `find_free_slots` | Free windows + candidate slots inside work hours |
| `create_event` | Create event; returns conflict details for replanning |
| `update_event_color` | Patch Google `colorId` (1–11) |

## API cheat sheet

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/api/health` | Health + auth flag |
| `GET` | `/api/auth/google` | Start Google OAuth (redirect) |
| `GET` | `/api/auth/google/callback` | OAuth redirect handler |
| `POST` | `/api/plan` | multipart: task_list, target_day, aesthetic_description?, image?, write_to_calendar |
| `POST` | `/api/feedback` | JSON accept/reject/edit items |
| `GET` | `/api/preferences` | Current preference store |
| `GET` | `/api/events?day=YYYY-MM-DD` | List events |

## Troubleshooting

- **`OPENROUTER_API_KEY is not set`** — create `.env` from `.env.example` and paste your OpenRouter key.
- **`404` / model not found from OpenRouter** — use a full OpenRouter model id like `openai/gpt-4o-mini` (not bare `gpt-4o-mini`).
- **`Missing Google OAuth client secrets`** — place Web client JSON at `credentials/client_secret.json` and set `GOOGLE_REDIRECT_URI` to a registered redirect URI.
- **`Google Calendar API has not been used...` / `accessNotConfigured`** — in Google Cloud, select project **`chrona-calendar-agent`** (id `180994919519`) and enable **Google Calendar API**:  
  https://console.developers.google.com/apis/api/calendar-json.googleapis.com/overview?project=180994919519  
  Wait 1–2 minutes after enabling, then retry. “Google Calendar connected” only means OAuth succeeded; the Calendar API must still be enabled separately.
- **No free slots** — widen work hours in `data/preferences.json` or pick a less busy day.
- **Colors look wrong** — Google only supports fixed event colors (1–11); the app maps your palette to the nearest of those.

## Evaluation notes (course)

This project demonstrates:

- A real **tool-using agent loop** (not a single prompt)
- **Conflict detection + replanning** via tool return values
- **Persistent preference memory** updated from user feedback
- **Multimodal-ish personalization** (image palette → calendar styling)

## License

Course / academic use.
# Chrona-AutoCal
