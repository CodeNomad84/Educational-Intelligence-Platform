import { useEffect, useState } from "react";
import { AnimatePresence, motion, type TargetAndTransition, type Transition } from "framer-motion";

export type MascotMood = "idle" | "thinking" | "insight" | "salute";

// Local copies live in public/assets/mascot/. They used to come from a Lovable asset manifest whose URLs
// (/__l5e/assets-v1/…) only resolve on Lovable's hosting, so every pose was broken anywhere else — including under the
// Django/dev-proxy setup (docs/changes/0040). The state → file mapping is the same contract as before.
const poses: Record<MascotMood, string> = {
  idle: "/assets/mascot/mascot-idle.png",
  thinking: "/assets/mascot/mascot-thinking.png",
  insight: "/assets/mascot/mascot-insight.png",
  salute: "/assets/mascot/mascot-salute.png",
};

const stateAnim: Record<MascotMood, { animate: TargetAndTransition; transition: Transition }> = {
  idle: { animate: { rotate: [-1, 1, -1], y: 0, scale: 1 }, transition: { rotate: { duration: 3.5, repeat: Infinity, ease: "easeInOut" } } },
  thinking: { animate: { rotate: [-2, 1.5, -2], y: 0, scale: 1 }, transition: { rotate: { duration: 4.5, repeat: Infinity, ease: "easeInOut" } } },
  insight: { animate: { rotate: 0, y: -8, scale: 1.04 }, transition: { type: "spring", stiffness: 300, damping: 18 } },
  salute: { animate: { rotate: 0, y: 0, scale: [0.96, 1.03, 1] }, transition: { duration: 0.6, ease: "easeOut" } },
};

export function MascotAssistant({ mood: external }: { mood?: MascotMood }) {
  const [greet, setGreet] = useState(true);
  useEffect(() => {
    Object.values(poses).forEach((src) => { const i = new Image(); i.src = src; });
    const t = setTimeout(() => setGreet(false), 3000);
    return () => clearTimeout(t);
  }, []);
  const mood: MascotMood = external && external !== "idle" ? external : greet ? "salute" : "idle";
  const s = stateAnim[mood];

  return (
    <div className="relative mx-auto aspect-square w-52 md:w-full">
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-[12%] rounded-full bg-primary blur-3xl"
        animate={{ opacity: mood === "thinking" ? [0.25, 0.55, 0.25] : mood === "insight" ? 0.3 : 0.12, scale: mood === "thinking" ? [0.9, 1.1, 0.9] : 1 }}
        transition={{ duration: 1.8, repeat: mood === "thinking" ? Infinity : 0, ease: "easeInOut" }}
      />
      {/* breathing loop */}
      <motion.div className="relative size-full" style={{ transformOrigin: "50% 100%" }}
        animate={{ y: [0, -6, 0], scaleY: [1, 1.015, 1] }} transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}>
        <motion.div className="relative size-full" style={{ transformOrigin: "50% 90%" }} animate={s.animate} transition={s.transition}>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.img key={mood} src={poses[mood]} alt="دستیار هوشمند آرمان نو"
              className="absolute inset-0 size-full object-contain drop-shadow-2xl"
              initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }}
              transition={{ type: "spring", stiffness: 260, damping: 22, opacity: { duration: 0.3 } }} />
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </div>
  );
}
