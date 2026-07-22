from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

from boletin.config import ROOT, get_runtime
from boletin.supabase_store import supabase_configured

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
LABEL = "cl.boletin.pae.semanal"
PLIST_PATH = LAUNCH_AGENTS / f"{LABEL}.plist"
SCRIPT = ROOT / "scripts" / "run_boletin.sh"


def sync_launch_agent() -> Path:
    """Regenera el LaunchAgent.

    Con Supabase: cada 30 min ejecuta `run --scheduled` y solo envía los
    boletines cuya frecuencia (día/hora) cae en la ventana.
    Sin Supabase: un disparo semanal según config.yaml.
    """
    ctx = get_runtime()
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)

    plist: dict = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/zsh", str(SCRIPT)],
        "WorkingDirectory": str(ROOT),
        "RunAtLoad": False,
        "StandardOutPath": str(ROOT / "output" / "launchd.out.log"),
        "StandardErrorPath": str(ROOT / "output" / "launchd.err.log"),
    }

    if supabase_configured(ctx.secrets):
        # Cada 30 minutos; el CLI decide qué boletines envía
        plist["StartInterval"] = 30 * 60
        mode = "cada 30 min (boletines web / frecuencia por boletín)"
    else:
        launchd_weekday = (ctx.schedule_weekday + 1) % 7
        plist["StartCalendarInterval"] = {
            "Weekday": launchd_weekday,
            "Hour": ctx.schedule_hour,
            "Minute": ctx.schedule_minute,
        }
        mode = (
            f"semanal config.yaml → weekday={ctx.schedule_weekday} "
            f"{ctx.schedule_hour:02d}:{ctx.schedule_minute:02d}"
        )

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

    print(f"LaunchAgent actualizado: {mode}")
    return PLIST_PATH
