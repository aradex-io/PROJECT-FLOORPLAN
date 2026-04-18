"""FLOORPLAN CLI — operational interface for Wi-Fi FTM positioning."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console()


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging.")
@click.option("-i", "--interface", default="wlan0", help="Wi-Fi interface to use.")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, interface: str) -> None:
    """FLOORPLAN — Wi-Fi FTM/RTT Indoor Positioning System."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["interface"] = interface
    setup_logging(verbose)


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Check hardware FTM capabilities."""
    from floorplan.ranging import RangingEngine

    interface = ctx.obj["interface"]
    console.print(f"[bold]Checking FTM support on {interface}...[/bold]")

    engine = RangingEngine(interface=interface)
    caps = engine.check_hardware()

    table = Table(title="FTM Capabilities")
    table.add_column("Feature", style="cyan")
    table.add_column("Supported", style="green")

    for feature, supported in caps.items():
        status = "[green]✓ Yes[/green]" if supported else "[red]✗ No[/red]"
        table.add_row(feature.replace("_", " ").title(), status)

    console.print(table)

    if not any(caps.values()):
        console.print(
            "\n[yellow]No FTM support detected. You may need:[/yellow]\n"
            "  • Intel AX200/AX210 Wi-Fi adapter\n"
            "  • Linux kernel ≥ 5.10 with iwlwifi\n"
            "  • Firmware: iwlwifi-cc-a0-72.ucode or newer"
        )


@cli.command()
@click.option(
    "-c", "--config", "config_path", type=click.Path(exists=True), help="Site config YAML."
)
@click.pass_context
def scan(ctx: click.Context, config_path: str | None) -> None:
    """Discover FTM-capable devices in range."""
    interface = ctx.obj["interface"]
    console.print(f"[bold]Scanning for FTM-capable devices on {interface}...[/bold]")

    # Use iw scan to find APs with FTM support
    import subprocess

    try:
        result = subprocess.run(
            ["iw", "dev", interface, "scan"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout

        devices: list[dict[str, object]] = []
        current: dict[str, object] = {}

        for line in output.split("\n"):
            line = line.strip()
            if line.startswith("BSS "):
                if current:
                    devices.append(current)
                mac = line.split()[1].rstrip("(")
                current = {"mac": mac, "ftm": False}
            elif "SSID:" in line:
                current["ssid"] = line.split("SSID:", 1)[1].strip()
            elif "signal:" in line:
                current["rssi"] = line.split("signal:", 1)[1].strip()
            elif "freq:" in line:
                current["freq"] = line.split("freq:", 1)[1].strip()
            elif "FTM" in line.upper() or "fine timing" in line.lower():
                current["ftm"] = True

        if current:
            devices.append(current)

        table = Table(title="Discovered Devices")
        table.add_column("MAC", style="cyan")
        table.add_column("SSID")
        table.add_column("Signal")
        table.add_column("Freq")
        table.add_column("FTM", style="green")

        for dev in devices:
            ftm_str = "[green]✓[/green]" if dev.get("ftm") else "[dim]-[/dim]"
            table.add_row(
                dev.get("mac", ""),
                dev.get("ssid", ""),
                dev.get("rssi", ""),
                dev.get("freq", ""),
                ftm_str,
            )

        console.print(table)
        console.print(
            f"\n[bold]{len(devices)}[/bold] devices found, "
            f"[bold]{sum(1 for d in devices if d.get('ftm'))}[/bold] FTM-capable"
        )

    except FileNotFoundError:
        console.print("[red]Error: 'iw' command not found. Install iw package.[/red]")
    except subprocess.TimeoutExpired:
        console.print("[red]Scan timed out.[/red]")
    except Exception as e:
        console.print(f"[red]Scan failed: {e}[/red]")


@cli.command()
@click.argument("mac")
@click.option("-c", "--channel", type=int, default=0, help="Channel frequency (MHz).")
@click.option("-n", "--count", type=int, default=1, help="Number of measurements.")
@click.pass_context
def range(ctx: click.Context, mac: str, channel: int, count: int) -> None:
    """Perform FTM ranging to a target device."""
    from floorplan.models import BurstConfig
    from floorplan.ranging import RangingEngine

    interface = ctx.obj["interface"]
    console.print(f"[bold]Ranging to {mac} on {interface}...[/bold]")

    engine = RangingEngine(interface=interface, burst_config=BurstConfig.accurate())

    results = []
    with engine:
        for i in range(count):
            result = engine.range_once(mac, channel)
            if result:
                results.append(result)
                console.print(
                    f"  [{i + 1}/{count}] Distance: [bold]{result.distance_m:.2f}m[/bold] "
                    f"(±{result.std_dev_m:.2f}m) "
                    f"RSSI: {result.rssi_dbm}dBm "
                    f"NLOS: {'[yellow]Yes[/yellow]' if result.is_nlos else 'No'}"
                )
            else:
                console.print(f"  [{i + 1}/{count}] [red]No response[/red]")

    if results:
        avg_dist = sum(r.distance_m for r in results) / len(results)
        console.print(
            f"\n[bold]Average: {avg_dist:.2f}m[/bold] "
            f"({len(results)}/{count} successful measurements)"
        )


@cli.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True),
    help="Site configuration YAML file.",
)
@click.option(
    "--filter",
    "filter_type",
    type=click.Choice(["kalman", "particle"]),
    default="kalman",
    help="Tracking filter type.",
)
@click.option("--record/--no-record", default=False, help="Record session to database.")
@click.option("--db", "db_path", default="floorplan.db", help="Database path for recording.")
@click.pass_context
def track(
    ctx: click.Context,
    config_path: str,
    filter_type: str,
    record: bool,
    db_path: str,
) -> None:
    """Start continuous multi-target tracking."""
    from floorplan.config import load_config
    from floorplan.models import BurstConfig
    from floorplan.position import PositionEngine
    from floorplan.ranging import RangingEngine
    from floorplan.tracking import TrackManager

    config = load_config(config_path)
    console.print(f"[bold]Starting tracking: {config.name}[/bold]")
    console.print(f"  Reference points: {len(config.reference_points)}")
    console.print(f"  Zones: {len(config.zones)}")
    console.print(f"  Filter: {filter_type}")

    # Initialize components
    ranging = RangingEngine(
        interface=config.interface,
        burst_config=BurstConfig.fast()
        if config.burst_config == "fast"
        else BurstConfig.accurate(),
    )
    _position = PositionEngine(
        reference_points=config.reference_points,
        filter_type=filter_type,
    )
    tracker = TrackManager(zones=config.zones)

    # Set up database recording
    store = None
    if record:
        from floorplan.db import SessionStore

        store = SessionStore(db_path)
        store.connect()
        session_id = store.start_session(config.name)
        console.print(f"  Recording to session {session_id}")

    # Add reference points as ranging targets
    for rp in config.reference_points:
        ranging.add_target(rp.mac, rp.channel)

    # Zone event handler
    def on_zone_event(event: Any) -> None:
        console.print(
            f"  [yellow]ZONE {event.event_type.upper()}[/yellow]: "
            f"{event.device_id} → {event.zone_name}"
        )
        if store:
            store.record_zone_event(
                event.device_id,
                event.zone_name,
                event.event_type,
                event.position,
                event.dwell_time_s,
                event.timestamp,
            )

    tracker.on_zone_event(on_zone_event)

    console.print("\n[bold green]Tracking active. Press Ctrl+C to stop.[/bold green]\n")

    try:
        ranging.start_continuous(interval_s=config.scan_interval_s)

        while True:
            devices = tracker.get_active_devices()
            tracker.cleanup_stale()

            table = Table(title="Active Devices", show_lines=False)
            table.add_column("Device")
            table.add_column("Position")
            table.add_column("Confidence")
            table.add_column("Zones")

            for dev in devices:
                pos = dev.position
                table.add_row(
                    dev.device_id[:17],
                    f"({pos.x:.1f}, {pos.y:.1f}) ±{pos.uncertainty_m:.1f}m",
                    f"{dev.confidence:.0%}",
                    ", ".join(dev.current_zones) or "-",
                )

            console.clear()
            console.print(table)
            time.sleep(1.0)

    except KeyboardInterrupt:
        console.print("\n[bold]Stopping...[/bold]")
    finally:
        ranging.stop_continuous()
        if store:
            store.end_session()
            store.close()


@cli.command()
@click.option("--passive", is_flag=True, help="Passive-only mode (no transmissions).")
@click.option("--channel", type=int, default=0, help="Channel to monitor.")
@click.pass_context
def monitor(ctx: click.Context, passive: bool, channel: int) -> None:
    """Monitor FTM exchanges and probe requests (passive surveillance)."""
    from floorplan.passive import FTMCapture, MonitorMode, ProbeTracker

    interface = ctx.obj["interface"]
    console.print(f"[bold]Starting {'passive ' if passive else ''}monitor on {interface}[/bold]")

    if passive:
        console.print("[dim]Passive mode: zero RF footprint[/dim]")

    mon = MonitorMode(interface)
    try:
        status = mon.enable(channel=channel)
        console.print(f"  Monitor interface: {status.monitor_interface}")

        ftm_cap = FTMCapture(interface=status.monitor_interface)
        probe_trk = ProbeTracker(interface=status.monitor_interface)

        def on_exchange(exc: Any) -> None:
            console.print(
                f"  [cyan]FTM[/cyan] {exc.initiator_mac} → {exc.responder_mac} "
                f"(ch {exc.channel}, burst #{exc.burst_count})"
            )

        def on_probe(sighting: Any) -> None:
            randomized = " [yellow]R[/yellow]" if sighting.is_randomized_mac else ""
            console.print(
                f"  [dim]PROBE[/dim] {sighting.mac}{randomized} "
                f"SSID={sighting.ssid or '(broadcast)'} "
                f"RSSI={sighting.rssi_dbm}dBm"
            )

        ftm_cap.on_exchange(on_exchange)
        probe_trk.on_probe(on_probe)

        ftm_cap.start()
        probe_trk.start()

        console.print("\n[bold green]Monitoring active. Press Ctrl+C to stop.[/bold green]\n")

        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        console.print("\n[bold]Stopping...[/bold]")
    except Exception as e:
        console.print(f"[red]Monitor error: {e}[/red]")
    finally:
        mon.disable()


@cli.command()
@click.argument("session_db", type=click.Path(exists=True))
@click.option("--speed", type=float, default=1.0, help="Playback speed multiplier.")
@click.option("--session-id", type=int, default=None, help="Session ID to replay.")
def replay(session_db: str, speed: float, session_id: int | None) -> None:
    """Replay a recorded session."""
    from floorplan.db import SessionStore

    store = SessionStore(session_db)
    store.connect()

    sessions = store.list_sessions()
    if not sessions:
        console.print("[red]No sessions found in database.[/red]")
        store.close()
        return

    if session_id is None:
        session_id = sessions[0]["id"]

    stats = store.get_session_stats(session_id)
    console.print(f"[bold]Replaying session {session_id}[/bold]")
    console.print(f"  Duration: {stats['duration_s']:.0f}s")
    console.print(f"  Devices: {stats['unique_devices']}")
    console.print(f"  Position records: {stats['position_records']}")
    console.print(f"  Playback speed: {speed}x")

    records = store.get_position_track(session_id)
    if not records:
        console.print("[yellow]No position data to replay.[/yellow]")
        store.close()
        return

    console.print(f"\n[green]Playing {len(records)} records...[/green]\n")

    last_ts = records[0]["timestamp"]
    try:
        for rec in records:
            dt = (rec["timestamp"] - last_ts) / speed
            if dt > 0:
                time.sleep(min(dt, 1.0))
            last_ts = rec["timestamp"]

            console.print(
                f"  {rec['device_id'][:17]} → "
                f"({rec['x']:.1f}, {rec['y']:.1f}) "
                f"±{rec['uncertainty_m']:.1f}m"
            )
    except KeyboardInterrupt:
        console.print("\n[bold]Playback stopped.[/bold]")
    finally:
        store.close()


@cli.command()
@click.option("--host", default="0.0.0.0", help="Dashboard host.")
@click.option("--port", type=int, default=8080, help="Dashboard port.")
@click.option("--static", "static_dir", default=None, help="Frontend static files directory.")
def dashboard(host: str, port: int, static_dir: str | None) -> None:
    """Start the web dashboard."""
    import uvicorn

    from floorplan.web.app import create_app

    console.print(f"[bold]Starting FLOORPLAN dashboard on {host}:{port}[/bold]")
    app = create_app(static_dir=static_dir)
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.argument("session_db", type=click.Path(exists=True))
@click.option("--session-id", type=int, default=None)
@click.option("--output", "-o", default="report.md", help="Output file path.")
@click.option("--format", "fmt", type=click.Choice(["markdown", "json"]), default="markdown")
def export(session_db: str, session_id: int | None, output: str, fmt: str) -> None:
    """Export session data for reporting."""
    from floorplan.db import SessionStore

    store = SessionStore(session_db)
    store.connect()

    sessions = store.list_sessions()
    if not sessions:
        console.print("[red]No sessions found.[/red]")
        store.close()
        return

    if session_id is None:
        session_id = sessions[0]["id"]

    stats = store.get_session_stats(session_id)
    devices = store.get_session_devices(session_id)
    zone_events = store.get_zone_events(session_id)

    if fmt == "json":
        data = {
            "session": stats,
            "devices": devices,
            "zone_events": zone_events,
        }
        with open(output, "w") as f:
            json.dump(data, f, indent=2, default=str)
    else:
        with open(output, "w") as f:
            f.write("# FLOORPLAN Session Report\n\n")
            f.write(f"## Session {session_id}\n\n")
            f.write(f"- Duration: {stats['duration_s']:.0f}s\n")
            f.write(f"- Devices tracked: {stats['unique_devices']}\n")
            f.write(f"- Position records: {stats['position_records']}\n")
            f.write(f"- Zone events: {stats['zone_events']}\n\n")

            if devices:
                f.write("## Devices\n\n")
                f.write("| Device ID | MAC | First Seen | Last Seen |\n")
                f.write("|-----------|-----|------------|----------|\n")
                for dev in devices:
                    f.write(
                        f"| {dev['device_id'][:17]} | {dev['mac']} | "
                        f"{dev.get('first_seen', '')} | {dev.get('last_seen', '')} |\n"
                    )
                f.write("\n")

            if zone_events:
                f.write("## Zone Events\n\n")
                f.write("| Time | Device | Zone | Event | Dwell |\n")
                f.write("|------|--------|------|-------|-------|\n")
                for evt in zone_events:
                    dwell = f"{evt.get('dwell_time_s', 0):.0f}s" if evt.get("dwell_time_s") else "-"
                    f.write(
                        f"| {evt['timestamp']} | {evt['device_id'][:17]} | "
                        f"{evt['zone_name']} | {evt['event_type']} | {dwell} |\n"
                    )

    console.print(f"[green]Report exported to {output}[/green]")
    store.close()


def main() -> None:
    """Entry point."""
    cli()


if __name__ == "__main__":
    main()
