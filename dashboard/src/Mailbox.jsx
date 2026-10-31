import { useEffect, useRef, useState } from "react";
import Gallery from "./Gallery";
import { EnvelopeIllustration, Icon } from "./Illustrations";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const STORAGE_KEY = "our-mailbox-key";

function displayName(person) {
  if (!person) return "người thương";
  if (person.name === "You") return "Đá đì";
  if (person.name === "Your girlfriend") return "Bé bi";
  return person.name;
}

function personalKey() {
  const key = new URLSearchParams(window.location.hash.slice(1)).get("key");
  if (key) {
    try { localStorage.setItem(STORAGE_KEY, key); } catch { /* Link still works for this visit. */ }
    history.replaceState(null, "", window.location.pathname + window.location.search);
    return key;
  }
  try { return localStorage.getItem(STORAGE_KEY) || ""; } catch { return ""; }
}

export default function Mailbox() {
  const [key, setKey] = useState(personalKey);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState("");
  const [tab, setTab] = useState("inbox");
  const [busy, setBusy] = useState(false);
  const [opening, setOpening] = useState(null);
  const [openNotes, setOpenNotes] = useState(new Set());
  const sending = useRef(false);

  async function request(path = "", options = {}) {
    const response = await fetch(`${API_BASE}/api/mailbox${path}`, {
      ...options,
      headers: { Authorization: "Bearer " + key, "Content-Type": "application/json", ...(options.headers || {}) },
      cache: "no-store",
    }).catch(() => { throw new Error("Không kết nối được với hộp thư. Kiểm tra mạng rồi thử lại nhé."); });
    if (response.status === 401) { setData(null); throw new Error("Liên kết này không còn hiệu lực. Hãy mở liên kết riêng mới nhất của mình nhé."); }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : "Chưa thực hiện được. Mình thử lại nhé.");
    }
    return response.json();
  }

  useEffect(() => {
    if (!key) return;
    let active = true;
    async function refresh() {
      try {
        const next = await request();
        if (active) { setData(next); setError(""); }
      } catch (err) { if (active) setError(err.message); }
    }
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [key]);

  async function send(event) {
    event.preventDefault();
    if (!draft.trim() || sending.current) return;
    sending.current = true;
    setBusy(true); setError(""); setNotice("");
    try {
      await request("/messages", { method: "POST", body: JSON.stringify({ body: draft }) });
      setDraft(""); setNotice("Đã gửi một chút yêu thương 💌");
      setData(await request());
    } catch (err) { setError(err.message); }
    finally { sending.current = false; setBusy(false); }
  }

  async function openNote(note) {
    if (opening !== null) return;
    setOpening(note.id);
    try {
      if (note.recipient === data.person.id && !note.read_at) {
        await request(`/messages/${note.id}/read`, { method: "POST" });
        setData((current) => ({ ...current, messages: current.messages.map((item) => item.id === note.id ? { ...item, read_at: new Date().toISOString() } : item) }));
      }
      setOpenNotes((current) => new Set([...current, note.id]));
    } catch (err) { setError(err.message); }
    finally { setOpening(null); }
  }

  function forget() {
    try { localStorage.removeItem(STORAGE_KEY); } catch { /* No saved key. */ }
    setKey(""); setData(null); setDraft(""); setError(""); setNotice(""); setOpenNotes(new Set());
  }

  if (!data) return <main className="mailbox-entry card">
    <EnvelopeIllustration /><p className="eyebrow">Chỉ riêng hai đứa mình</p><h1>Hộp thư của đôi mình</h1>
    <p className="subtitle">{!key ? "Mở liên kết riêng để đọc thư nhé. Không cần tài khoản, chỉ cần một chút yêu thương." : error ? "Hộp thư đang gặp chút trục trặc." : "Đang mở hộp thư…"}</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {key && <button className="button secondary" disabled={busy || opening !== null} onClick={forget}>Quên thiết bị này</button>}
  </main>;

  const incoming = data.messages.filter((note) => note.recipient === data.person.id);
  const unread = incoming.filter((note) => !note.read_at).length;
  const notes = tab === "inbox" ? incoming : data.messages.filter((note) => note.sender === data.person.id);
  return <main className="shell mailbox-shell">
    <header className="hero"><div><p className="eyebrow">Chỉ riêng hai đứa mình</p><h1>Hộp thư của đôi mình <span className="hero-heart">♥</span></h1><p className="subtitle">Chào {displayName(data.person)}. Hôm nay mình gửi nhau chút yêu thương nhé.</p></div><button className="button secondary" disabled={busy || opening !== null} onClick={forget}>Quên thiết bị này</button></header>
    {error && <p className="notice error" role="alert">{error}</p>}
    {notice && <p className="notice success" role="status">{notice}</p>}
    <section className="welcome-card mailbox-welcome"><div className="welcome-copy"><p className="eyebrow">Gửi thương yêu mỗi ngày</p><h2>Lời nhắn nhỏ. <em>Yêu thương lớn.</em></h2><p>{unread ? `Có ${unread} lá thư chưa mở đang chờ mình nè.` : "Một lời chào buổi sáng, một lời cảm ơn, hay điều thương mến muốn nói ngay với nhau."}</p></div><EnvelopeIllustration /></section>
    <nav className="memory-nav" aria-label="Góc của đôi mình"><a href="#letters"><Icon name="mail" /> Hộp thư</a><a href="#memories"><Icon name="image" /> Góc kỷ niệm</a></nav>
    <section id="letters" className="grid mailbox-grid">
      <form className="card composer" onSubmit={send}>
        <div className="card-heading"><div><p className="eyebrow">Gửi thương yêu từ {displayName(data.person)}</p><h2>Gửi {displayName(data.partner)}</h2></div><span className="heart-mark"><Icon name="mail" /></span></div>
        <label htmlFor="love-note">Hôm nay mình muốn nhắn gì?</label><textarea id="love-note" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Có một điều ở người thương khiến mình luôn mỉm cười…" maxLength={2000} rows={7} required disabled={busy} />
        <p className="counter mailbox-counter">{draft.length}/2000</p>
        <div className="send-mode"><p className="private-note">Lời nhắn chỉ dành cho đôi mình.</p><button className="button primary" disabled={busy || !draft.trim() || !data.partner}>{busy ? "Đang gửi…" : "Gửi yêu thương"}</button></div>
      </form>
      <section className="card" aria-label="Thư của mình">
        <div className="mailbox-tabs" aria-label="Chọn hộp thư"><button className={`button ${tab === "inbox" ? "primary" : "secondary"}`} aria-pressed={tab === "inbox"} onClick={() => setTab("inbox")}>Thư đến {unread > 0 && `(${unread})`}</button><button className={`button ${tab === "sent" ? "primary" : "secondary"}`} aria-pressed={tab === "sent"} onClick={() => setTab("sent")}>Thư đã gửi</button></div>
        {notes.length === 0 && <div className="empty-state"><EnvelopeIllustration /><strong>{tab === "inbox" ? "Lá thư đầu tiên đang trên đường tới" : "Bắt đầu bằng một lời ngọt ngào"}</strong><p>{tab === "inbox" ? "Khi người thương gửi thư, thư sẽ chờ mình ở đây." : "Gửi một lời chào nhỏ thôi, cũng đủ làm người thương vui cả ngày."}</p></div>}
        <div className="mailbox-notes">{notes.map((note) => {
          const expanded = tab === "sent" || note.read_at || openNotes.has(note.id);
          return <article className={`love-note ${!expanded ? "sealed" : ""}`} key={note.id}>
            <div className="note-meta"><strong>{tab === "inbox" ? `Từ ${displayName(data.partner)}` : `Gửi ${displayName(data.partner)}`}</strong><time dateTime={note.created_at}>{new Date(note.created_at).toLocaleString("vi-VN", { dateStyle: "medium", timeStyle: "short" })}</time></div>
            {expanded ? <p className="note-body">{note.body}</p> : <button className="button secondary" onClick={() => openNote(note)} disabled={opening !== null}><Icon name="mail" />{opening === note.id ? "Đang mở…" : "Mở lá thư nhỏ"}</button>}
            <small>{note.read_at ? "Đã mở thư" : tab === "sent" ? "Đã gửi · chưa mở" : "Một bất ngờ dành riêng cho mình"}</small>
          </article>;
        })}</div>
        {data.messages.length === 200 && <p className="private-note">Đang hiển thị 200 lá thư gần nhất.</p>}
      </section>
    </section><Gallery /><footer>Hai người. Một góc nhỏ dành cho yêu thương.</footer>
  </main>;
}
