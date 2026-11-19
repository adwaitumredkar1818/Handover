"use client";

import React, { useId } from "react";

interface DeveloperEnergyEffectProps {
  className?: string;
  ariaLabel?: string;
}

/**
 * DeveloperEnergyEffect
 *
 * Implements the 3D isometric cyan energy platform beneath each developer card:
 * - Two bouncing cyan wireframe outlines (#bounce, #bounce2)
 * - Multi-faceted dark isometric base block with glowing turquoise cavity floor
 * - Angled light/energy beam spreading outward at a tilt up to both card ends
 * - Floating diamond sparkle particles (#particles)
 * - Ambient upward cyan illumination casting light onto the card above
 * - Unique SVG gradient and filter IDs to prevent collisions across multiple instances
 */
export const DeveloperEnergyEffect: React.FC<DeveloperEnergyEffectProps> = ({
  className = "",
  ariaLabel = "Animated cyan energy platform illuminating card",
}) => {
  const reactId = useId();
  const id = reactId.replace(/:/g, "_");

  const gradBeam = `gradBeam_${id}`;
  const gradCavity = `gradCavity_${id}`;
  const filterGlow = `filterGlow_${id}`;
  const filterSoft = `filterSoft_${id}`;

  return (
    <div
      className={`relative w-[280px] h-[190px] mt-6 sm:mt-7 flex items-center justify-center pointer-events-none select-none ${className}`}
      aria-hidden="true"
      role="presentation"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 260 210"
        width="260"
        height="210"
        className="overflow-visible"
        aria-label={ariaLabel}
      >
        <defs>
          {/* Subtle cyan glow filter */}
          <filter id={filterGlow} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Wide ambient soft illumination filter */}
          <filter id={filterSoft} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="8" />
          </filter>

          {/* Central cavity pool gradient */}
          <linearGradient id={gradCavity} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="10%" stopColor="#16222f" stopOpacity={1} />
            <stop offset="60%" stopColor="#0891b2" stopOpacity={1} />
            <stop offset="100%" stopColor="#00f2fe" stopOpacity={1} />
          </linearGradient>

          {/* Angled vertical beam gradient fanning upward toward the card */}
          <linearGradient id={gradBeam} x1="130" y1="140" x2="130" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#00f2fe" stopOpacity={0.8} />
            <stop
              className="dev-energy-animated-stop"
              offset="35%"
              stopColor="#00f2fe"
              stopOpacity={0.45}
            />
            <stop offset="70%" stopColor="#0891b2" stopOpacity={0.2} />
            <stop offset="100%" stopColor="#00f2fe" stopOpacity={0.06} />
          </linearGradient>
        </defs>

        <g style={{ order: -1 }}>
          {/* Ambient cyan lighting casting upward onto bottom of developer card */}
          <ellipse
            cx="130"
            cy="10"
            rx="115"
            ry="18"
            fill="rgba(0, 242, 254, 0.16)"
            filter={`url(#${filterSoft})`}
          />

          {/* Layer 1: Outlined bouncing cyan geometric wireframe */}
          <g className="dev-energy-bounce" style={{ transformOrigin: "130px 145px" }}>
            <polygon
              strokeWidth="1.5"
              stroke="#00f2fe"
              fill="none"
              points="130,110 185,140 130,170 75,140"
            />
          </g>

          {/* Layer 2: Deeper bouncing cyan wireframe outline */}
          <g className="dev-energy-bounce2" style={{ transformOrigin: "130px 145px" }}>
            <polygon
              strokeWidth="1.5"
              stroke="#22d3ee"
              strokeOpacity={0.6}
              fill="none"
              points="130,110 185,140 130,170 75,140"
            />
          </g>

          {/* Solid isometric base top rim */}
          <polygon
            strokeWidth="1"
            stroke="#2d3748"
            fill="#2c3647"
            points="130,105 190,138 130,171 70,138"
          />

          {/* Glowing central cyan inner well pool */}
          <polygon
            strokeWidth="0"
            fill={`url(#${gradCavity})`}
            filter={`url(#${filterGlow})`}
            points="130,114 175,138 130,162 85,138"
          />

          {/* Left inner well wall */}
          <polygon
            strokeWidth="0"
            fill="#0891b2"
            points="85,138 130,162 130,168 85,144"
          />

          {/* Right inner well wall */}
          <polygon
            strokeWidth="0"
            fill="#06b6d4"
            points="130,162 175,138 175,144 130,168"
          />

          {/* --- ANGLED LIGHT / ENERGY BEAM TILTED UPTO CARD ENDS --- */}
          {/* Main trapezoidal frustum beam expanding outward as it rises */}
          <polygon
            strokeWidth="0"
            fill={`url(#${gradBeam})`}
            points="18,0 242,0 170,140 130,163 90,140"
          />

          {/* Left angled neon boundary ray line extending to left card end */}
          <line
            x1="90"
            y1="140"
            x2="18"
            y2="0"
            stroke="#00f2fe"
            strokeWidth="1.5"
            strokeOpacity={0.85}
            filter={`url(#${filterGlow})`}
          />

          {/* Right angled neon boundary ray line extending to right card end */}
          <line
            x1="170"
            y1="140"
            x2="242"
            y2="0"
            stroke="#00f2fe"
            strokeWidth="1.5"
            strokeOpacity={0.85}
            filter={`url(#${filterGlow})`}
          />

          {/* Top card underside illumination edge */}
          <line
            x1="18"
            y1="0"
            x2="242"
            y2="0"
            stroke="#a5f3fc"
            strokeWidth="2"
            strokeOpacity={0.7}
            filter={`url(#${filterGlow})`}
          />

          {/* Secondary inner subtle ray beams */}
          <line
            x1="110"
            y1="142"
            x2="75"
            y2="0"
            stroke="#38bdf8"
            strokeWidth="1"
            strokeOpacity={0.35}
          />
          <line
            x1="150"
            y1="142"
            x2="185"
            y2="0"
            stroke="#38bdf8"
            strokeWidth="1"
            strokeOpacity={0.35}
          />

          {/* Floating diamond particles inside the tilted energy beam */}
          <g className="dev-energy-particles" style={{ transformOrigin: "130px 80px" }}>
            <polygon
              fill="#a5f3fc"
              points="105,75 110,80 105,85 100,80"
              filter={`url(#${filterGlow})`}
            />
            <polygon
              fill="#22d3ee"
              points="155,55 160,60 155,65 150,60"
            />
            <polygon
              fill="#ffffff"
              points="130,40 133,43 130,46 127,43"
              filter={`url(#${filterGlow})`}
            />
            <polygon
              fill="#67e8f9"
              points="78,35 82,39 78,43 74,39"
              opacity={0.85}
            />
            <polygon
              fill="#00f2fe"
              points="182,30 186,34 182,38 178,34"
              opacity={0.85}
            />
          </g>

          {/* Left front base facet */}
          <polygon
            strokeWidth="1"
            stroke="#1f2937"
            fill="#1e2633"
            points="70,138 130,171 130,195 70,162"
          />

          {/* Right front base facet */}
          <polygon
            strokeWidth="1"
            stroke="#111827"
            fill="#141a24"
            points="130,171 190,138 190,162 130,195"
          />
        </g>
      </svg>
    </div>
  );
};
