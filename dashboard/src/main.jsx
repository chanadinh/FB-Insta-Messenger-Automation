import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import Mailbox from "./Mailbox";
import AnniversaryGallery from "./AnniversaryGallery";
import { Icon, EnvelopeIllustration } from "./Illustrations";
import { getInitialLanguage, LANGUAGE_STORAGE_KEY, locales, translate } from "./translations";

const API_BASE = import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "");
function CatIllustration({ t }) {
  return (
    <svg className="cat-illustration" viewBox="0 0 280 220" role="img" aria-label={t("catDescription")}>
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
      <text x="140" y="169" textAnchor="middle" fill="#9e5e62" fontFamily="inherit" fontSize="14" fontWeight="600">{t("loveYou")}</text>
      <path d="M67 154q-16 5-13 22 3 12 18 3m141-25q16 5 13 22-3 12-18 3" fill="none" stroke="var(--cat-fur)" strokeWidth="16" strokeLinecap="round" />
    </svg>
  );
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData ? { ...(options.headers || {}) } : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }).catch(() => { throw translatedError("connectionFailed"); });
  const body = await response.json();
  if (!response.ok) throw (typeof body.detail === "string" || typeof body.error === "string"
    ? new Error(body.detail || body.error) : translatedError("requestFailed"));
  return body;
}

function translatedError(key, values = {}) {
  return Object.assign(new Error(), { translationKey: key, values });
}

