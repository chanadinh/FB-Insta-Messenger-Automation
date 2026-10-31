import { useRef } from "react";
import { gsap, useGSAP, withMotion } from "./motion";

/** Soft colour glows drifting slowly behind the page. */
export function AmbientBackdrop() {
  const scope = useRef(null);
  useGSAP(() => withMotion(() => {
    gsap.utils.toArray(".ambient-glow").forEach((glow, index) => {
      gsap.to(glow, {
        x: () => gsap.utils.random(-90, 90),
        y: () => gsap.utils.random(-70, 70),
        scale: () => gsap.utils.random(.85, 1.2),
        duration: 14 + index * 4,
        ease: "sine.inOut",
        repeat: -1,
        yoyo: true,
        repeatRefresh: true,
      });
    });
  }), { scope });
  return <div ref={scope} className="ambient" aria-hidden="true">
    <span className="ambient-glow rose" /><span className="ambient-glow lilac" /><span className="ambient-glow peach" />
  </div>;
}

/** Hearts and petals that rise and sway inside their container. */
export function FloatingHearts({ count = 10 }) {
  const scope = useRef(null);
  useGSAP(() => withMotion(() => {
    const box = scope.current.getBoundingClientRect();
    gsap.utils.toArray(".floating-heart", scope.current).forEach((heart) => {
      const rise = () => {
        gsap.set(heart, {
          x: gsap.utils.random(0, box.width),
          y: box.height + 20,
          scale: gsap.utils.random(.5, 1.25),
          rotation: gsap.utils.random(-30, 30),
          autoAlpha: 0,
        });
        const duration = gsap.utils.random(9, 15);
        gsap.timeline({ onComplete: rise, delay: gsap.utils.random(0, 6) })
          .to(heart, { autoAlpha: gsap.utils.random(.35, .8), duration: 1.2 })
          .to(heart, { y: -40, duration, ease: "none" }, 0)
          .to(heart, { x: `+=${gsap.utils.random(-60, 60)}`, rotation: `+=${gsap.utils.random(-40, 40)}`, duration: duration / 4, ease: "sine.inOut", repeat: 3, yoyo: true }, 0)
          .to(heart, { autoAlpha: 0, duration: 1.6 }, duration - 1.6);
      };
      rise();
    });
  }), { scope });
  return <div ref={scope} className="floating-hearts" aria-hidden="true">
    {Array.from({ length: count }, (_, index) => <span key={index} className={`floating-heart ${index % 3 === 0 ? "petal" : ""}`}>{index % 3 === 0 ? "❀" : "♥"}</span>)}
  </div>;
}
