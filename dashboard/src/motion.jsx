// Shared GSAP motion for the anniversary and mailbox pages. Everything here only
// runs when the visitor has not asked for reduced motion.
import { Fragment, useRef } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP, ScrollTrigger);

export { gsap, ScrollTrigger, useGSAP };

export const MOTION_OK = "(prefers-reduced-motion: no-preference)";
const FINE_POINTER = "(hover: hover) and (pointer: fine)";

// Some embedded or power-saving views report "visible" but barely draw frames.
// Content starts hidden for the entrance, so if the ~2.4s intro has not finished
// well after it should have, finish it and drive GSAP from timers instead.
function guardAgainstStalledFrames(intro) {
  let ticking;
  const timer = window.setTimeout(() => {
    if (intro.progress() === 1 || document.visibilityState !== "visible") return;
    intro.progress(1);
    gsap.set(".reveal", { y: 0, autoAlpha: 1, overwrite: true });
    ticking = window.setInterval(() => gsap.ticker.tick(), 1000 / 30);
  }, 4000);
  return () => { window.clearTimeout(timer); window.clearInterval(ticking); };
}

export function motionAllowed() {
  return window.matchMedia(MOTION_OK).matches;
}

/** Run `setup` only when motion is allowed; GSAP reverts it if that changes. */
export function withMotion(setup, query = MOTION_OK) {
  const mm = gsap.matchMedia();
  mm.add(query, setup);
  return () => mm.revert();
}

/**
 * Page entrance: hero lines rise in, the welcome card settles, and every
 * `.reveal` block fades up the first time it scrolls into view.
 */
export function useIntro(scope, dependencies = []) {
  useGSAP(() => withMotion(() => {
    const intro = gsap.timeline({ defaults: { ease: "power3.out", duration: .8 } });
    intro
      .from(".brand-mark", { scale: 0, rotation: -45, duration: .9, ease: "back.out(2.2)" })
      .from(".rail-link", { x: -14, autoAlpha: 0, stagger: .07, duration: .6 }, "<.15")
      .from(".hero .breadcrumb, .hero .eyebrow", { y: 14, autoAlpha: 0, stagger: .08 }, "<")
      .from(".hero h1 .word", { yPercent: 110, autoAlpha: 0, rotation: 4, stagger: .06, duration: .9 }, "<.1")
      .from(".hero-heart", { scale: 0, rotation: -60, duration: .9, ease: "elastic.out(1, .45)" }, "<.35")
      .from(".hero .subtitle, .hero-actions > *", { y: 12, autoAlpha: 0, stagger: .08 }, "<.1")
      .from(".letter-hero", { y: 34, scale: .97, autoAlpha: 0, duration: 1 }, "<.05")
      .from(".mini-stats > div", { y: 22, autoAlpha: 0, stagger: .1, duration: .7 }, "<.3");

    // A gentle double heartbeat on the title heart, then a pause.
    gsap.timeline({ repeat: -1, repeatDelay: 2.4, delay: 2 })
      .to(".hero-heart", { scale: 1.22, duration: .16, ease: "power2.out" })
      .to(".hero-heart", { scale: 1, duration: .24, ease: "power2.in" })
      .to(".hero-heart", { scale: 1.14, duration: .14, ease: "power2.out" })
      .to(".hero-heart", { scale: 1, duration: .5, ease: "elastic.out(1, .4)" });

    const blocks = gsap.utils.toArray(".reveal");
    gsap.set(blocks, { y: 40, autoAlpha: 0 });
    ScrollTrigger.batch(blocks, {
      start: "top 88%",
      once: true,
      onEnter: (batch) => gsap.to(batch, { y: 0, autoAlpha: 1, stagger: .12, duration: .9, ease: "power3.out", overwrite: true }),
    });
    return guardAgainstStalledFrames(intro);
  }), { scope, dependencies });
}

