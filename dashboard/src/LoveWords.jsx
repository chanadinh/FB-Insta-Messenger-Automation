import { useEffect, useRef, useState } from "react";
import { Icon } from "./Illustrations";
import { animateOut, burstHearts, gsap, revealNew, useGSAP } from "./motion";
import { locales, translate } from "./translations";

export default function LoveWords({ apiBase, language, suggestedThread }) {
  const t = (key, values) => translate(language, key, values);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [thread, setThread] = useState("");
  const [automatic, setAutomatic] = useState(false);
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState(null);
  const [filter, setFilter] = useState("all");
  const [visible, setVisible] = useState(6);
  const initialized = useRef(false);
  const dirty = useRef(false);
  const working = useRef(false);
  const requestId = useRef(0);
  const section = useRef(null);
  const syncButton = useRef(null);

  async function request(path = "", options = {}) {
    const response = await fetch(`${apiBase}/api/love-words${path}`, {
      ...options, headers: { "Content-Type": "application/json" }, cache: "no-store",
    }).catch(() => { throw new Error("connection_failed"); });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail?.code || "sync_failed");
    return body;
  }

  function accept(next) {
    setData(next);
    if (!initialized.current) {
      setThread(next.settings.thread_url); setAutomatic(next.settings.auto_sync);
      initialized.current = true;
    }
  }

  async function refresh() {
    const id = ++requestId.current;
    try {
      const next = await request();
      if (id === requestId.current) { accept(next); setError(""); }
    } catch (err) { if (id === requestId.current) setError(err.message); }
    finally { if (id === requestId.current) setLoading(false); }
  }

  useEffect(() => {
    refresh();
    const timer = setInterval(() => { if (!document.hidden && !working.current) refresh(); }, 10000);
    return () => { clearInterval(timer); ++requestId.current; };
  }, [apiBase]);

  useEffect(() => {
    if (!dirty.current && !data?.settings.thread_url && /^https:\/\/(www\.)?instagram\.com\/direct\/t\/\d+\/?$/.test(suggestedThread || "")) setThread(suggestedThread);
  }, [suggestedThread, data?.settings.thread_url]);

  async function act(name, operation) {
    if (working.current) return;
    working.current = true; ++requestId.current;
    setPending(name); setError(""); setNotice(null);
    try { await operation(); }
    catch (err) { setError(err.message); }
    finally { working.current = false; setPending(""); }
  }

  function save(event) {
    event.preventDefault();
    act("save", async () => {
      const next = await request("/settings", { method: "PUT", body: JSON.stringify({ thread_url: thread, auto_sync: automatic }) });
      accept(next); setThread(next.settings.thread_url); setAutomatic(next.settings.auto_sync);
      dirty.current = false; setNotice({ key: "loveSettingsSaved" });
    });
  }

  function sync() {
    act("sync", async () => {
      const next = await request("/sync", { method: "POST" });
      accept(next); setNotice({ key: next.added ? "loveAdded" : "loveNoNew", values: { count: next.added, scanned: next.scanned } });
      if (next.added) burstHearts(syncButton.current);
    });
  }

  function remove(id, card) {
    act(`remove:${id}`, async () => {
      await animateOut(card);
      await request(`/${id}`, { method: "DELETE" }).catch((err) => { gsap.set(card, { clearProps: "all" }); throw err; });
      setData((current) => ({ ...current, notes: current.notes.filter((note) => note.id !== id) }));
    });
  }

  const busy = !!pending || !!data?.syncing;
  const needsSave = thread.trim() !== (data?.settings.thread_url || "") || automatic !== !!data?.settings.auto_sync;
  const notes = (data?.notes || []).filter((note) => filter === "all" || note.language === filter || note.language === "mixed");
  const errorCode = error || data?.settings.last_error;
  const errorKey = `loveError_${errorCode}`;
  const shownIds = notes.slice(0, visible).map((note) => note.id).join(",");

  // Saved words settle in like little cards being laid on a table.
  useGSAP(() => {
    revealNew(".love-word", { y: 30, rotation: () => gsap.utils.random(-5, 5), stagger: .07, ease: "back.out(1.6)" });
  }, { scope: section, dependencies: [shownIds] });

  return <section ref={section} id="love-words" className="card love-words reveal" aria-labelledby="love-words-title">
    <div className="card-heading"><div><p className="eyebrow">{t("loveEyebrow")}</p><h2 id="love-words-title">{t("loveTitle")} <span className="photo-count">{data?.notes.length || 0}</span></h2><p className="subtitle">{t("loveSubtitle")}</p></div><span className="heart-mark"><Icon name="heart" /></span></div>
    <form className="love-settings" onSubmit={save}>
      <label htmlFor="love-thread">{t("loveThreadLabel")}</label>
      <input id="love-thread" type="url" placeholder="https://www.instagram.com/direct/t/…/" value={thread} onChange={(event) => { dirty.current = true; setThread(event.target.value); }} disabled={busy || loading} required aria-describedby="love-thread-help" />
      <p id="love-thread-help" className="private-note">{t("loveThreadHelp")}</p>
      {data?.settings.profile_name && <p className="private-note">{t("loveProfile", { profile: data.settings.profile_name })}</p>}
      <label className="love-auto"><input type="checkbox" checked={automatic} onChange={(event) => { dirty.current = true; setAutomatic(event.target.checked); }} disabled={busy || loading} /><span>{t("loveAutoLabel")}<small>{t("loveAutoHelp")}</small></span></label>
      <div className="love-actions"><button className="button secondary" disabled={busy || loading || !thread.trim() || !needsSave}>{pending === "save" ? t("savingRecipient") : t("loveSaveSettings")}</button><button ref={syncButton} type="button" className="button primary" onClick={sync} disabled={busy || loading || needsSave || !data?.settings.thread_url}><Icon name="sparkle" width="16" height="16" />{pending === "sync" || data?.syncing ? t("loveSyncing") : t("loveSyncNow")}</button></div>
      {needsSave && <p className="private-note">{t("loveSaveFirst")}</p>}
    </form>

    {errorCode && <div className="notice error love-feedback" role="alert"><span>{t(errorKey) === errorKey ? t("loveError_sync_failed") : t(errorKey)}</span>{!data && <button className="button secondary" onClick={refresh}>{t("retry")}</button>}</div>}
    {notice && <p className="notice success" role="status">{t(notice.key, notice.values)}</p>}
    {data?.settings.last_checked && <p className="love-last-sync">{t("loveLastChecked", { date: new Date(data.settings.last_checked).toLocaleString(locales[language], { dateStyle: "medium", timeStyle: "short" }) })}</p>}

    <div className="love-filter" role="group" aria-label={t("loveFilterLabel")}>{[["all", t("loveAll")], ["vi", "Tiếng Việt"], ["en", "English"]].map(([value, label]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => { setFilter(value); setVisible(6); }}>{label}</button>)}</div>
    {loading ? <p className="subtitle" role="status">{t("loveLoading")}</p>
      : notes.length ? <div className="love-words-grid">{notes.slice(0, visible).map((note) => <article className="love-word" key={note.id}>
        <div className="love-word-meta"><span>{note.language === "mixed" ? "VI + EN" : note.language.toUpperCase()}</span><button type="button" className="love-remove" aria-label={t("loveRemove")} disabled={busy} onClick={(event) => remove(note.id, event.currentTarget.closest(".love-word"))}><Icon name="close" width="16" height="16" /></button></div>
        <blockquote lang={note.language === "mixed" ? undefined : note.language}>{note.body}</blockquote>
        <p>{t("loveSavedOn", { date: new Date(note.saved_at).toLocaleDateString(locales[language], { dateStyle: "medium" }) })}</p>
      </article>)}</div> : <div className="love-empty"><Icon name="heart" width="30" height="30" /><h3>{t("loveEmptyTitle")}</h3><p>{t(data?.settings.thread_url ? "loveEmptySynced" : "loveEmptyHelp")}</p><span>“Anh yêu em” · “love u” · “iu vk” · “nhớ ck”</span></div>}
    {notes.length > visible && <button type="button" className="button secondary love-more" onClick={() => setVisible((current) => current + 6)}>{t("loveShowMore")}</button>}
    <p className="private-note love-footnote">{t("loveScope")}</p>
  </section>;
}
