"use client";

import React, { useEffect, useRef } from "react";

interface GridCell {
  x: number;
  y: number;
  alpha: number;
  fading: boolean;
  lastTouched: number;
}

/**
 * DevelopersGridCanvas
 *
 * Interactive mouse-tracing grid effect for the Developers page background.
 * Implements the user's HTML5 Canvas radial-gradient square cell algorithm,
 * adapted to Handover's brand cyan/sapphire palette.
 */
export const DevelopersGridCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const squareSize = 80;
    const grid: GridCell[] = [];

    const initGrid = () => {
      grid.length = 0;
      for (let x = 0; x < width; x += squareSize) {
        for (let y = 0; y < height; y += squareSize) {
          grid.push({
            x,
            y,
            alpha: 0,
            fading: false,
            lastTouched: 0,
          });
        }
      }
    };

    const getCellAt = (x: number, y: number): GridCell | undefined => {
      return grid.find(
        (cell) =>
          x >= cell.x &&
          x < cell.x + squareSize &&
          y >= cell.y &&
          y < cell.y + squareSize
      );
    };

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      initGrid();
    };

    const handleMouseMove = (e: MouseEvent) => {
      const mouseX = e.clientX;
      const mouseY = e.clientY;

      const cell = getCellAt(mouseX, mouseY);
      if (cell && cell.alpha === 0) {
        cell.alpha = 1;
        cell.lastTouched = Date.now();
        cell.fading = false;
      }
    };

    const drawGrid = () => {
      ctx.clearRect(0, 0, width, height);
      const now = Date.now();

      for (let i = 0; i < grid.length; i++) {
        const cell = grid[i];
        if (!cell) continue;

        // Start fading after 500ms
        if (cell.alpha > 0 && !cell.fading && now - cell.lastTouched > 500) {
          cell.fading = true;
        }

        if (cell.fading) {
          cell.alpha -= 0.02;
          if (cell.alpha <= 0) {
            cell.alpha = 0;
            cell.fading = false;
          }
        }

        if (cell.alpha > 0) {
          const centerX = cell.x + squareSize / 2;
          const centerY = cell.y + squareSize / 2;

          // Radial gradient from cell center outward using Handover's cyan & brand blue
          const gradient = ctx.createRadialGradient(
            centerX,
            centerY,
            5,
            centerX,
            centerY,
            squareSize
          );
          // High-tech electric cyan fading outward
          gradient.addColorStop(0, `rgba(0, 195, 230, ${cell.alpha * 0.85})`);
          gradient.addColorStop(0.5, `rgba(49, 95, 186, ${cell.alpha * 0.5})`);
          gradient.addColorStop(1, `rgba(49, 95, 186, 0)`);

          ctx.strokeStyle = gradient;
          ctx.lineWidth = 1.4;
          ctx.strokeRect(
            cell.x + 0.5,
            cell.y + 0.5,
            squareSize - 1,
            squareSize - 1
          );

          // Subtle inner glow fill for the active cell
          ctx.fillStyle = `rgba(0, 242, 254, ${cell.alpha * 0.04})`;
          ctx.fillRect(
            cell.x + 1,
            cell.y + 1,
            squareSize - 2,
            squareSize - 2
          );
        }
      }

      animationFrameId = requestAnimationFrame(drawGrid);
    };

    window.addEventListener("resize", handleResize);
    window.addEventListener("mousemove", handleMouseMove);

    initGrid();
    drawGrid();

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full pointer-events-none z-0"
      aria-hidden="true"
    />
  );
};
