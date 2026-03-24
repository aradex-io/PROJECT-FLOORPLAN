import React from "react";

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

interface Props {
  devices: Device[];
  selectedDevice: string | null;
  onSelectDevice: (id: string | null) => void;
}

function stateLabel(state: string): { text: string; className: string } {
  switch (state) {
    case "active":
      return { text: "Active", className: "text-green-400" };
    case "stale":
      return { text: "Stale", className: "text-yellow-400" };
    case "lost":
      return { text: "Lost", className: "text-gray-500" };
    default:
      return { text: state, className: "text-gray-400" };
  }
}

export function DevicePanel({ devices, selectedDevice, onSelectDevice }: Props) {
  const selected = devices.find((d) => d.device_id === selectedDevice);

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold mb-4 text-gray-200">Tracked Devices</h2>

      {/* Device list */}
      <div className="space-y-2 mb-6">
        {devices.length === 0 && (
          <p className="text-gray-500 text-sm">No devices detected</p>
        )}
        {devices.map((device) => {
          const sl = stateLabel(device.state);
          const isSelected = device.device_id === selectedDevice;

          return (
            <button
              key={device.device_id}
              onClick={() =>
                onSelectDevice(isSelected ? null : device.device_id)
              }
              className={`w-full text-left p-3 rounded-lg transition-colors ${
                isSelected
                  ? "bg-floor-highlight/20 border border-floor-highlight/50"
                  : "bg-floor-accent/30 hover:bg-floor-accent/50 border border-transparent"
              }`}
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-sm">{device.mac}</span>
                <span className={`text-xs ${sl.className}`}>{sl.text}</span>
              </div>
              <div className="text-xs text-gray-500 mt-1">
                ({device.position.x.toFixed(1)}, {device.position.y.toFixed(1)})
                {device.uncertainty_m > 0 &&
                  ` ±${device.uncertainty_m.toFixed(1)}m`}
              </div>
            </button>
          );
        })}
      </div>

      {/* Selected device detail */}
      {selected && (
        <div className="border-t border-floor-accent pt-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Device Detail
          </h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-gray-500">MAC</dt>
              <dd className="font-mono">{selected.mac}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Position</dt>
              <dd>
                ({selected.position.x.toFixed(2)},{" "}
                {selected.position.y.toFixed(2)})
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Uncertainty</dt>
              <dd>{selected.uncertainty_m.toFixed(2)}m</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Confidence</dt>
              <dd>{(selected.confidence * 100).toFixed(0)}%</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">Speed</dt>
              <dd>{selected.speed_mps.toFixed(2)} m/s</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-gray-500">State</dt>
              <dd className={stateLabel(selected.state).className}>
                {stateLabel(selected.state).text}
              </dd>
            </div>
            {selected.zones.length > 0 && (
              <div className="flex justify-between">
                <dt className="text-gray-500">Zones</dt>
                <dd>{selected.zones.join(", ")}</dd>
              </div>
            )}
          </dl>
        </div>
      )}
    </div>
  );
}