function App() {
  const [language, setLanguage] = useState(getInitialLanguage);
  const t = (key, values) => translate(language, key, values);
  const [contacts, setContacts] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [draft, setMessage] = useState(null);
  const message = draft ?? t("defaultMessage");
  const [sendAt, setSendAt] = useState("");
  const [notice, setNotice] = useState({ type: "", text: "" });
  const [busy, setBusy] = useState(false);
  const [opened, setOpened] = useState(() => sessionStorage.getItem("anniversary-surprise-opened") === "true");

  const selectedContact = useMemo(() => contacts.find((contact) => contact.ig_url), [contacts]);
  const contactIndex = contacts.indexOf(selectedContact);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = translate(language, "pageTitle");
    try { localStorage.setItem(LANGUAGE_STORAGE_KEY, language); } catch { /* Storage is optional. */ }
  }, [language]);

  async function load() {
    try {
      const [nextContacts, nextSchedules] = await Promise.all([
        api("/api/contacts"),
        api("/api/schedules"),
      ]);
      setContacts(nextContacts);
      setSchedules(nextSchedules);
    } catch (error) {
      showError(error);
    }

  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, []);

  function showNotice(type, key, values = {}) {
    setNotice({ type, key, values });
    window.setTimeout(() => setNotice({ type: "", text: "" }), 5000);
  }

  function showError(error) {
    setNotice(error.translationKey
      ? { type: "error", key: error.translationKey, values: error.values }
      : { type: "error", text: error.message, key: error.message ? "" : "requestFailed" });
  }

  async function sendNow() {
    if (!selectedContact || !message.trim()) return;
    setBusy(true);
    try {
      const result = await api("/api/anniversary/send", {
        method: "POST",
        body: JSON.stringify({ contact_index: contactIndex, message, dry_run: false }),
      });
      if (!result.ok) throw (result.error ? new Error(result.error) : translatedError("sendFailed"));
      showNotice("success", "messageSent");
      await load();
    } catch (error) {
      showError(error);
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
      if (!result.ok) throw (result.error ? new Error(result.error) : translatedError("surpriseFailed"));
      sessionStorage.setItem("anniversary-surprise-opened", "true");
      setOpened(true);
      showNotice("success", "surpriseOnWay");
    } catch (error) {
      showError(error);
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
      if (!result.ok) throw (result.error ? new Error(result.error) : translatedError("scheduleFailed"));
      showNotice("success", "scheduled");
      setSendAt("");
      await load();
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function cancelSchedule(id) {
    try {
      await api(`/api/schedules/${id}`, { method: "DELETE" });
      showNotice("success", "cancelled");
      await load();
    } catch (error) {
      showError(error);
    }
  }

  const activeSchedules = schedules.filter((schedule) => schedule.enabled);
  return (
    <main className="app-shell">
      <nav className="side-rail" aria-label={t("dashboardSections")}>
        <a className="brand-mark" href="#" aria-label={t("homeLink")}><Icon /></a>
        <div className="rail-links">
          <a className="rail-link active" href="#compose"><Icon name="mail" /> {t("writeNote")}</a>
          <a className="rail-link" href="#gallery"><Icon name="image" /> {t("memories")}</a>
          <a className="rail-link" href="#upcoming"><Icon name="calendar" /> {t("upcoming")}</a>
        </div>
        <div className="rail-footer">{t("madeWith")}<br /><strong>{t("love")}</strong></div>
      </nav>
      <div className="shell">
      <header className="hero">
        <div>
          <div className="breadcrumb"><span>{t("home")}</span><b>/</b> {t("anniversaryNote")}</div>
          <p className="eyebrow">{t("fromYou")}</p>
          <h1>{t("heading")} <span>♥</span></h1>
          <p className="subtitle">{t("subtitle")}</p>
        </div>
        <div className="hero-actions">
          <div className="language-switch" role="group" aria-label={t("language")}>
            <button type="button" lang="en" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>English</button>
            <button type="button" lang="vi" aria-pressed={language === "vi"} onClick={() => setLanguage("vi")}>Tiếng Việt</button>
          </div>
          <span className="occasion-badge"><Icon name="sparkle" /> {t("firstChapter")}</span>
        </div>
      </header>

      {(notice.key || notice.text) && <div role={notice.type === "error" ? "alert" : "status"} className={`notice ${notice.type}`}>{notice.key ? t(notice.key, notice.values) : notice.text}</div>}

      <section className={`welcome-card ${opened ? "opened" : ""}`}>
        <div className="welcome-copy">
          <p className="eyebrow">{t("delivery")}</p>
          <h2>{t("sayIt")} <em>{t("heart")}</em></h2>
          <p>{t("welcome")}</p>
          <div className="welcome-pills"><span>♡ {t("personal")}</span><span>✦ {t("private")}</span><span>◷ {t("onTime")}</span></div>
          <button type="button" className="button surprise-button" onClick={(event) => { event.stopPropagation(); openSurprise(); }} disabled={opened || busy || !selectedContact}>
            {opened ? t("surpriseSent") : busy ? t("sending") : t("sendSurprise")}
          </button>
        </div>
        <CatIllustration t={t} />
      </section>

      <section className="mini-stats" aria-label={t("noteOverview")}>
        <div><span className="stat-icon peach"><Icon /></span><div><b>{t("lovelyYear")}</b><small>{t("moreToCome")}</small></div></div>
        <div><span className="stat-icon lavender"><Icon name="calendar" /></span><div><b>{t("scheduledCount", { count: activeSchedules.length })}</b><small>{t("lookForward")}</small></div></div>
        <div><span className="stat-icon mint"><Icon name="instagram" /></span><div><b>{selectedContact ? t("recipientReady") : t("addRecipient")}</b><small>{selectedContact ? t("viaInstagram") : t("setupContact")}</small></div></div>
      </section>

      <AnniversaryGallery apiBase={API_BASE} language={language} />

      <section className="grid">
        <form id="compose" className="card composer" onSubmit={scheduleMessage}>
          <div className="card-heading">
            <div>
              <p className="eyebrow">{t("message")}</p>
              <h2>{t("makePersonal")}</h2>
            </div>
            <div className="heart-mark"><Icon name="mail" /></div>
          </div>

          <label>
            {t("messageLabel")}
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows="7" maxLength="2000" required />
          </label>
          <div className="counter">{message.length}/2000</div>

          <div className="send-mode single-action">
            <p className="private-note">{t("privateNote")}</p>
            <button type="button" className="button secondary" onClick={sendNow} disabled={busy || !selectedContact}>
              {busy ? t("sending") : t("sendNote")}
            </button>
          </div>

          <div className="schedule-box">
            <label>
              {t("scheduleLabel")}
              <input type="datetime-local" value={sendAt} onChange={(event) => setSendAt(event.target.value)} required />
            </label>
            <button className="button primary" disabled={busy || !sendAt || !selectedContact}>
              {t("scheduleNote")}
            </button>
          </div>
        </form>

        <aside>
          <div className="card preview-card">
            <div className="card-heading"><div><p className="eyebrow">{t("preview")}</p><h2>{t("previewHeading")}</h2></div><span className="instagram-icon"><Icon name="instagram" /></span></div>
            <div className="message-preview"><div className="preview-avatar">♥</div><div><strong>{selectedContact ? `${selectedContact.first_name || ""} ${selectedContact.last_name || ""}`.trim() || t("recipientFallback") : t("recipientFallback")}</strong><p>{message || t("previewPlaceholder")}</p><small>{t("instagramDM")}</small></div></div>
          </div>
          <div id="upcoming" className="card upcoming">
            <div className="card-heading"><div><p className="eyebrow">{t("calendar")}</p><h2>{t("upcoming")}</h2></div><span className="calendar"><Icon name="calendar" /></span></div>
            {activeSchedules.length === 0 && <div className="empty-state"><EnvelopeIllustration /><strong>{t("upcomingEmpty")}</strong><p>{t("upcomingHint")}<br />{t("upcomingHintMore")}</p></div>}
            {activeSchedules.map((schedule) => (
              <div className="scheduled" key={schedule.id}>
                <div><strong>{schedule.name === "One-year anniversary message" ? t("scheduleName") : schedule.name}</strong><span>{schedule.next_run ? new Date(schedule.next_run).toLocaleString(locales[language]) : t("pending")}</span></div>
                <button aria-label={t("cancelSchedule")} onClick={() => cancelSchedule(schedule.id)}>×</button>
              </div>
            ))}
          </div>
        </aside>
      </section>
      <footer>{t("footer")}</footer>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode>{window.location.pathname.startsWith("/mailbox") ? <Mailbox /> : <App />}</StrictMode>);
