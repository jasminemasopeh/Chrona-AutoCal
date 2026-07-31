# Chrona — Calendar Scheduling Agent

Chrona is an LLM calendar agent that turns a task list into a conflict-free Google Calendar schedule. You review each proposed slot (Accept / Reject / Edit), then click **Put in calendar**. A separate tab can restyle whole calendars from an aesthetic or image.

Built for CIS5930 (LLM Agents).

---

## Use online (no install)

Open the live app:

**[https://chrona-autocal.onrender.com/](https://chrona-autocal.onrender.com/)**

### How to use the website

1. Click **Connect Google** and sign in with the Google account whose calendars you want Chrona to use. Approve calendar access when prompted.
2. Confirm the status pill shows **Google Calendar connected**.
3. On **Plan schedule**:
   - Pick a **target day**.
   - Add tasks as chips (type a task and press Enter). Examples:
     - `Gym (45m)`
     - `Deep work on term project (90m) before 3pm`
     - `Grocery run (30m)`
     - `Reply to emails (20m)`
   - Click **Plan schedule**. Chrona proposes a calendar and time for each task (nothing is written yet).
4. For each proposal, choose **Accept**, **Reject**, or **Edit** (edit lets you change start/end).
5. Click **Put in calendar** to write accepted/edited events to Google Calendar. Rejected items are skipped. Preference memory is updated from your choices.
6. Open [Google Calendar](https://calendar.google.com/) and check the target day (Gym/health → Personal, work-style tasks → Work when those calendars exist).

### Color palettes tab (optional)

1. Switch to **Color palettes**.
2. Optionally add an aesthetic description, upload an image, and/or style notes (e.g. “keep text black”).
3. Keep **Apply colors to Google calendars** checked if you want changes saved.
4. Click **Generate palette**, review the assignments, and confirm in Google Calendar (including mobile — calendar colors sync).

### Notes for online visitors

- The free Render host may sleep when idle; the first load can take ~30–60 seconds.
- You must complete Google sign-in yourself; Chrona only accesses calendars you authorize.
- Removing a task chip that was already scheduled also deletes that event from Google Calendar.

---

## Run locally

### Requirements

- Python 3.10+
- An [OpenRouter API key](https://openrouter.ai/keys)
- A Google Cloud project with **Google Calendar API** enabled and a **Web application** OAuth client

### 1. Install

```bash
git clone https://github.com/jasminemasopeh/Chrona-AutoCal.git
cd Chrona-AutoCal
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o-mini
TIMEZONE=America/New_York
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
```

### 3. Google OAuth (local)

1. In [Google Cloud Console](https://console.cloud.google.com/), enable **Google Calendar API**.
2. Create an **OAuth client ID** → application type **Web application**.
3. Add authorized redirect URI: `http://127.0.0.1:8000/api/auth/google/callback`
4. Download the client JSON and save it as `credentials/client_secret.json`.
5. On the OAuth consent screen, add your Google account as a **Test user** while the app is in Testing.

### 4. Start the app

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

Then follow the same steps as **Use online**: Connect Google → add tasks → Plan schedule → Accept/Reject/Edit → **Put in calendar**.

### Local troubleshooting

- **`OPENROUTER_API_KEY is not set`** — copy `.env.example` to `.env` and paste your key.
- **`Missing Google OAuth client secrets`** — place the Web client JSON at `credentials/client_secret.json`.
- **`404` / model not found** — use a full OpenRouter model id, e.g. `openai/gpt-4o-mini`.
- **No free slots** — pick a less busy day or widen `work_hours` in `data/preferences.json`.

---

## License

Course / academic use.
