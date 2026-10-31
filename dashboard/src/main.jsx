import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import Mailbox from "./Mailbox";
import AnniversaryGallery from "./AnniversaryGallery";
import LoveWords from "./LoveWords";
import { Icon, EnvelopeIllustration } from "./Illustrations";
import { getInitialLanguage, LANGUAGE_STORAGE_KEY, locales, translate } from "./translations";
import { normalizeInstagramRecipient } from "./instagramRecipient";
import { AmbientBackdrop, FloatingHearts } from "./Decor";
import {
  animateOut, burstHearts, gsap, motionAllowed, revealNew, ScrollTrigger, useGSAP,
  useIntro, useMagnetic, useWordsRefresh, withMotion, words,
} from "./motion";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const SETUP_URL = `${API_BASE || (import.meta.env.DEV ? "http://127.0.0.1:8000" : "")}/`;
function CatIllustration({ t }) {
  const scope = useRef(null);
  const { contextSafe } = useGSAP(() => withMotion(() => {
    gsap.to(".cat-body", { scaleY: 1.018, scaleX: .995, svgOrigin: "140 196", duration: 1.9, ease: "sine.inOut", repeat: -1, yoyo: true });
    gsap.to(".cat-sign", { rotation: 2.5, svgOrigin: "140 150", duration: 2.6, ease: "sine.inOut", repeat: -1, yoyo: true });
    gsap.to(".cat-ear", { rotation: -6, svgOrigin: "100 50", duration: .12, repeat: 3, yoyo: true, repeatDelay: 5.5, delay: 3 });
    const blink = () => gsap.timeline({ onComplete: () => gsap.delayedCall(gsap.utils.random(2.2, 5.5), blink) })
      .to(".cat-eyes", { scaleY: .08, svgOrigin: "140 93", duration: .09, ease: "power2.in" })
      .to(".cat-eyes", { scaleY: 1, duration: .16, ease: "power2.out" });
    gsap.delayedCall(2, blink);

    // The pupils follow the pointer around the page.
    const x = gsap.quickTo(".cat-pupils", "x", { duration: .45, ease: "power3.out" });
    const y = gsap.quickTo(".cat-pupils", "y", { duration: .45, ease: "power3.out" });
    const look = (event) => {
      const box = scope.current.getBoundingClientRect();
      x(gsap.utils.clamp(-6, 6, (event.clientX - (box.left + box.width / 2)) / 40));
      y(gsap.utils.clamp(-5, 5, (event.clientY - (box.top + box.height * .42)) / 40));
    };
    window.addEventListener("pointermove", look);
    return () => window.removeEventListener("pointermove", look);
  }), { scope });

  const hop = contextSafe(() => {
    burstHearts(scope.current, 10);
    if (!motionAllowed()) return;
    gsap.timeline()
      .to(scope.current, { y: -18, scaleY: 1.04, duration: .22, ease: "power2.out" })
      .to(scope.current, { y: 0, scaleY: 1, duration: .55, ease: "bounce.out" });
  });

  return (
    <svg ref={scope} className="cat-illustration" viewBox="0 0 280 220" role="img" aria-label={t("catDescription")} onClick={hop}>
      <ellipse cx="140" cy="199" rx="86" ry="12" fill="#e9caca" opacity=".55" />
      <g className="cat-body">
        <path d="M75 68 67 21c-1-8 8-12 14-7l37 28c14-5 30-5 44 0l37-28c6-5 15-1 14 7l-8 47c12 14 18 31 18 53 0 47-31 70-83 70s-83-23-83-70c0-22 6-39 18-53Z" fill="var(--cat-fur)" />
        <path className="cat-ear" d="M76 37 74 28l26 20Z" fill="#efaaa9" />
        <path d="M204 37l2-9-26 20Z" fill="#efaaa9" />
        <g className="cat-eyes">
          <ellipse cx="104" cy="93" rx="21" ry="26" fill="#fff9f1" />
          <ellipse cx="176" cy="93" rx="21" ry="26" fill="#fff9f1" />
          <g className="cat-pupils">
            <ellipse cx="106" cy="95" rx="10" ry="15" fill="#3f2a32" />
            <ellipse cx="174" cy="95" rx="10" ry="15" fill="#3f2a32" />
            <circle cx="109" cy="89" r="4" fill="white" /><circle cx="177" cy="89" r="4" fill="white" />
          </g>
        </g>
        <path d="M132 118q8-8 16 0-8 9-16 0Z" fill="#c27877" />
        <path d="M140 123q-7 12-17 5m17-5q7 12 17 5" fill="none" stroke="#573a40" strokeWidth="2" strokeLinecap="round" />
        <path d="M81 125 43 116m39 20-40 4m114-15 38-9m-38 29 40 4" fill="none" stroke="#bd817e" strokeWidth="2" strokeLinecap="round" opacity=".7" />
        <g className="cat-sign">
          <path d="M77 142q63-25 126 0l-7 54q-56 14-112 0Z" fill="#fffaf4" stroke="#ecd9d0" strokeWidth="3" />
          <text x="140" y="169" textAnchor="middle" fill="#9e5e62" fontFamily="inherit" fontSize="14" fontWeight="600">{t("loveYou")}</text>
          <path d="M67 154q-16 5-13 22 3 12 18 3m141-25q16 5 13 22-3 12-18 3" fill="none" stroke="var(--cat-fur)" strokeWidth="16" strokeLinecap="round" />
        </g>
      </g>
    </svg>
  );
}