/** Re-run the title words when the text changes (e.g. switching language). */
export function useWordsRefresh(scope, key) {
  const previous = useRef(key);
  useGSAP(() => {
    if (previous.current === key) return;
    previous.current = key;
    return withMotion(() => {
      gsap.from(".hero h1 .word, .hero .subtitle", { yPercent: 60, autoAlpha: 0, stagger: .04, duration: .55, ease: "power3.out" });
    });
  }, { scope, dependencies: [key] });
}

/** Split a sentence into animatable words, keeping the spaces readable. */
export function words(text) {
  return text.split(" ").map((word, index, all) => (
    <Fragment key={index}><span className="word-mask"><span className="word">{word}</span></span>{index < all.length - 1 ? " " : ""}</Fragment>
  ));
}

/** Buttons that lean toward the pointer, then spring back. */
export function useMagnetic(ref, strength = .28) {
  useGSAP(() => withMotion(() => {
    const element = ref.current;
    if (!element) return;
    const x = gsap.quickTo(element, "x", { duration: .5, ease: "power3.out" });
    const y = gsap.quickTo(element, "y", { duration: .5, ease: "power3.out" });
    const move = (event) => {
      if (element.disabled) return;
      const box = element.getBoundingClientRect();
      x((event.clientX - box.left - box.width / 2) * strength);
      y((event.clientY - box.top - box.height / 2) * strength);
    };
    const leave = () => { x(0); y(0); };
    element.addEventListener("pointermove", move);
    element.addEventListener("pointerleave", leave);
    return () => { element.removeEventListener("pointermove", move); element.removeEventListener("pointerleave", leave); };
  }, `${MOTION_OK} and ${FINE_POINTER}`), { dependencies: [ref] });
}

/** Little hearts that float up from an element, e.g. after a note is sent. */
export function burstHearts(origin, count = 14) {
  if (!origin || !motionAllowed()) return;
  const box = origin.getBoundingClientRect();
  const layer = document.createElement("div");
  layer.className = "heart-burst";
  layer.setAttribute("aria-hidden", "true");
  document.body.appendChild(layer);
  const colors = ["#c4566f", "#e48aa0", "#f2b5c0", "#b77fd0", "#e9a07f"];
  const hearts = Array.from({ length: count }, () => {
    const heart = document.createElement("span");
    heart.textContent = "♥";
    heart.style.color = gsap.utils.random(colors);
    heart.style.left = `${box.left + box.width / 2}px`;
    heart.style.top = `${box.top + box.height / 2}px`;
    layer.appendChild(heart);
    return heart;
  });
  gsap.timeline({ onComplete: () => layer.remove() })
    .fromTo(hearts, { scale: 0, xPercent: -50, yPercent: -50 }, {
      x: () => gsap.utils.random(-140, 140),
      y: () => gsap.utils.random(-190, -60),
      rotation: () => gsap.utils.random(-50, 50),
      scale: () => gsap.utils.random(.7, 1.6),
      duration: () => gsap.utils.random(.7, 1.1),
      ease: "power3.out",
      stagger: .015,
    })
    .to(hearts, { y: "+=50", autoAlpha: 0, duration: .9, ease: "power1.in", stagger: .015 }, "-=.45");
}

/** Make newly rendered children of `selector` float in once; returns the new ones. */
export function revealNew(selector, vars = {}) {
  const fresh = gsap.utils.toArray(selector).filter((element) => !element.dataset.shown);
  fresh.forEach((element) => { element.dataset.shown = "true"; });
  if (fresh.length && motionAllowed()) {
    gsap.from(fresh, { y: 26, autoAlpha: 0, scale: .96, duration: .7, ease: "power3.out", stagger: .06, clearProps: "transform,opacity,visibility", ...vars });
  }
  return fresh;
}

/** Fade an element away before it is removed. Resolves immediately without motion. */
export function animateOut(element, vars = {}) {
  if (!element || !motionAllowed()) return Promise.resolve();
  return new Promise((resolve) => {
    gsap.to(element, { scale: .85, autoAlpha: 0, rotation: gsap.utils.random(-6, 6), duration: .4, ease: "power2.in", ...vars, onComplete: resolve });
  });
}
