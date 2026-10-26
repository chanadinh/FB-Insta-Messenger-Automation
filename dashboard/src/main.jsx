import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import Mailbox from "./Mailbox";
import { Icon, EnvelopeIllustration } from "./Illustrations";

const API_BASE = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
const defaultMessage =
  "Happy one year, my love. Thank you for making every day brighter. I love you so much ❤️";

function CatIllustration() {
  return (
    <svg className="cat-illustration" viewBox="0 0 280 220" role="img" aria-label="Cute cat holding a love note">
      <ellipse cx="140" cy="199" rx="86" ry="12" fill="#e9caca" opacity=".55" />
      <path d="M75 68 67 21c-1-8 8-12 14-7l37 28c14-5 30-5 44 0l37-28c6-5 15-1 14 7l-8 47c12 14 18 31 18 53 0 47-31 70-83 70s-83-23-83-70c0-22 6-39 18-53Z" fill="var(--cat-fur)" />
      <path d="M76 37 74 28l26 20Z M204 37l2-9-26 20Z" fill="#efaaa9" />
      <ellipse cx="104" cy="93" rx="21" ry="26" fill="#fff9f1" />
      <ellipse cx="176" cy="93" rx="21" ry="26" fill="#fff9f1" />
      <ellipse cx="106" cy="95" rx="10" ry="15" fill="#3f2a32" />
      <ellipse cx="174" cy="95" rx="10" ry="15" fill="#3f2a32" />
      <circle cx="109" cy="89" r="4" fill="white" /><circle cx="177" cy="89" r="4" fill="white" />
      <path d="M132 118q8-8 16 0-8 9-16 0Z" fill="#c27877" />
      <path d="M140 123q-7 12-17 5m17-5q7 12 17 5" fill="none" stroke="#573a40" strokeWidth="2" strokeLinecap="round" />
      <path d="M81 125 43 116m39 20-40 4m114-15 38-9m-38 29 40 4" fill="none" stroke="#bd817e" strokeWidth="2" strokeLinecap="round" opacity=".7" />
      <path d="M77 142q63-25 126 0l-7 54q-56 14-112 0Z" fill="#fffaf4" stroke="#ecd9d0" strokeWidth="3" />
      <text x="140" y="169" textAnchor="middle" fill="#9e5e62" fontFamily="Georgia, serif" fontSize="18" fontWeight="bold">I love you</text>
      <path d="M67 154q-16 5-13 22 3 12 18 3m141-25q16 5 13 22-3 12-18 3" fill="none" stroke="var(--cat-fur)" strokeWidth="16" strokeLinecap="round" />
    </svg>
  );
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData ? { ...(options.headers || {}) } : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || body.error || "Request failed");
  return body;
}