const SECTIONS = [["compose", "mail", "writeNote"], ["gallery", "image", "memories"], ["love-words", "heart", "loveNav"], ["upcoming", "calendar", "upcoming"]];

/** The section whose top most recently passed 40% of the viewport height. */
function currentSection() {
  const line = window.innerHeight * .4;
  let current = SECTIONS[0][0];
  let best = -Infinity;
  for (const [id] of SECTIONS) {
    const top = document.getElementById(id)?.getBoundingClientRect().top;
    if (top !== undefined && top <= line && top > best) { best = top; current = id; }
  }
  return current;
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${API_BASE}${path}`, {
    headers: isFormData ? { ...(options.headers || {}) } : { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  }).catch(() => { throw translatedError("connectionFailed"); });
  const body = await response.json().catch(() => { throw translatedError("requestFailed"); });
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
  const [contactsLoading, setContactsLoading] = useState(true);
  const [contactsError, setContactsError] = useState(false);
  const [schedulesError, setSchedulesError] = useState(false);
  const [recipientUrl, setRecipientUrl] = useState("");
  const [recipientInput, setRecipientInput] = useState("");
  const [addingRecipient, setAddingRecipient] = useState(false);
  const [schedules, setSchedules] = useState([]);
  const [draft, setMessage] = useState(null);
  const message = draft ?? t("defaultMessage");
  const [sendAt, setSendAt] = useState("");
  const [notice, setNotice] = useState({ type: "", text: "" });
  const [pendingAction, setPendingAction] = useState(null);
  const busy = pendingAction !== null;
  const [opened, setOpened] = useState(() => {
    try { return sessionStorage.getItem("anniversary-surprise-opened") === "true"; } catch { return false; }
  });
  const action = useRef(false);
  const recipientField = useRef(null);
  const page = useRef(null);
  const surpriseButton = useRef(null);
  const sendButton = useRef(null);
  const scheduleButton = useRef(null);
  const [activeSection, setActiveSection] = useState(SECTIONS[0][0]);

  useIntro(page);
  useWordsRefresh(page, language);
  useMagnetic(surpriseButton);
  useMagnetic(scheduleButton, .2);

  // Highlight the rail link for the section being read.
  useGSAP(() => {
    const pick = () => setActiveSection(currentSection());
    ScrollTrigger.create({ start: 0, end: "max", onUpdate: pick, onRefresh: pick });
    pick();
  }, { scope: page });

  // Slide the rail highlight under the active link.
  useGSAP(() => {
    const place = (animate) => {
      const link = page.current.querySelector(`.rail-link[data-section="${activeSection}"]`);
      if (!link) return;
      gsap.to(".rail-indicator", {
        x: link.offsetLeft, y: link.offsetTop, width: link.offsetWidth, height: link.offsetHeight,
        duration: animate && motionAllowed() ? .55 : 0, ease: "power3.out", overwrite: true,
      });
    };
    place(true);
    const resize = () => place(false);
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, { scope: page, dependencies: [activeSection, language] });

  const recipients = useMemo(() => contacts.filter((contact) => contact.ig_url?.trim()), [contacts]);
  const selectedContact = recipients.find((contact) => contact.ig_url.trim() === recipientUrl) || recipients[0];
  const contactIndex = contacts.indexOf(selectedContact);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = translate(language, "pageTitle");
    try { localStorage.setItem(LANGUAGE_STORAGE_KEY, language); } catch { /* Storage is optional. */ }
  }, [language]);

  async function load() {
    await Promise.allSettled([
      api("/api/contacts").then((next) => {
        if (!Array.isArray(next)) throw new Error();
        setContacts(next); setContactsError(false);
      }).catch(() => setContactsError(true)).finally(() => setContactsLoading(false)),
      api("/api/schedules").then((next) => {
        if (!Array.isArray(next)) throw new Error();
        setSchedules(next); setSchedulesError(false);
      }).catch(() => setSchedulesError(true)),
    ]);
  }

  useEffect(() => {
    load();
    const timer = setInterval(() => { if (!action.current) load(); }, 30000);
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

  function beginAction(name) {
    if (action.current) return false;
    action.current = true; setPendingAction(name); setNotice({ type: "", text: "" });
    return true;
  }

  function finishAction() { action.current = false; setPendingAction(null); }

  function checkRecipient() {
    if (selectedContact && !addingRecipient) return true;
    showNotice("error", "recipientRequired");
    document.getElementById("compose").scrollIntoView({ behavior: "smooth", block: "start" });
    recipientField.current?.focus({ preventScroll: true });
    return false;
  }

  async function saveRecipient() {
    const url = normalizeInstagramRecipient(recipientInput);
    if (!url) { showNotice("error", "invalidRecipient"); recipientField.current?.focus(); return; }
    if (!beginAction("recipient")) return;
    try {
      const existing = contacts.find((contact) => normalizeInstagramRecipient(contact.ig_url || "") === url);
      if (!existing) {
        const username = new URL(url).pathname.split("/")[1];
        const result = await api("/api/contacts", { method: "POST", body: JSON.stringify({
          first_name: username === "direct" ? "Instagram" : username, ig_url: url,
        }) });
        if (!result.ok) throw (result.error ? new Error(result.error) : translatedError("requestFailed"));
      }
      const next = await api("/api/contacts");
      if (!Array.isArray(next)) throw translatedError("requestFailed");
      setContacts(next); setContactsError(false); setContactsLoading(false);
      setRecipientUrl(existing?.ig_url.trim() || url); setAddingRecipient(false); setRecipientInput("");
      showNotice("success", "recipientSaved");
    } catch (error) {
      showError(error);
    } finally {
      finishAction();
    }
  }

  async function sendNow(surprise = false) {
    if ((surprise && opened) || !checkRecipient() || !message.trim() || !beginAction(surprise ? "surprise" : "send")) return;
    try {
      const result = await api("/api/anniversary/send", {
        method: "POST",
        body: JSON.stringify({ contact_index: contactIndex, message, dry_run: false }),
      });
      if (!result.ok) throw (result.error ? new Error(result.error) : translatedError("sendFailed"));
      burstHearts(surprise ? surpriseButton.current : sendButton.current, surprise ? 24 : 14);
      if (surprise) {
        try { sessionStorage.setItem("anniversary-surprise-opened", "true"); } catch { /* Sending does not require storage. */ }
        setOpened(true);
      }
      showNotice("success", surprise ? "surpriseOnWay" : "messageSent");
    } catch (error) {
      showError(error);
    } finally {
      finishAction();
    }
  }

  async function scheduleMessage(event) {
    event.preventDefault();
    if (!checkRecipient() || !sendAt || !message.trim() || !beginAction("schedule")) return;
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
      burstHearts(scheduleButton.current);
      showNotice("success", "scheduled");
      setSendAt("");
      load();
    } catch (error) {
      showError(error);
    } finally {
      finishAction();
    }
  }

  async function cancelSchedule(id, row) {
    try {
      await animateOut(row, { x: 30, rotation: 0 });
      await api(`/api/schedules/${id}`, { method: "DELETE" });
      showNotice("success", "cancelled");
      await load();
    } catch (error) {
      gsap.set(row, { clearProps: "all" });
      showError(error);
    }
  }

  const activeSchedules = schedules.filter((schedule) => schedule.enabled);

  useGSAP(() => { revealNew(".scheduled", { x: 24, y: 0 }); }, { scope: page, dependencies: [activeSchedules.length] });
  useGSAP(() => withMotion(() => {
    gsap.from(".notice.toast", { y: -14, autoAlpha: 0, scale: .97, duration: .45, ease: "back.out(2)" });
  }), { scope: page, dependencies: [notice.key, notice.text] });
  const typed = useRef(false);
  useGSAP(() => {
    if (!typed.current) { typed.current = true; return; }
    withMotion(() => { gsap.fromTo(".message-preview", { scale: .985 }, { scale: 1, duration: .45, ease: "back.out(3)", overwrite: true }); });
  }, { scope: page, dependencies: [message] });
  return (
    <main ref={page} className="app-shell">
      <AmbientBackdrop />
      <nav className="side-rail" aria-label={t("dashboardSections")}>
        <a className="brand-mark" href="#" aria-label={t("homeLink")}><Icon /></a>
        <div className="rail-links">
          <span className="rail-indicator" aria-hidden="true" />
          {SECTIONS.map(([id, icon, label]) => <a key={id} data-section={id} className={`rail-link ${activeSection === id ? "active" : ""}`} aria-current={activeSection === id ? "location" : undefined} href={`#${id}`}><Icon name={icon} /> {t(label)}</a>)}
        </div>
        <div className="rail-footer">{t("madeWith")}<br /><strong>{t("love")}</strong></div>
      </nav>
      <div className="shell">
      <header className="hero">
        <div>
          <div className="breadcrumb"><span>{t("home")}</span><b>/</b> {t("anniversaryNote")}</div>
          <p className="eyebrow">{t("fromYou")}</p>
          <h1>{words(t("heading"))} <span className="hero-heart">♥</span></h1>
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

      {(notice.key || notice.text) && <div role={notice.type === "error" ? "alert" : "status"} className={`notice toast ${notice.type}`}>{notice.key ? t(notice.key, notice.values) : notice.text}</div>}

      <section className={`welcome-card ${opened ? "opened" : ""}`}>
        <FloatingHearts />
        <div className="welcome-copy">
          <p className="eyebrow">{t("delivery")}</p>
          <h2>{t("sayIt")} <em>{t("heart")}</em></h2>
          <p>{t("welcome")}</p>
          <div className="welcome-pills"><span>♡ {t("personal")}</span><span>✦ {t("private")}</span><span>◷ {t("onTime")}</span></div>
          <button ref={surpriseButton} type="button" className="button surprise-button" onClick={() => sendNow(true)} disabled={opened || busy || contactsLoading || !message.trim()}>
            {opened ? t("surpriseSent") : pendingAction === "surprise" ? t("sending") : t("sendSurprise")}
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
      <LoveWords apiBase={API_BASE} language={language} suggestedThread={selectedContact?.ig_url?.trim()} />

      <section className="grid">
        <form id="compose" className="card composer reveal" onSubmit={scheduleMessage}>
          <div className="card-heading">
            <div>
              <p className="eyebrow">{t("message")}</p>
              <h2>{t("makePersonal")}</h2>
            </div>
            <div className="heart-mark"><Icon name="mail" /></div>
          </div>

          <div className="recipient-picker">
            <label htmlFor="instagram-recipient">{t("recipientLabel")}</label>
            {contactsLoading ? <p className="private-note" role="status">{t("recipientsLoading")}</p>
              : selectedContact && !addingRecipient ? <div className="recipient-selection"><select id="instagram-recipient" value={selectedContact.ig_url.trim()} disabled={busy} onChange={(event) => setRecipientUrl(event.target.value)}>{recipients.map((contact, index) => <option key={index} value={contact.ig_url.trim()}>{`${contact.first_name || ""} ${contact.last_name || ""}`.trim() || contact.ig_url}</option>)}</select><button type="button" className="button secondary" disabled={busy} onClick={() => setAddingRecipient(true)}>{t("newRecipient")}</button></div>
                : <><input ref={recipientField} id="instagram-recipient" type="text" value={recipientInput} disabled={busy} onChange={(event) => setRecipientInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); saveRecipient(); } }} placeholder={t("recipientPlaceholder")} autoComplete="off" autoCapitalize="none" spellCheck={false} aria-describedby="recipient-help" /><p id="recipient-help" className="private-note">{t("recipientHelp")}</p><div className="recipient-actions"><button type="button" className="button secondary" disabled={busy || !recipientInput.trim()} onClick={saveRecipient}>{pendingAction === "recipient" ? t("savingRecipient") : t("saveRecipient")}</button>{selectedContact && <button type="button" className="button secondary" disabled={busy} onClick={() => setAddingRecipient(false)}>{t("cancel")}</button>}</div></>}
            {contactsError && <p className="recipient-error" role="alert">{t("recipientsFailed")} <button type="button" disabled={busy} onClick={load}>{t("retry")}</button></p>}
            <p className="private-note">{t("instagramLoginHint")} <a href={SETUP_URL} target="_blank" rel="noreferrer">{t("manageLogin")}</a></p>
          </div>

          <label>
            {t("messageLabel")}
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows="7" maxLength="2000" required />
          </label>
          <div className="counter">{message.length}/2000</div>

          <div className="send-mode single-action">
            <p className="private-note">{t("privateNote")}</p>
            <button ref={sendButton} type="button" className="button secondary" onClick={() => sendNow()} disabled={busy || contactsLoading || !message.trim()}>
              {pendingAction === "send" ? t("sending") : t("sendNote")}
            </button>
          </div>

          <div className="schedule-box">
            <label>
              {t("scheduleLabel")}
              <input type="datetime-local" value={sendAt} onChange={(event) => setSendAt(event.target.value)} required />
            </label>
            <button ref={scheduleButton} className="button primary" disabled={busy || contactsLoading || !sendAt || !message.trim()}>
              {pendingAction === "schedule" ? t("scheduling") : t("scheduleNote")}
            </button>
          </div>
        </form>

        <aside>
          <div className="card preview-card reveal">
            <div className="card-heading"><div><p className="eyebrow">{t("preview")}</p><h2>{t("previewHeading")}</h2></div><span className="instagram-icon"><Icon name="instagram" /></span></div>
            <div className="message-preview"><div className="preview-avatar">♥</div><div><strong>{selectedContact ? `${selectedContact.first_name || ""} ${selectedContact.last_name || ""}`.trim() || t("recipientFallback") : t("recipientFallback")}</strong><p>{message || t("previewPlaceholder")}</p><small>{t("instagramDM")}</small></div></div>
          </div>
          <div id="upcoming" className="card upcoming reveal">
            <div className="card-heading"><div><p className="eyebrow">{t("calendar")}</p><h2>{t("upcoming")}</h2></div><span className="calendar"><Icon name="calendar" /></span></div>
            {schedulesError && <p className="recipient-error" role="alert">{t("schedulesFailed")} <button type="button" disabled={busy} onClick={load}>{t("retry")}</button></p>}
            {activeSchedules.length === 0 && <div className="empty-state"><EnvelopeIllustration /><strong>{t("upcomingEmpty")}</strong><p>{t("upcomingHint")}<br />{t("upcomingHintMore")}</p></div>}
            {activeSchedules.map((schedule) => (
              <div className="scheduled" key={schedule.id}>
                <div><strong>{schedule.name === "One-year anniversary message" ? t("scheduleName") : schedule.name}</strong><span>{schedule.next_run ? new Date(schedule.next_run).toLocaleString(locales[language]) : t("pending")}</span></div>
                <button aria-label={t("cancelSchedule")} onClick={(event) => cancelSchedule(schedule.id, event.currentTarget.closest(".scheduled"))}>×</button>
              </div>
            ))}
          </div>
        </aside>
      </section>
      <footer className="reveal">{t("footer")}</footer>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode>{window.location.pathname.startsWith("/mailbox") ? <Mailbox /> : <App />}</StrictMode>);
