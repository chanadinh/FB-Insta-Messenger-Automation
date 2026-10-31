import { useRef, useState } from "react";
import { EnvelopeIllustration, Icon } from "./Illustrations";
import { gsap, motionAllowed, revealNew, useGSAP } from "./motion";
import { locales } from "./translations";

/** Letters from the partner (sealed until opened) and the ones I sent. */
export default function LetterBox({ t, language, letters, onRead }) {
  const scope = useRef(null);
  const [tab, setTab] = useState("inbox");
  const [opening, setOpening] = useState(null);
  const names = { me: letters?.me, partner: letters?.partner };
  const list = (tab === "inbox" ? letters?.inbox : letters?.sent?.filter((letter) => letter.deliver_at <= letters.now)) || [];
  const when = (value) => new Date(value).toLocaleString(locales[language], { dateStyle: "medium", timeStyle: "short" });

  useGSAP(() => {
    revealNew(".inbox-letter", { y: 24, rotation: () => gsap.utils.random(-3, 3), stagger: .06, ease: "back.out(1.5)" });
  }, { scope, dependencies: [tab, list.map((letter) => letter.id).join(",")] });

  async function open(letter, card) {
    if (opening !== null) return;
    setOpening(letter.id);
    try {
      await onRead(letter);
      if (motionAllowed()) {
        // Unfold the note: the seal lifts away, then the words appear line by line.
        requestAnimationFrame(() => {
          const body = card?.querySelector(".inbox-letter-body");
          if (body) gsap.fromTo(body, { clipPath: "inset(0 0 100% 0)", y: -8 }, { clipPath: "inset(0 0 0% 0)", y: 0, duration: .9, ease: "power2.out" });
        });
      }
    } finally {
      setOpening(null);
    }
  }

  return <section ref={scope} id="inbox" className="card inbox reveal" aria-labelledby="inbox-title">
    <div className="card-heading">
      <div><p className="eyebrow">{t("inboxEyebrow", names)}</p><h2 id="inbox-title">{t("inboxTitle", names)} {letters?.unread > 0 && <span className="photo-count">{letters.unread}</span>}</h2></div>
      <span className="heart-mark"><Icon name="mail" /></span>
    </div>
    <div className="love-filter inbox-tabs" role="group" aria-label={t("inboxNav")}>
      <button type="button" aria-pressed={tab === "inbox"} onClick={() => setTab("inbox")}>{t("inboxTab")}{letters?.unread > 0 ? ` (${letters.unread})` : ""}</button>
      <button type="button" aria-pressed={tab === "sent"} onClick={() => setTab("sent")}>{t("sentTab")}</button>
    </div>

    {list.length === 0
      ? <div className="empty-state"><EnvelopeIllustration /><strong>{t(tab === "inbox" ? "inboxEmpty" : "sentEmpty", names)}</strong><p>{t(tab === "inbox" ? "inboxEmptyHint" : "sentEmptyHint", names)}</p></div>
      : <div className="inbox-grid">{list.map((letter) => {
        const sealed = tab === "inbox" && !letter.read_at;
        return <article key={letter.id} className={`inbox-letter ${sealed ? "sealed" : ""}`}>
          <div className="inbox-letter-meta">
            <strong className="handwritten">{t(tab === "inbox" ? "fromName" : "toName", { name: tab === "inbox" ? letter.sender : letter.recipient })}</strong>
            <time dateTime={letter.deliver_at}>{when(letter.deliver_at)}</time>
          </div>
          {sealed
            ? <button type="button" className="inbox-seal" disabled={opening !== null} onClick={(event) => open(letter, event.currentTarget.closest(".inbox-letter"))}>
              <span className="mini-seal" aria-hidden="true">♥</span>
              <span>{opening === letter.id ? t("opening") : t("sealedFrom", names)}</span>
              <small>{t("openLetter")}</small>
            </button>
            : <p className="inbox-letter-body">{letter.body}</p>}
          {tab === "sent" && <small className="inbox-receipt">{letter.read_at ? t("readReceipt", names) : t("notReadYet")}</small>}
        </article>;
      })}</div>}
  </section>;
}
