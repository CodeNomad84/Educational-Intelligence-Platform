import { AnimatePresence, motion, type Transition } from "framer-motion";

import { cn } from "@/lib/utils";
import type { MascotState } from "./dashboard-context";

interface MascotProps {
  state: MascotState;
  size?: number;
  className?: string;
}

const loop = (duration: number, extra: Transition = {}): Transition => ({
  duration,
  repeat: Infinity,
  ease: "easeInOut",
  ...extra,
});

const BURST = Array.from({ length: 12 }, (_, i) => {
  const angle = (i / 12) * Math.PI * 2;
  return { x: Math.cos(angle) * 88, y: Math.sin(angle) * 80, i };
});

const ORBIT = [0, 72, 144, 216, 288].map((deg, i) => {
  const r = (deg * Math.PI) / 180;
  return { cx: 100 + Math.cos(r) * 86, cy: 108 + Math.sin(r) * 78, i };
});

const NODE_FILLS = ["var(--info)", "var(--success)", "var(--primary-glow)", "var(--warning)", "var(--info)"];

/** «رهنما» — the sprout-headed Smart Mentor. Emotionally responsive SVG companion. */
export function Mascot({ state, size = 200, className }: MascotProps) {
  const isThinking = state === "thinking";
  const isAnalytical = state === "analytical";
  const isCelebrate = state === "celebrate";

  const bodyAnimate = isCelebrate
    ? { y: [0, -16, 0, -8, 0], rotate: [0, -4, 4, 0, 0], scale: 1 }
    : isThinking
      ? { y: [-4, -12, -4], rotate: 0, scale: 1 }
      : { y: 0, rotate: 0, scale: [1, 1.025, 1] };

  const bodyTransition = isCelebrate ? loop(1.1) : isThinking ? loop(2.4) : loop(3.6);

  const pupil = isThinking ? { x: 3, y: -5 } : isAnalytical ? { x: -1, y: 1 } : { x: 0, y: 0 };

  return (
    <div className={cn("relative select-none", className)} style={{ width: size, height: size }}>
      <svg viewBox="0 0 200 200" width={size} height={size} role="img" aria-label={`دستیار رهنما — ${STATE_LABEL[state]}`}>
        <defs>
          <radialGradient id="m-aura" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="var(--primary-glow)" stopOpacity="0.55" />
            <stop offset="60%" stopColor="var(--primary)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--primary)" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="m-body" x1="0" y1="0" x2="0.4" y2="1">
            <stop offset="0%" stopColor="var(--mascot-body)" />
            <stop offset="100%" stopColor="var(--mascot-body-2)" />
          </linearGradient>
          <linearGradient id="m-leaf" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--mascot-leaf)" />
            <stop offset="100%" stopColor="var(--success)" />
          </linearGradient>
          <filter id="m-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Aura */}
        <motion.circle
          cx="100"
          cy="108"
          r="92"
          fill="url(#m-aura)"
          animate={{
            opacity: isThinking || isAnalytical ? [0.7, 1, 0.7] : isCelebrate ? 1 : [0.35, 0.5, 0.35],
            scale: isThinking ? [0.95, 1.05, 0.95] : 1,
          }}
          transition={loop(isThinking ? 1.6 : 4)}
        />

        {/* Ground shadow */}
        <motion.ellipse
          cx="100"
          cy="182"
          rx="46"
          ry="7"
          fill="var(--background)"
          opacity="0.6"
          animate={{ scaleX: isCelebrate ? [1, 0.7, 1, 0.85, 1] : isThinking ? [0.85, 0.7, 0.85] : [1, 0.96, 1] }}
          transition={bodyTransition}
        />

        {/* Analytical orbit of data nodes */}
        <AnimatePresence>
          {isAnalytical && (
            <motion.g
              key="orbit"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1, rotate: 360 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={{ opacity: { duration: 0.3 }, scale: { duration: 0.4 }, rotate: { duration: 14, repeat: Infinity, ease: "linear" } }}
              style={{ transformBox: "view-box", transformOrigin: "100px 108px" }}
            >
              <ellipse cx="100" cy="108" rx="86" ry="78" fill="none" stroke="var(--info)" strokeOpacity="0.25" strokeDasharray="3 6" />
              {ORBIT.map((n) => (
                <g key={n.i} filter="url(#m-glow)">
                  <circle cx={n.cx} cy={n.cy} r="5" fill={NODE_FILLS[n.i]} />
                  <circle cx={n.cx} cy={n.cy} r="9" fill="none" stroke={NODE_FILLS[n.i]} strokeOpacity="0.4" />
                </g>
              ))}
            </motion.g>
          )}
        </AnimatePresence>

        {/* Character */}
        <motion.g animate={bodyAnimate} transition={bodyTransition} style={{ transformBox: "view-box", transformOrigin: "100px 170px" }}>
          {/* Sprout */}
          <motion.g
            animate={{ rotate: isCelebrate ? [-14, 14, -14] : [-5, 5, -5] }}
            transition={loop(isCelebrate ? 0.6 : 3)}
            style={{ transformBox: "view-box", transformOrigin: "100px 58px" }}
          >
            <path d="M100 58 C100 46 101 38 100 28" stroke="var(--mascot-leaf)" strokeWidth="4" strokeLinecap="round" fill="none" />
            <path d="M100 34 C88 20 72 22 68 30 C78 38 92 40 100 34 Z" fill="url(#m-leaf)" />
            <path d="M100 30 C110 14 128 14 134 22 C124 32 108 36 100 30 Z" fill="url(#m-leaf)" />
          </motion.g>

          {/* Arms */}
          <motion.ellipse
            cx="42"
            cy="124"
            rx="11"
            ry="18"
            fill="var(--mascot-body-2)"
            animate={{ rotate: isCelebrate ? [20, 60, 20] : isThinking ? 30 : 12 }}
            transition={isCelebrate ? loop(0.5) : { duration: 0.4 }}
            style={{ transformBox: "view-box", transformOrigin: "50px 112px" }}
          />
          <motion.ellipse
            cx="158"
            cy="124"
            rx="11"
            ry="18"
            fill="var(--mascot-body-2)"
            animate={{ rotate: isCelebrate ? [-20, -150, -130, -150] : isThinking ? -60 : -12 }}
            transition={isCelebrate ? loop(0.8) : { duration: 0.4 }}
            style={{ transformBox: "view-box", transformOrigin: "150px 112px" }}
          />

          {/* Body */}
          <ellipse cx="100" cy="114" rx="62" ry="58" fill="url(#m-body)" />
          <ellipse cx="82" cy="86" rx="22" ry="12" fill="var(--foreground)" opacity="0.12" />
          <ellipse cx="100" cy="138" rx="36" ry="26" fill="var(--mascot-belly)" opacity="0.28" />

          {/* Cheeks */}
          <ellipse cx="64" cy="124" rx="9" ry="5.5" fill="var(--mascot-cheek)" opacity={isCelebrate ? 0.8 : 0.5} />
          <ellipse cx="136" cy="124" rx="9" ry="5.5" fill="var(--mascot-cheek)" opacity={isCelebrate ? 0.8 : 0.5} />

          {/* Eyes */}
          {isCelebrate ? (
            <g stroke="var(--mascot-eye)" strokeWidth="5" strokeLinecap="round" fill="none">
              <path d="M68 108 Q79 94 90 108" />
              <path d="M110 108 Q121 94 132 108" />
            </g>
          ) : (
            <motion.g
              animate={{ scaleY: [1, 1, 0.1, 1, 1] }}
              transition={{ duration: 4.2, times: [0, 0.9, 0.93, 0.96, 1], repeat: Infinity }}
              style={{ transformBox: "view-box", transformOrigin: "100px 104px" }}
            >
              <ellipse cx="79" cy="104" rx="13" ry="14.5" fill="var(--foreground)" />
              <ellipse cx="121" cy="104" rx="13" ry="14.5" fill="var(--foreground)" />
              <motion.g animate={pupil} transition={{ type: "spring", stiffness: 120, damping: 14 }}>
                <circle cx="80" cy="106" r="7.5" fill="var(--mascot-eye)" />
                <circle cx="122" cy="106" r="7.5" fill="var(--mascot-eye)" />
                <circle cx="83" cy="103" r="2.6" fill="var(--foreground)" />
                <circle cx="125" cy="103" r="2.6" fill="var(--foreground)" />
              </motion.g>
            </motion.g>
          )}

          {/* Smart glasses */}
          <AnimatePresence>
            {isAnalytical && (
              <motion.g
                key="glasses"
                initial={{ y: -26, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: -26, opacity: 0 }}
                transition={{ type: "spring", stiffness: 260, damping: 18 }}
                filter="url(#m-glow)"
              >
                <circle cx="79" cy="104" r="19" fill="var(--info)" fillOpacity="0.12" stroke="var(--info)" strokeWidth="3.5" />
                <circle cx="121" cy="104" r="19" fill="var(--info)" fillOpacity="0.12" stroke="var(--info)" strokeWidth="3.5" />
                <path d="M98 102 Q100 98 102 102" stroke="var(--info)" strokeWidth="3.5" fill="none" />
                <path d="M60 100 L48 96" stroke="var(--info)" strokeWidth="3" strokeLinecap="round" />
                <path d="M140 100 L152 96" stroke="var(--info)" strokeWidth="3" strokeLinecap="round" />
                <path d="M68 96 L76 92" stroke="var(--foreground)" strokeOpacity="0.7" strokeWidth="2" strokeLinecap="round" />
                <path d="M110 96 L118 92" stroke="var(--foreground)" strokeOpacity="0.7" strokeWidth="2" strokeLinecap="round" />
              </motion.g>
            )}
          </AnimatePresence>

          {/* Mouth */}
          {isCelebrate ? (
            <path d="M84 130 Q100 152 116 130 Z" fill="var(--mascot-eye)" />
          ) : isThinking ? (
            <motion.ellipse cx="104" cy="134" rx="5" ry="5.5" fill="var(--mascot-eye)" animate={{ ry: [5.5, 4, 5.5] }} transition={loop(1.6)} />
          ) : (
            <path
              d={isAnalytical ? "M88 132 Q100 140 112 132" : "M86 130 Q100 144 114 130"}
              stroke="var(--mascot-eye)"
              strokeWidth="4.5"
              strokeLinecap="round"
              fill="none"
            />
          )}
        </motion.g>

        {/* Thought bubbles */}
        <AnimatePresence>
          {isThinking && (
            <motion.g key="thought" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {[
                { cx: 150, cy: 52, r: 4 },
                { cx: 162, cy: 38, r: 6 },
                { cx: 178, cy: 20, r: 9 },
              ].map((b, i) => (
                <motion.circle
                  key={i}
                  {...b}
                  fill="var(--foreground)"
                  animate={{ opacity: [0.2, 0.9, 0.2], y: [0, -3, 0] }}
                  transition={loop(1.4, { delay: i * 0.25 })}
                />
              ))}
            </motion.g>
          )}
        </AnimatePresence>

        {/* Celebration burst */}
        <AnimatePresence>
          {isCelebrate && (
            <motion.g key="burst" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              {BURST.map((p) => (
                <motion.rect
                  key={p.i}
                  x="97"
                  y="105"
                  width={p.i % 2 ? 6 : 8}
                  height={p.i % 2 ? 6 : 3}
                  rx="1.5"
                  fill={["var(--warning)", "var(--success)", "var(--primary-glow)", "var(--info)", "var(--mascot-cheek)"][p.i % 5]}
                  animate={{ x: [0, p.x], y: [0, p.y], opacity: [1, 0], rotate: [0, 180] }}
                  transition={{ duration: 1.1, repeat: Infinity, ease: "easeOut", delay: (p.i % 3) * 0.12 }}
                />
              ))}
              <motion.path
                d="M100 2 L105 14 L118 15 L108 23 L111 36 L100 29 L89 36 L92 23 L82 15 L95 14 Z"
                fill="var(--warning)"
                filter="url(#m-glow)"
                animate={{ scale: [0.8, 1.15, 0.8], rotate: [0, 20, 0] }}
                transition={loop(0.9)}
                style={{ transformBox: "view-box", transformOrigin: "100px 20px" }}
              />
            </motion.g>
          )}
        </AnimatePresence>
      </svg>
    </div>
  );
}

export const STATE_LABEL: Record<MascotState, string> = {
  idle: "آماده کمک",
  thinking: "در حال فکر کردن…",
  analytical: "در حال تحلیل داده‌ها",
  celebrate: "آفرین! مأموریت انجام شد",
};
