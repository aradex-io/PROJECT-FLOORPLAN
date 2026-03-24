import React, { useRef, useEffect, useMemo } from "react";

interface Position {
  x: number;
  y: number;
  z: number;
}

interface Device {
  device_id: string;
  mac: string;
  position: Position;
  uncertainty_m: number;
  confidence: number;
  state: string;
  speed_mps: number;
  zones: string[];
}

interface Props {
  devices: Device[];
  selectedDevice: string | null;
  onSelectDevice: (id: string | null) => void;
}

const SCALE = 30; // pixels per meter
const ORIGIN_X = 50;
const ORIGIN_Y = 50;

function stateColor(state: string, selected: boolean): string {
  if (selected) return "#e94560";
  switch (state) {
    case "active":
      return "#4ade80";
    case "stale":
      return "#facc15";
    case "lost":
      return "#6b7280";
    default:
      return "#4ade80";
  }
}

export function FloorPlanView({ devices, selectedDevice, onSelectDevice }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Resize canvas to container
    const container = canvas.parentElement;
    if (container) {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
    }

    const w = canvas.width;
    const h = canvas.height;

    // Clear
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, w, h);

    // Draw grid
    ctx.strokeStyle = "#ffffff10";
    ctx.lineWidth = 1;
    for (let x = ORIGIN_X; x < w; x += SCALE) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = ORIGIN_Y; y < h; y += SCALE) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    // Draw scale marker
    ctx.fillStyle = "#ffffff40";
    ctx.font = "11px monospace";
    ctx.fillText("1m", ORIGIN_X + SCALE - 8, ORIGIN_Y - 8);

    // Draw devices
    for (const device of devices) {
      const px = ORIGIN_X + device.position.x * SCALE;
      const py = ORIGIN_Y + device.position.y * SCALE;
      const isSelected = device.device_id === selectedDevice;
      const color = stateColor(device.state, isSelected);

      // Uncertainty circle
      if (device.uncertainty_m > 0) {
        const radius = device.uncertainty_m * SCALE;
        ctx.beginPath();
        ctx.arc(px, py, radius, 0, Math.PI * 2);
        ctx.fillStyle = color + "15";
        ctx.fill();
        ctx.strokeStyle = color + "40";
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Device dot
      const dotSize = isSelected ? 8 : 6;
      ctx.beginPath();
      ctx.arc(px, py, dotSize, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // Label
      ctx.fillStyle = "#ffffffcc";
      ctx.font = "10px monospace";
      const label = device.mac.substring(0, 8);
      ctx.fillText(label, px + 10, py + 4);

      // Speed indicator (trail line)
      if (device.speed_mps > 0.1) {
        const vLen = Math.min(device.speed_mps * SCALE * 0.5, 40);
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px - vLen, py);
        ctx.strokeStyle = color + "60";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }

    // Origin marker
    ctx.fillStyle = "#ffffff30";
    ctx.beginPath();
    ctx.arc(ORIGIN_X, ORIGIN_Y, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText("(0,0)", ORIGIN_X + 6, ORIGIN_Y - 6);
  }, [devices, selectedDevice]);

  const handleClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    // Find clicked device
    for (const device of devices) {
      const px = ORIGIN_X + device.position.x * SCALE;
      const py = ORIGIN_Y + device.position.y * SCALE;
      const dist = Math.sqrt((clickX - px) ** 2 + (clickY - py) ** 2);
      if (dist < 15) {
        onSelectDevice(device.device_id);
        return;
      }
    }
    onSelectDevice(null);
  };

  return (
    <canvas
      ref={canvasRef}
      className="w-full h-full cursor-crosshair"
      onClick={handleClick}
    />
  );
}
