# Facebook & Instagram Messenger Automation

Send personalized messages on **Facebook** and/or **Instagram** from a contact list, using browser automation. The main workflow is the **web dashboard**; a smaller **CLI** is available for Facebook-only runs.

> **Warning:** This tool uses browser automation which violates Meta’s Terms of Service. Use at your own risk — your account may be restricted or banned.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage (dashboard — recommended)

### 1. Start the server

```bash
python server.py
```

Open **http://127.0.0.1:8000** (or http://localhost:8000). The UI talks to the API and live logs over WebSockets.

### 2. Browser profiles and login

- Profiles are listed in `profiles.json` (default profile name: `Main`). Each profile uses its own Chromium data under `browser_profile_<slug>/` (e.g. `browser_profile_main/`).
- Use **Setup Login** in the UI (or `POST /api/setup-login` with `{"platform": "facebook"}` or `"instagram"`) to sign in once per platform. Sessions persist in that profile directory.
- Optional: legacy `cookies.json` is imported into a profile **once** (see `.cookies_imported` in the profile folder).

### 3. Contacts — `contacts.csv`

Columns used by the automation engine:

```csv
first_name,last_name,fb_url,ig_url,custom_field
John,Doe,https://www.facebook.com/messages/t/...,https://www.instagram.com/direct/t/...,your note
```

- Include **fb_url** and/or **ig_url** (Messenger / Instagram DM thread URLs). Rows with neither URL are skipped.
- Extra columns can be referenced in the message template.

### 4. Config — `config.json`

```json
{
  "message_template": "Hey {{first_name}}, just wanted to follow up on {{custom_field}}.",
  "min_delay_seconds": 30,
  "max_delay_seconds": 90,
  "headless": true,
  "dry_run": false,
  "openai_api_key": "",
  "openai_model": "gpt-5.4",
  "follow_up_count": 3,
  "follow_up_delay_min": 5,
  "follow_up_delay_max": 15,
  "chat_tone": "friendly and casual"
}
```

- **openai_api_key** (optional): if set, the engine generates follow-up messages after a successful send; **follow_up_*** and **chat_tone** control count, spacing, and style.
- **dry_run**: log what would be sent without opening a browser (no login required).

### 5. Run automation

From the dashboard: configure contacts, then start the run (you can restrict to selected contacts). Via API: `POST /api/start` with an optional JSON body `{"contact_indices": [0, 1]}` to run a subset.

## Usage (CLI — Facebook only)

`main.py` runs **sequentially** on **Facebook** using a **`profile_url`** column (not `fb_url`). Use a CSV that includes `profile_url`, or pass `--contacts` to such a file.

```bash
python main.py
python main.py --dry-run
python main.py --config my_config.json --contacts my_list.csv
python main.py --headless
```

For the same `fb_url` / `ig_url` format as the dashboard, use `server.py` and the engine, not this CLI.

## How it works (engine / dashboard)

1. Launches Chromium with a **persistent profile** and light anti-automation tweaks.
2. For each contact, opens **one tab per platform** that has a URL and sends in **parallel** (Facebook and Instagram can run together).
3. Renders the first message with **Jinja2**-style templates.
4. If an OpenAI key is configured, generates follow-ups and sends them with delays between follow-ups (**follow_up_delay_min** / **follow_up_delay_max**).
5. Logs attempts to **`message_log.csv`**; the dashboard streams logs over **`/ws`**.

## Files

| Path | Purpose |
|------|---------|
| `server.py` | FastAPI app: API, WebSocket, static UI |
| `static/` | Dashboard assets |
| `main.py` | CLI entry (Facebook, `profile_url`) |
| `config.json` | Template, delays, headless/dry_run, OpenAI follow-up settings |
| `contacts.csv` | Recipients (`fb_url` / `ig_url` for the engine) |
| `profiles.json` | Named profiles and active profile |
| `browser_profile_<name>/` | Per-profile Chromium user data (sessions) |
| `cookies.json` | Optional one-time cookie import for a new profile |
| `message_log.csv` | Send history |
| `fb_automation/` | Browser, engine, Messenger/Instagram helpers, templates, logger |
