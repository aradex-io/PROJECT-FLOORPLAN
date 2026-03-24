import React, { useState, useEffect, useCallback } from "react";
import { FloorPlanView } from "./components/FloorPlanView";
import { DevicePanel } from "./components/DevicePanel";
import { useWebSocket } from "./hooks/useWebSocket";

interface Device {
  device_id: string;
  mac: string;
  position: { x: number; y: number; z: number };
  uncertainty_m: number;
  confidence: number;
  state: string;
  speed_mps: number;
  zones: string[];
}

function App() {
  const [devices, setDevices] = useState<Map<string, Device>>(new Map());
  const [selectedDevice, setSelectedDevice] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<string>("disconnected");

  const handleMessage = useCallback((data: Record<string, unknown>) => {
    const type = data.type as string;
    if (type === "position_update") {
      const device = data as unknown as Device;
      setDevices((prev) => {
        const next = new Map(prev);
        next.set(device.device_id, device);
        return next;
      });
    } else if (type === "device_list") {
      const list = (data as { devices: Device[] }).devices;
      const next = new Map<string, Device>();
      list.forEach((d) => next.set(d.device_id, d));
      setDevices(next);
    } else if (type === "zone_event") {
      console.log("Zone event:", data);
    }
  }, []);

  const { status } = useWebSocket("/api/ws", handleMessage);

  useEffect(() => {
    setConnectionStatus(status);
  }, [status]);

  const deviceList = Array.from(devices.values());

  return (
    <div className="flex h-screen bg-floor-bg">
      {/* Main floor plan area */}
      <div className="flex-1 relative">
        <header className="absolute top-0 left-0 right-0 z-10 bg-floor-panel/80 backdrop-blur p-4 flex items-center justify-between">
          <h1 className="text-xl font-bold tracking-wider">FLOORPLAN</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-400">
              {deviceList.length} device{deviceList.length !== 1 ? "s" : ""}
            </span>
            <span
              className={`text-sm px-2 py-1 rounded ${
                connectionStatus === "connected"
                  ? "bg-green-900/50 text-green-400"
                  : "bg-red-900/50 text-red-400"
              }`}
            >
              {connectionStatus}
            </span>
          </div>
        </header>

        <FloorPlanView
          devices={deviceList}
          selectedDevice={selectedDevice}
          onSelectDevice={setSelectedDevice}
        />
      </div>

      {/* Side panel */}
      <div className="w-80 bg-floor-panel border-l border-floor-accent overflow-y-auto">
        <DevicePanel
          devices={deviceList}
          selectedDevice={selectedDevice}
          onSelectDevice={setSelectedDevice}
        />
      </div>
    </div>
  );
}

export default App;
