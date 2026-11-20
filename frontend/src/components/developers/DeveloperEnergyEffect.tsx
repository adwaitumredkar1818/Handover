"use client";

import React, { useId } from "react";

interface DeveloperEnergyEffectProps {
  className?: string;
  ariaLabel?: string;
}

/**
 * DeveloperEnergyEffect
 *
 * Implements the sci-fi 3D isometric cyan holographic energy pedestal:
 * - Placed with increased distance beneath each developer card.
 * - Wide tilted holographic light beam fanning out at an angle up to both bottom corners of the card.
 * - Underside card illumination edge and radiant ambient aura that "glows up the card".
 * - High-tech volumetric laser boundary rays and inner directional beam lines.
 * - Rising diamond sparkle particles ascending along the tilted energy beam.
 * - Multi-faceted dark isometric base block with glowing turquoise cavity pool.
 * - Bouncing dual-layer cyan wireframe outline rings.
 */
export const DeveloperEnergyEffect: React.FC<DeveloperEnergyEffectProps> = ({
  className = "",
  ariaLabel = "Animated cyan energy platform illuminating card",
}) => {
  const reactId = useId();
  const id = reactId.replace(/:/g, "_");

  const gradBeam = `gradBeam_${id}`;
  const gradCavity = `gradCavity_${id}`;
  const gradUnderGlow = `gradUnderGlow_${id}`;
  const filterGlow = `filterGlow_${id}`;
  const filterSoft = `filterSoft_${id}`;
  const filterIntense = `filterIntense_${id}`;

  return (
    <div
      className={`relative w-[340px] h-[230px] -mt-1 flex items-center justify-center pointer-events-none select-none ${className}`}
      aria-hidden="true"
      role="presentation"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 340 240"
        width="340"
        height="240"
        className="overflow-visible"
        aria-label={ariaLabel}
      >
        <defs>
          {/* Intense neon glow filter for laser boundaries and card bottom */}
          <filter id={filterIntense} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="4.5" result="blur1" />
            <feGaussianBlur stdDeviation="1.5" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Standard cyan glow filter */}
          <filter id={filterGlow} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Wide ambient soft illumination filter */}
          <filter id={filterSoft} x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="12" />
          </filter>

          {/* Central cavity pool gradient */}
          <linearGradient id={gradCavity} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="5%" stopColor="#0d1b2a" stopOpacity={1} />
            <stop offset="45%" stopColor="#0284c7" stopOpacity={1} />
            <stop offset="85%" stopColor="#00f2fe" stopOpacity={1} />
            <stop offset="100%" stopColor="#a5f3fc" stopOpacity={1} />
          </linearGradient>

          {/* Angled vertical beam gradient fanning upward toward the card */}
          <linearGradient
            id={gradBeam}
            x1="170"
            y1="190"
            x2="170"
            y2="0"
            gradientUnits="userSpaceOnUse"
          >
            <stop offset="0%" stopColor="#00f2fe" stopOpacity={0.88} />
            <stop
              className="dev-energy-animated-stop"
              offset="25%"
              stopColor="#00f2fe"
              stopOpacity={0.55}
            />
            <stop offset="60%" stopColor="#0284c7" stopOpacity={0.28} />
            <stop offset="90%" stopColor="#00f2fe" stopOpacity={0.16} />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity={0.32} />
          </linearGradient>

          {/* Underside horizontal glow gradient where beam hits card */}
          <linearGradient id={gradUnderGlow} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00f2fe" stopOpacity={0.1} />
            <stop offset="15%" stopColor="#00f2fe" stopOpacity={0.85} />
            <stop offset="50%" stopColor="#a5f3fc" stopOpacity={1} />
            <stop offset="85%" stopColor="#00f2fe" stopOpacity={0.85} />
            <stop offset="100%" stopColor="#00f2fe" stopOpacity={0.1} />
          </linearGradient>
        </defs>

        <g>
          {/* Ambient wide cyan glow that bathes and "glows up" the bottom of the card */}
          <ellipse
            cx="170"
            cy="0"
            rx="165"
            ry="24"
            fill="rgba(0, 242, 254, 0.35)"
            filter={`url(#${filterSoft})`}
          />
          <ellipse
            cx="170"
            cy="0"
            rx="120"
            ry="12"
            fill="rgba(165, 243, 252, 0.45)"
            filter={`url(#${filterGlow})`}
          />

          {/* --- ANGLED HOLOGRAPHIC ENERGY BEAM TILTED UP TO CARD ENDS --- */}
          {/* 
            Trapezoid light frustum:
            Top-Left: (8, 0) -> Touching the left bottom corner of card
            Top-Right: (332, 0) -> Touching the right bottom corner of card
            Bottom-Right: (215, 185) -> Meeting right edge of pedestal cavity
            Bottom-Apex: (170, 202) -> Bottom center of pedestal well
            Bottom-Left: (125, 185) -> Meeting left edge of pedestal cavity
          */}
          <polygon
            strokeWidth="0"
            fill={`url(#${gradBeam})`}
            points="8,0 332,0 215,185 170,202 125,185"
          />

          {/* Left angled neon laser boundary tilted outward to left card corner */}
          <line
            x1="125"
            y1="185"
            x2="8"
            y2="0"
            stroke="#00f2fe"
            strokeWidth="2.2"
            strokeOpacity={0.9}
            filter={`url(#${filterIntense})`}
          />

          {/* Right angled neon laser boundary tilted outward to right card corner */}
          <line
            x1="215"
            y1="185"
            x2="332"
            y2="0"
            stroke="#00f2fe"
            strokeWidth="2.2"
            strokeOpacity={0.9}
            filter={`url(#${filterIntense})`}
          />

          {/* Card underside illumination line (spans full width of card) */}
          <line
            x1="8"
            y1="0"
            x2="332"
            y2="0"
            stroke={`url(#${gradUnderGlow})`}
            strokeWidth="3.5"
            filter={`url(#${filterIntense})`}
          />

          {/* Secondary inner volumetric rays fanning outward at intermediate angles */}
          <line
            x1="140"
            y1="188"
            x2="70"
            y2="0"
            stroke="#38bdf8"
            strokeWidth="1.2"
            strokeOpacity={0.4}
          />
          <line
            x1="155"
            y1="194"
            x2="130"
            y2="0"
            stroke="#a5f3fc"
            strokeWidth="1.4"
            strokeOpacity={0.5}
          />
          <line
            x1="185"
            y1="194"
            x2="210"
            y2="0"
            stroke="#a5f3fc"
            strokeWidth="1.4"
            strokeOpacity={0.5}
          />
          <line
            x1="200"
            y1="188"
            x2="270"
            y2="0"
            stroke="#38bdf8"
            strokeWidth="1.2"
            strokeOpacity={0.4}
          />

          {/* Floating diamond particles rising upward along the tilted beam */}
          <g className="dev-energy-particles" style={{ transformOrigin: "170px 100px" }}>
            <polygon
              fill="#ffffff"
              points="170,40 174,44 170,48 166,44"
              filter={`url(#${filterGlow})`}
            />
            <polygon
              fill="#a5f3fc"
              points="130,85 135,90 130,95 125,90"
              filter={`url(#${filterGlow})`}
            />
            <polygon
              fill="#22d3ee"
              points="210,65 215,70 210,75 205,70"
              filter={`url(#${filterGlow})`}
            />
            <polygon
              fill="#00f2fe"
              points="90,45 94,49 90,53 86,49"
              opacity={0.85}
            />
            <polygon
              fill="#67e8f9"
              points="250,42 254,46 250,50 246,46"
              opacity={0.85}
            />
            <polygon
              fill="#38bdf8"
              points="150,130 153,133 150,136 147,133"
              opacity={0.7}
            />
            <polygon
              fill="#a5f3fc"
              points="190,120 193,123 190,126 187,123"
              opacity={0.7}
            />
          </g>

          {/* --- 3D ISOMETRIC ENERGY PLATFORM PEDESTAL --- */}
          {/* Wireframe Ring 1: Bouncing cyan geometric outline */}
          <g className="dev-energy-bounce" style={{ transformOrigin: "170px 195px" }}>
            <polygon
              strokeWidth="1.6"
              stroke="#00f2fe"
              strokeOpacity={0.85}
              fill="none"
              points="170,158 230,185 170,212 110,185"
            />
          </g>

          {/* Wireframe Ring 2: Lower delayed bouncing cyan wireframe */}
          <g className="dev-energy-bounce2" style={{ transformOrigin: "170px 195px" }}>
            <polygon
              strokeWidth="1.6"
              stroke="#38bdf8"
              strokeOpacity={0.65}
              fill="none"
              points="170,158 230,185 170,212 110,185"
            />
          </g>

          {/* Solid Isometric Base Rim Top */}
          <polygon
            strokeWidth="1"
            stroke="#2d3748"
            fill="#232d3d"
            points="170,156 232,185 170,214 108,185"
          />

          {/* Glowing central cyan inner well pool */}
          <polygon
            strokeWidth="0"
            fill={`url(#${gradCavity})`}
            filter={`url(#${filterIntense})`}
            points="170,166 215,185 170,204 125,185"
          />

          {/* Left inner well wall */}
          <polygon
            strokeWidth="0"
            fill="#0369a1"
            points="125,185 170,204 170,210 125,191"
          />

          {/* Right inner well wall */}
          <polygon
            strokeWidth="0"
            fill="#0284c7"
            points="170,204 215,185 215,191 170,210"
          />

          {/* Left front base facet */}
          <polygon
            strokeWidth="1"
            stroke="#1f2937"
            fill="#18202c"
            points="108,185 170,214 170,234 108,205"
          />

          {/* Right front base facet */}
          <polygon
            strokeWidth="1"
            stroke="#111827"
            fill="#111620"
            points="170,214 232,185 232,205 170,234"
          />
        </g>
      </svg>
    </div>
  );
};
