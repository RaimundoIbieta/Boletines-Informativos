from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

from boletin.config import ROOT, WEEKDAY_NAMES, get_runtime

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
LABEL = "cl.boletin.pae.semanal"
PLIST_PATH = LAUNCH_AGENTS / f"{LABEL}.plist"
SCRIPT = ROOT / "scripts" / "run_boletin.sh"


def sync_launch_agent() -> Path:
    """Regenera el LaunchAgent según config.yaml (día/hora)."""
    ctx = get_runtime()
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)

    # launchd: 0 y 7 = domingo, 1 = lunes … 6 = sábado
    # Nuestro weekday_index: 0 = lunes … 6 = domingo
    launchd_weekday = (ctx.schedule_weekday + 1) % 7

    plist = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", str(SCRIPT)],
        "WorkingDirectory": str(ROOT),
        "StartCalendarInterval": {
            "Weekday": launchd_weekday,
            "Hour": ctx.schedule_hour,
            "Minute": ctx.schedule_minute,
        },
        "RunAtLoad": False,
        "StandardOutPath": str(ROOT / "output" / "launchd.out.log"),
        "StandardErrorPath": str(ROOT / "output" / "launchd.err.log"),
    }

    with PLIST_PATH.open("wb") as fh:
        plistlib.dump(plist, fh)

    uid = subprocess.check_output(["id", "-u"], text=True).strip()
    domain = f"gui/{uid}"
    target = f"{domain}/{LABEL}"
    subprocess.run(["launchctl", "bootout", target], check=False, capture_output=True)
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(PLIST_PATH)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["launchctl", "enable", target], check=False, capture_output=True)

    day = WEEKDAY_NAMES.get(ctx.schedule_weekday, str(ctx.schedule_weekday))
    print(
        f"Programado: {day} {ctx.schedule_hour:02d}:{ctx.schedule_minute:02d} "
        f"({ctx.app.schedule.timezone})"
    )
    return PLIST_PATH
