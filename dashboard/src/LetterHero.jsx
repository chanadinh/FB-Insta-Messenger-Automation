import { useRef, useState } from "react";
import { FloatingHearts } from "./Decor";
import { gsap, motionAllowed, useGSAP } from "./motion";

const OPENED_KEY = "anniversary-letter-opened";

function rememberOpened(open) {
  try { sessionStorage.setItem(OPENED_KEY, String(open)); } catch { /* Opening works without storage. */ }
}

/**
 * A sealed envelope that opens into the letter (`children`). Tapping the wax
 * seal cracks it, swings the flap open and lifts the letter out.
 */
export default function LetterHero({ t, names, children }) {
  const scope = useRef(null);
  const timeline = useRef(null);
  const [open, setOpen] = useState(() => {
    try { return sessionStorage.getItem(OPENED_KEY) === "true"; } catch { return false; }
  });

  const { contextSafe } = useGSAP(() => {
    timeline.current = gsap.timeline({ paused: true, defaults: { ease: "power2.inOut" } })
      .to(".wax-seal", { scale: 1.25, duration: .18, ease: "power2.out" })
      .to(".wax-seal", { scale: 0, rotation: 35, autoAlpha: 0, duration: .32, ease: "back.in(2)" })
      .to(".envelope-flap", { rotationX: 180, transformPerspective: 900, transformOrigin: "50% 0%", duration: .7 }, "-=.05")
      .to(".envelope", { yPercent: 18, autoAlpha: 0, duration: .65, ease: "power2.in" }, "+=.05")
      .fromTo(".letter-paper", { y: 70, scale: .94, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: .9, ease: "power3.out" }, "<.2")
      .fromTo(".letter-paper .ink", { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 1.1, stagger: .5, ease: "power1.inOut" }, "<.35");
    if (open) timeline.current.progress(1);

    // The seal breathes gently while it waits to be opened.
    gsap.to(".wax-seal-glow", { scale: 1.25, autoAlpha: 0, duration: 1.8, ease: "sine.out", repeat: -1 });
    gsap.to(".postmark", { rotation: 360, svgOrigin: "60 60", duration: 60, ease: "none", repeat: -1 });
  }, { scope });

  const toggle = contextSafe((next) => {
    setOpen(next);
    rememberOpened(next);
    const animation = timeline.current;
    if (!motionAllowed()) { animation.progress(next ? 1 : 0); return; }
    if (next) animation.timeScale(1).play(); else animation.timeScale(1.6).reverse();
  });

  return <section ref={scope} className={`letter-hero ${open ? "is-open" : ""}`}>
    <FloatingHearts />
    <article className="letter-paper" aria-hidden={!open} inert={open ? undefined : ""}>
      <p className="letter-to ink handwritten">{t("letterTo", names)}</p>
      {children}
      <div className="letter-footer">
        <p className="letter-signoff ink handwritten">{t("letterSignoff", names)} ♥</p>
        <button type="button" className="fold-button" onClick={() => toggle(false)}>{t("closeLetter")}</button>
      </div>
    </article>

    <div className="envelope" aria-hidden={open} inert={open ? "" : undefined}>
      <svg className="envelope-folds" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 100 50 52 100 100" />
      </svg>
      <svg className="envelope-flap" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 0h100L50 100Z" />
      </svg>
      <div className="envelope-address">
        <p className="handwritten">{t("letterTo", names)}</p>
        <span /><span />
      </div>
      <div className="stamp" aria-hidden="true">
        <span className="stamp-heart">♥</span>
        <small>{t("stampLabel")}</small>
      </div>
      <svg className="postmark" viewBox="0 0 120 120" aria-hidden="true">
        <defs><path id="postmark-ring" d="M60 60m-42 0a42 42 0 1 1 84 0a42 42 0 1 1-84 0" /></defs>
        <circle cx="60" cy="60" r="54" /><circle cx="60" cy="60" r="32" />
        <text><textPath href="#postmark-ring" startOffset="2%">{`${t("postmark")} · ${t("stampLabel")} · `}</textPath></text>
        <text x="60" y="66" textAnchor="middle" className="postmark-heart">♥</text>
      </svg>
      <button type="button" className="wax-seal" onClick={() => toggle(true)} aria-label={t("openLetter")}>
        <span className="wax-seal-glow" aria-hidden="true" />
        <span aria-hidden="true">♥</span>
      </button>
      <p className="seal-hint">{t("sealHint")}</p>
    </div>
  </section>;
}
