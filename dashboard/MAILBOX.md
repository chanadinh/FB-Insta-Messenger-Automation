# Our little mailbox

Two private links identify you and your girlfriend automatically. No signup is needed.
The browser remembers its link until “Forget this browser” is selected. Opening the
other person's link in that browser changes its identity. Use separate browser profiles
when testing both people on the same computer.

## Run on the existing server

Build the dashboard once, and again after frontend changes:

```sh
cd dashboard
npm install
npm run build
cd ..
uvicorn server:app --host 0.0.0.0 --port 8000
```

The mailbox is served at `/mailbox/`. The original automation dashboard stays at `/`.
Docker builds the frontend automatically. For frontend development, `npm run dev`
proxies mailbox requests to the backend on port 8000; visit `/mailbox/` on Vite.

## Create your two links

Run this on the server, in the project directory, using the same `APP_DATA_DIR` as
the running server. Replace the base URL with the server address both of you use:

```sh
python -m fb_automation.mailbox --base-url https://your-server.example --your-name "Your name" --her-name "Her name"
```

For local testing use `--base-url http://localhost:8000`. A localhost link only works
on the server computer. On your home network use the computer's LAN address.
For a Docker deployment, run the command inside the application container so it
uses the `/data` volume.

The command prints two links **once**. Save yours and privately share the
`girlfriend` link. The link itself grants access; no public identity picker or
registration endpoint exists. Anyone holding a link can act as that person.
For remote use, serve over HTTPS and restrict public access to `/mailbox/` and
`/api/mailbox` at your reverse proxy. The existing automation admin routes are
separate and are not protected by these mailbox keys.

To replace lost or exposed links, repeat the command with `--rotate`. Both previous
links stop working, including remembered browser sessions; existing notes remain.

## Storage and behavior

- Notes persist in `mailbox.sqlite3` under `APP_DATA_DIR` (project directory by default).
  Back up that file to retain your notes. It contains private message text.
- Only hashes of the private link keys are stored on the server. The browser stores
  its key locally, removes it from the address bar, and sends it in an authorization header.
- Inbox and sent notes refresh every 10 seconds. The latest 200 notes are shown.
- Notes open individually and record a read receipt. Sending happens only when
  “Send with love” is clicked. This feature does not send Instagram messages.
- The server must be running for either person to send or retrieve notes.

## Checks

With FastAPI and `httpx` installed:

```sh
python -m unittest discover -s tests -v
```
