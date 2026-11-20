"use client";

import React, { useState } from "react";
import Image from "next/image";
import { Mail, ArrowUpRight } from "lucide-react";
import { Developer } from "./types";

interface DeveloperCardProps {
  developer: Developer;
  priority?: boolean;
}

export const DeveloperCard: React.FC<DeveloperCardProps> = ({
  developer,
  priority = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Toggle expanded state for touch devices and keyboard interaction
  const handleCardClick = (e: React.MouseEvent) => {
    // If the click landed on an interactive link or button, do not toggle
    const target = e.target as HTMLElement;
    if (target.closest("a") || target.closest("button")) {
      return;
    }
    setIsExpanded((prev) => !prev);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setIsExpanded((prev) => !prev);
    }
  };

  return (
    <article
      tabIndex={0}
      aria-label={`${developer.name} - ${developer.role}`}
      data-expanded={isExpanded}
      className="dev-card relative w-[340px] h-[440px] shrink-0"
      style={{
        width: 340,
        height: 440,
        position: "relative",
        overflow: "hidden",
        boxSizing: "border-box",
      }}
      onClick={handleCardClick}
      onKeyDown={handleKeyDown}
    >
      {/* Top-Right Quick Contact Icon */}
      <a
        href={`mailto:${developer.email}`}
        className="dev-card-mail"
        aria-label={`Send email to ${developer.name}`}
        title={`Email ${developer.name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <Mail aria-hidden="true" />
      </a>

      {/* Developer Portrait Container (Full Card Illustration) */}
      <div
        className="dev-card-profile-pic"
        style={{ position: "absolute", overflow: "hidden" }}
      >
        <Image
          src={developer.image}
          alt={developer.avatarAlt}
          width={340}
          height={440}
          priority={priority}
          className="w-full h-full object-cover object-top select-none pointer-events-none"
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      {/* Interactive Bottom Section (Shows Name & Role in default view, expands to full details on hover/tap) */}
      <div className="dev-card-bottom">
        {/* Default State Preview: Always visible so visitor knows who the developer is */}
        <div className="dev-card-default-preview">
          <div className="dev-card-default-name">{developer.name}</div>
          <div className="dev-card-default-role">{developer.role}</div>
        </div>

        {/* Expanded State Content: Full profile details with complete description */}
        <div className="dev-card-content">
          {/* Header block with avatar thumbnail, full name, and role tag */}
          <div className="dev-card-expanded-header">
            <div className="dev-card-avatar-thumb">
              <Image
                src={developer.image}
                alt=""
                width={56}
                height={56}
                className="w-full h-full object-cover object-top"
              />
            </div>
            <div className="dev-card-header-text">
              <span className="dev-card-name">{developer.name}</span>
              <div className="dev-card-role-tag">{developer.role}</div>
            </div>
          </div>

          <div className="dev-card-divider" />

          {/* Full description clearly readable without any truncation */}
          <p className="dev-card-about">{developer.responsibility}</p>

          {/* Quick email display */}
          <a
            href={`mailto:${developer.email}`}
            className="dev-card-email-link"
            onClick={(e) => e.stopPropagation()}
            title={`Send email to ${developer.email}`}
          >
            <Mail className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate">{developer.email}</span>
          </a>
        </div>

        {/* Social Links & Action Button (Visible in both default and expanded states) */}
        <div className="dev-card-bottom-bar">
          <div className="dev-card-social-links">
            {/* GitHub Profile */}
            <a
              href={developer.github}
              target="_blank"
              rel="noopener noreferrer"
              className="dev-card-social-link"
              aria-label={`${developer.name}'s GitHub Profile`}
              title="GitHub Profile"
              onClick={(e) => e.stopPropagation()}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" className="w-[18px] h-[18px]">
                <path
                  d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"
                  fill="currentColor"
                />
              </svg>
            </a>

            {/* LinkedIn Profile */}
            <a
              href={developer.linkedin}
              target="_blank"
              rel="noopener noreferrer"
              className="dev-card-social-link"
              aria-label={`${developer.name}'s LinkedIn Profile`}
              title="LinkedIn Profile"
              onClick={(e) => e.stopPropagation()}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" className="w-[17px] h-[17px]">
                <path
                  d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"
                  fill="currentColor"
                />
              </svg>
            </a>
          </div>

          {/* Direct Email Action Button */}
          <a
            href={`mailto:${developer.email}`}
            className="dev-card-contact-btn"
            aria-label={`Contact ${developer.name}`}
            onClick={(e) => e.stopPropagation()}
          >
            <span>Contact Me</span>
            <ArrowUpRight className="size-3" aria-hidden="true" />
          </a>
        </div>
      </div>
    </article>
  );
};
