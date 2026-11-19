"use client";

import React from "react";

export interface AssistantThinking3DProps {
  size?: "sm" | "md" | "lg";
  isThinking?: boolean;
  label?: string;
  className?: string;
}

export function AssistantThinking3D({
  size = "md",
  isThinking = false,
  label,
  className = "",
}: AssistantThinking3DProps) {
  // Dimension mappings
  const dimensions = {
    sm: { width: 120, height: 90, viewBox: "0 0 240 180" },
    md: { width: 180, height: 135, viewBox: "0 0 240 180" },
    lg: { width: 240, height: 180, viewBox: "0 0 240 180" },
  }[size];

  return (
    <div className={`flex flex-col items-center justify-center select-none ${className}`}>
      <div
        className="relative flex items-center justify-center"
        style={{ width: dimensions.width, height: dimensions.height }}
      >
        {/* Soft Ambient Radial Glow Behind Stack */}
        <div
          className={`absolute rounded-full pointer-events-none transition-all duration-1000 ${
            isThinking
              ? "w-44 h-32 bg-blue-500/25 blur-2xl animate-pulse"
              : "w-36 h-28 bg-blue-400/20 blur-xl"
          }`}
          style={{ top: "35%", left: "50%", transform: "translate(-50%, -50%)" }}
        />

        {/* 3D Glass Layer Stack with Orbit Ring & Particle */}
        <svg
          viewBox={dimensions.viewBox}
          width="100%"
          height="100%"
          className="relative z-10 overflow-visible"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            {/* Top Plate Gradients */}
            <linearGradient id="topPlateSurface" x1="50" y1="20" x2="190" y2="85" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#E0F2FE" stopOpacity="0.95" />
              <stop offset="45%" stopColor="#93C5FD" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="topPlateLeftEdge" x1="50" y1="50" x2="120" y2="90" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#0284C7" stopOpacity="0.85" />
            </linearGradient>
            <linearGradient id="topPlateRightEdge" x1="120" y1="90" x2="190" y2="50" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#0284C7" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#0369A1" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="topGlossReflect" x1="80" y1="30" x2="160" y2="70" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#FFFFFF" stopOpacity="0.75" />
              <stop offset="60%" stopColor="#FFFFFF" stopOpacity="0.1" />
              <stop offset="100%" stopColor="#FFFFFF" stopOpacity="0" />
            </linearGradient>

            {/* Middle Plate Gradients */}
            <linearGradient id="midPlateSurface" x1="50" y1="50" x2="190" y2="115" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#60A5FA" stopOpacity="0.9" />
              <stop offset="50%" stopColor="#3B82F6" stopOpacity="0.85" />
              <stop offset="100%" stopColor="#2563EB" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="midPlateLeftEdge" x1="50" y1="80" x2="120" y2="120" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#2563EB" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#1D4ED8" stopOpacity="0.9" />
            </linearGradient>
            <linearGradient id="midPlateRightEdge" x1="120" y1="120" x2="190" y2="80" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#1D4ED8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#1E40AF" stopOpacity="0.95" />
            </linearGradient>

            {/* Bottom Plate Gradients */}
            <linearGradient id="botPlateSurface" x1="50" y1="80" x2="190" y2="145" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#3B82F6" stopOpacity="0.85" />
              <stop offset="50%" stopColor="#1D4ED8" stopOpacity="0.9" />
              <stop offset="100%" stopColor="#1E3A8A" stopOpacity="0.95" />
            </linearGradient>
            <linearGradient id="botPlateLeftEdge" x1="50" y1="110" x2="120" y2="150" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#1D4ED8" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#172554" stopOpacity="0.95" />
            </linearGradient>
            <linearGradient id="botPlateRightEdge" x1="120" y1="150" x2="190" y2="110" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#172554" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#0F172A" stopOpacity="0.9" />
            </linearGradient>

            {/* Orbit Glow Filter */}
            <filter id="glowParticle" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Plate Drop Shadow Filter */}
            <filter id="layerShadow" x="-20%" y="-20%" width="140%" height="160%">
              <feDropShadow dx="0" dy="6" stdDeviation="5" floodColor="#0F2D6B" floodOpacity="0.25" />
            </filter>
            <filter id="bottomGlow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" result="blur" />
            </filter>
          </defs>

          {/* Bottom Ambient Ground Reflection */}
          <ellipse cx="120" cy="148" rx="60" ry="16" fill="#3B82F6" opacity="0.35" filter="url(#bottomGlow)" />

          {/* Orbital Ring - Back Section (Under Middle & Top Plates) */}
          <g opacity="0.6">
            <path
              d="M 28 116 C 28 92, 212 92, 212 116"
              stroke="#93C5FD"
              strokeWidth="1.5"
              strokeDasharray="3 3"
              opacity="0.4"
            />
          </g>

          {/* ========================================================= */}
          {/* LAYER 3: BOTTOM GLASS PLATE (Floating Phase 1)            */}
          {/* ========================================================= */}
          <g
            className="transition-transform duration-700 ease-out"
            style={{
              animation: "assistantFloat 4.2s ease-in-out infinite",
              animationDelay: "0.25s",
              transformOrigin: "120px 135px",
            }}
          >
            {/* Left Edge Bevel */}
            <path
              d="M 62 120 L 120 148 L 120 156 L 62 128 Z"
              fill="url(#botPlateLeftEdge)"
            />
            {/* Right Edge Bevel */}
            <path
              d="M 120 148 L 178 120 L 178 128 L 120 156 Z"
              fill="url(#botPlateRightEdge)"
            />
            {/* Top Surface */}
            <path
              d="M 120 96 C 123 94.5 127 94.5 130 96 L 174 116 C 177 117.5 178.5 120 177 122 L 126 147 C 123 148.5 117 148.5 114 147 L 63 122 C 61.5 120 63 117.5 66 116 Z"
              fill="url(#botPlateSurface)"
              stroke="#60A5FA"
              strokeWidth="1.2"
              strokeOpacity="0.6"
              filter="url(#layerShadow)"
            />
          </g>

          {/* ========================================================= */}
          {/* LAYER 2: MIDDLE GLASS PLATE (Floating Phase 2)            */}
          {/* ========================================================= */}
          <g
            className="transition-transform duration-700 ease-out"
            style={{
              animation: "assistantFloat 4.2s ease-in-out infinite",
              animationDelay: "0.12s",
              transformOrigin: "120px 105px",
            }}
          >
            {/* Left Edge Bevel */}
            <path
              d="M 62 90 L 120 118 L 120 126 L 62 98 Z"
              fill="url(#midPlateLeftEdge)"
            />
            {/* Right Edge Bevel */}
            <path
              d="M 120 118 L 178 90 L 178 98 L 120 126 Z"
              fill="url(#midPlateRightEdge)"
            />
            {/* Top Surface */}
            <path
              d="M 120 66 C 123 64.5 127 64.5 130 66 L 174 86 C 177 87.5 178.5 90 177 92 L 126 117 C 123 118.5 117 118.5 114 117 L 63 92 C 61.5 90 63 87.5 66 86 Z"
              fill="url(#midPlateSurface)"
              stroke="#93C5FD"
              strokeWidth="1.2"
              strokeOpacity="0.8"
              filter="url(#layerShadow)"
            />
          </g>

          {/* Orbital Ring - Front Section (Wraps over Bottom & Mid, Under Top) */}
          <g>
            <path
              d="M 212 116 C 212 140, 28 140, 28 116"
              stroke="#BAE6FD"
              strokeWidth="1.8"
              opacity="0.85"
            />
          </g>

          {/* ========================================================= */}
          {/* LAYER 1: TOP GLOSSY GLASS PLATE (Floating Phase 3)        */}
          {/* ========================================================= */}
          <g
            className="transition-transform duration-700 ease-out"
            style={{
              animation: "assistantFloat 4.2s ease-in-out infinite",
              animationDelay: "0s",
              transformOrigin: "120px 75px",
            }}
          >
            {/* Left Edge Bevel */}
            <path
              d="M 62 60 L 120 88 L 120 96 L 62 68 Z"
              fill="url(#topPlateLeftEdge)"
            />
            {/* Right Edge Bevel */}
            <path
              d="M 120 88 L 178 60 L 178 68 L 120 96 Z"
              fill="url(#topPlateRightEdge)"
            />
            {/* Top Surface */}
            <path
              d="M 120 36 C 123 34.5 127 34.5 130 36 L 174 56 C 177 57.5 178.5 60 177 62 L 126 87 C 123 88.5 117 88.5 114 87 L 63 62 C 61.5 60 63 57.5 66 56 Z"
              fill="url(#topPlateSurface)"
              stroke="#FFFFFF"
              strokeWidth="1.5"
              filter="url(#layerShadow)"
            />
            {/* Gloss Reflection Highlights on Top Plate */}
            <path
              d="M 120 38 L 155 54 C 152 57 135 63 118 63 C 105 63 85 58 85 54 Z"
              fill="url(#topGlossReflect)"
            />
            <circle cx="120" cy="40" r="3" fill="#FFFFFF" opacity="0.9" />
          </g>

          {/* ========================================================= */}
          {/* ORBITING GLOWING PARTICLE                                 */}
          {/* ========================================================= */}
          <g>
            {/* Elliptical Path Motion for the Particle */}
            <ellipse
              cx="120"
              cy="116"
              rx="92"
              ry="24"
              fill="none"
              stroke="transparent"
              id="orbitTrack"
            />
            {/* Animated Particle */}
            <circle r="4.5" fill="#38BDF8" filter="url(#glowParticle)">
              <animateMotion
                dur={isThinking ? "2.6s" : "4.8s"}
                repeatCount="indefinite"
                rotate="auto"
              >
                <mpath href="#orbitTrack" />
              </animateMotion>
            </circle>
            {/* Hot Center Core for Particle */}
            <circle r="2" fill="#FFFFFF">
              <animateMotion
                dur={isThinking ? "2.6s" : "4.8s"}
                repeatCount="indefinite"
                rotate="auto"
              >
                <mpath href="#orbitTrack" />
              </animateMotion>
            </circle>
          </g>
        </svg>
      </div>

      {/* Optional Contextual Loading Label */}
      {label && (
        <div className="mt-3 text-center animate-fade-in">
          <div className="text-xs font-semibold text-slate-700 flex items-center justify-center gap-2">
            <span className="size-2 rounded-full bg-blue-500 animate-ping" />
            <span>{label}</span>
          </div>
          <p className="text-[10px] text-slate-400 mt-0.5">Searching authorized project sources with zero fabrication</p>
        </div>
      )}

      {/* Embedded CSS for smooth floating motion */}
      <style jsx>{`
        @keyframes assistantFloat {
          0%,
          100% {
            transform: translateY(0px) rotateX(0deg);
          }
          50% {
            transform: translateY(-8px) rotateX(1deg);
          }
        }
      `}</style>
    </div>
  );
}

export default AssistantThinking3D;
