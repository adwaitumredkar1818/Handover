"use client";

import React, { useEffect, useState, useRef } from "react";
import { usePathname, useSearchParams } from "next/navigation";

export interface PageLoadingBarProps {
  isNavigating?: boolean;
}

export function PageLoadingBar({ isNavigating = false }: PageLoadingBarProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Trigger loading animation on path or search param changes
  useEffect(() => {
    setVisible(true);
    setProgress(25);

    if (timerRef.current) clearInterval(timerRef.current);

    timerRef.current = setInterval(() => {
      setProgress((prev) => {
        if (prev < 80) return prev + Math.floor(Math.random() * 12) + 5;
        if (prev < 92) return prev + 2;
        return prev;
      });
    }, 120);

    const finishTimeout = setTimeout(() => {
      if (timerRef.current) clearInterval(timerRef.current);
      setProgress(100);
      const hideTimeout = setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, 350);
      return () => clearTimeout(hideTimeout);
    }, 400);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      clearTimeout(finishTimeout);
    };
  }, [pathname, searchParams]);

  // Handle explicit isNavigating prop
  useEffect(() => {
    if (isNavigating) {
      setVisible(true);
      setProgress(30);
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setProgress((prev) => (prev < 85 ? prev + 8 : prev));
      }, 150);
    } else if (visible && progress > 0) {
      if (timerRef.current) clearInterval(timerRef.current);
      setProgress(100);
      const timeout = setTimeout(() => {
        setVisible(false);
        setProgress(0);
      }, 300);
      return () => clearTimeout(timeout);
    }
  }, [isNavigating]);

  if (!visible && progress === 0) return null;

  return (
    <div
      className="fixed top-0 left-0 right-0 z-[9999] h-[2.5px] pointer-events-none overflow-hidden"
      aria-hidden="true"
    >
      <div
        className="h-full bg-gradient-to-r from-[#315FBA] via-[#299B80] to-[#8B78C9] transition-all duration-300 ease-out shadow-[0_1px_6px_rgba(49,95,186,0.4)]"
        style={{
          width: `${progress}%`,
          opacity: visible ? 1 : 0,
        }}
      />
    </div>
  );
}

export default PageLoadingBar;