function App() {
  const [contacts, setContacts] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [gallery, setGallery] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(defaultMessage);
  const [sendAt, setSendAt] = useState("");
  const [notice, setNotice] = useState({ type: "", text: "" });
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(() => sessionStorage.getItem("anniversary-surprise-opened") === "true");

  const selectedContact = useMemo(() => contacts.find((contact) => contact.ig_url), [contacts]);
  const contactIndex = contacts.indexOf(selectedContact);

  async function load() {
    try {
      const [nextContacts, nextSchedules] = await Promise.all([
        api("/api/contacts"),
        api("/api/schedules"),
      ]);
      setContacts(nextContacts);
      setSchedules(nextSchedules);
      setGallery(await api("/api/gallery"));
    } catch (error) {
      setNotice({ type: "error", text: error.message });
    }

  }

  async function importPhotos(event) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        const form = new FormData();
        form.append("file", file);
        const result = await api("/api/gallery", { method: "POST", body: form });
        if (!result.ok) throw new Error(result.error || `Could not import ${file.name}`);
      }
      showNotice("success", `${files.length} ${files.length === 1 ? "memory was" : "memories were"} added 💗`);
      setGallery(await api("/api/gallery"));
    } catch (error) {
      showNotice("error", error.message);
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, []);

  function showNotice(type, text) {
    setNotice({ type, text });
    window.setTimeout(() => setNotice({ type: "", text: "" }), 5000);
  }

  async function sendNow() {
    if (!selectedContact || !message.trim()) return;
    setBusy(true);
    try {
      const result = await api("/api/anniversary/send", {
        method: "POST",
        body: JSON.stringify({ contact_index: contactIndex, message, dry_run: false }),
      });
      if (!result.ok) throw new Error(result.error || "Instagram did not report a successful send");
      showNotice("success", "Your message is on its way 💌");
      await load();
    } catch (error) {
      showNotice("error", error.message);
    } finally {
      setBusy(false);
    }
  }

  async function openSurprise() {
    if (opened || busy || !selectedContact || !message.trim()) return;
    setBusy(true);
    try {
      const result = await api("/api/anniversary/send", {
        method: "POST",
        body: JSON.stringify({ contact_index: contactIndex, message, dry_run: false }),
      });
      if (!result.ok) throw new Error(result.error || "Your surprise could not be opened");
      sessionStorage.setItem("anniversary-surprise-opened", "true");
      setOpened(true);
      showNotice("success", "A little surprise is on its way 💌");
    } catch (error) {
      showNotice("error", error.message);
    } finally {
      setBusy(false);
    }
  }

  async function scheduleMessage(event) {
    event.preventDefault();
    if (!selectedContact || !sendAt || !message.trim()) return;
    setBusy(true);
    try {
      const result = await api("/api/schedules", {
        method: "POST",
        body: JSON.stringify({
          name: "One-year anniversary message",
          schedule_type: "once",
          run_at: new Date(sendAt).toISOString(),
          contact_index: Number(contactIndex),
          platforms: ["instagram"],
          idea: message,
          use_ai: false,
          enabled: true,
        }),
      });
      if (!result.ok) throw new Error(result.error || "Could not schedule message");
      showNotice("success", "Scheduled. Keep the server running for the send time.");
      setSendAt("");
      await load();
    } catch (error) {
      showNotice("error", error.message);
    } finally {
      setBusy(false);
    }
  }

  async function cancelSchedule(id) {
    try {
      await api(`/api/schedules/${id}`, { method: "DELETE" });
      showNotice("success", "Scheduled message cancelled.");
      await load();
    } catch (error) {
      showNotice("error", error.message);
    }
  }

  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  return (
    <main className="app-shell">
      <nav className="side-rail" aria-label="Dashboard sections">
        <a className="brand-mark" href="#" aria-label="Love notes home"><Icon /></a>
        <div className="rail-links">
          <a className="rail-link active" href="#compose"><Icon name="mail" /> Write a note</a>
          <a className="rail-link" href="#gallery"><Icon name="image" /> Memories</a>
          <a className="rail-link" href="#upcoming"><Icon name="calendar" /> Upcoming</a>
        </div>
        <div className="rail-footer">made with<br /><strong>love</strong></div>
      </nav>
      <div className="shell">
      <header className="hero">
        <div>
          <div className="breadcrumb"><span>Home</span><b>/</b> Anniversary note</div>
          <p className="eyebrow">A little note from you</p>
          <h1>One year of us <span>♥</span></h1>
          <p className="subtitle">A tiny, thoughtful surprise for her Instagram inbox.</p>
        </div>
        <span className="occasion-badge"><Icon name="sparkle" /> Our first chapter</span>
      </header>

      {notice.text && <div role={notice.type === "error" ? "alert" : "status"} className={`notice ${notice.type}`}>{notice.text}</div>}

      <section className={`welcome-card ${opened ? "opened" : ""}`}>
        <div className="welcome-copy">
          <p className="eyebrow">The sweetest kind of delivery</p>
          <h2>Say it with a little <em>heart.</em></h2>
          <p>Write something only the two of you would understand, then let the server take care of the timing.</p>
          <div className="welcome-pills"><span>♡ Personal</span><span>✦ Private</span><span>◷ On time</span></div>
          <button type="button" className="button surprise-button" onClick={(event) => { event.stopPropagation(); openSurprise(); }} disabled={opened || busy || !selectedContact}>
            {opened ? "Surprise sent ♥" : busy ? "Sending..." : "Send a little surprise"}
          </button>
        </div>
        <CatIllustration />
      </section>

      <section className="mini-stats" aria-label="Your note at a glance">
        <div><span className="stat-icon peach"><Icon /></span><div><b>One lovely year</b><small>So much more to come</small></div></div>
        <div><span className="stat-icon lavender"><Icon name="calendar" /></span><div><b>{activeSchedules.length} scheduled</b><small>A little joy to look forward to</small></div></div>
        <div><span className="stat-icon mint"><Icon name="instagram" /></span><div><b>{selectedContact ? "Recipient ready" : "Add a recipient"}</b><small>{selectedContact ? "Delivering via Instagram" : "Set up an Instagram contact"}</small></div></div>
      </section>

      <section className="card gallery-card" id="gallery">
        <div className="card-heading">
          <div><p className="eyebrow">Little moments</p><h2>Our memory gallery</h2></div>
          <label className="button secondary upload-button">
            {uploading ? "Adding..." : "＋ Add photos"}
            <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple onChange={importPhotos} disabled={uploading} />
          </label>
        </div>
        {gallery.length ? (
          <div className="gallery-grid">
            {gallery.map((image) => <img key={image.name} src={`${API_BASE}${image.url}`} alt="A memory from us" loading="lazy" />)}
          </div>
        ) : (
          <div className="gallery-empty"><span>♡</span><strong>Add the moments that make you smile</strong><p>Import photos from your device and they will bloom here.</p></div>
        )}
      </section>

      <section className="grid">
        <form id="compose" className="card composer" onSubmit={scheduleMessage}>
          <div className="card-heading">
            <div>
              <p className="eyebrow">Message</p>
              <h2>Make it personal</h2>
            </div>
            <div className="heart-mark"><Icon name="mail" /></div>
          </div>

          <label>
            A message from the heart
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows="7" maxLength="2000" required />
          </label>
          <div className="counter">{message.length}/2000</div>

          <div className="send-mode single-action">
            <p className="private-note">Only she will see this note.</p>
            <button type="button" className="button secondary" onClick={sendNow} disabled={busy || !selectedContact}>
              {busy ? "Sending..." : "Send this note"}
            </button>
          </div>

          <div className="schedule-box">
            <label>
              Schedule the message
              <input type="datetime-local" value={sendAt} onChange={(event) => setSendAt(event.target.value)} required />
            </label>
            <button className="button primary" disabled={busy || !sendAt || !selectedContact}>
              Schedule anniversary note
            </button>
          </div>
        </form>

        <aside>
          <div className="card preview-card">
            <div className="card-heading"><div><p className="eyebrow">A little preview</p><h2>How it feels</h2></div><span className="instagram-icon"><Icon name="instagram" /></span></div>
            <div className="message-preview"><div className="preview-avatar">♥</div><div><strong>{selectedContact ? `${selectedContact.first_name || ""} ${selectedContact.last_name || ""}`.trim() || "Her" : "Her"}</strong><p>{message || "Your love note will appear here..."}</p><small>Instagram direct message</small></div></div>
          </div>
          <div id="upcoming" className="card upcoming">
            <div className="card-heading"><div><p className="eyebrow">On the calendar</p><h2>Upcoming</h2></div><span className="calendar"><Icon name="calendar" /></span></div>
            {activeSchedules.length === 0 && <div className="empty-state"><EnvelopeIllustration /><strong>A little love, on standby</strong><p>Pick a time for your note.<br />We’ll keep its place right here.</p></div>}
            {activeSchedules.map((schedule) => (
              <div className="scheduled" key={schedule.id}>
                <div><strong>{schedule.name}</strong><span>{schedule.next_run ? new Date(schedule.next_run).toLocaleString() : "Pending"}</span></div>
                <button aria-label="Cancel scheduled message" onClick={() => cancelSchedule(schedule.id)}>×</button>
              </div>
            ))}
          </div>
        </aside>
      </section>
      <footer>Made with a little love, just for you.</footer>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode>{window.location.pathname.startsWith("/mailbox") ? <Mailbox /> : <App />}</StrictMode>);
