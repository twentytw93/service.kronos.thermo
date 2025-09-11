#twentytw93-KronosTeam
import xbmc
import xbmcgui
import subprocess
import time
import os
import xbmcaddon

BOOT_DELAY_SECONDS = 33          # exact as requested, abort-safe
WARNING_TEMP = 85                # °C: single warning (debounced)
SHUTDOWN_TEMP = 95               # °C: enforce stop + notify on real stop
COOL_HYSTERESIS = 3              # °C: reset flags after cooling below threshold hysteresis
CHECK_INTERVAL = 5               # seconds
NOTIFY_COOLDOWN_SEC = 11         # min seconds between repeated ≥95°C stop notifications

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = ADDON.getAddonInfo('path')

def _log(msg):
    xbmc.log(f"[Kronos Thermo] {msg}", xbmc.LOGINFO)

def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            milli = f.read().strip()
        if milli.isdigit():
            return int(milli) / 1000.0
    except Exception:
        pass
    try:
        out = subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8", "ignore")
        out = out.strip().replace("temp=", "").replace("'C", "")
        return float(out)
    except Exception:
        return None

def show_notification(message, icon_file="warn.png"):
    icon_path = os.path.join(ADDON_PATH, "resources", "media", icon_file)
    xbmcgui.Dialog().notification(
        "[B]" + ADDON_NAME + "[/B]",
        message,
        icon_path,
        5000
    )

def stop_playback():
    player = xbmc.Player()
    if player.isPlaying():
        try:
            player.stop()
            _log("Playback stopped due to overheat condition.")
            return True
        except Exception as e:
            _log(f"Failed to stop playback: {e}")
    return False

class ThermoService(xbmc.Monitor):
    def __init__(self):
        super().__init__()
        self.warned_85 = False           # debounce for 85 °C notify
        self.latched_95 = False          # latch for ≥95 °C "episode" (logic reset on cooling)
        self._last_crit_notify_ts = 0.0  # cooldown timer for ≥95 °C notifications

    def boot_wait(self):
        _log("Boot detected. Waiting for Home window...")
        while not xbmc.getCondVisibility("Window.IsVisible(home)"):
            if self.waitForAbort(0.1):  # 100 ms steps
                raise SystemExit

        _log(f"Stabilizing for {BOOT_DELAY_SECONDS}s (abort-safe).")
        if self.waitForAbort(BOOT_DELAY_SECONDS):
            raise SystemExit

    def handle_temp(self, temp):
        if temp is None or temp <= 0.0 or temp > 150.0:
            return

        if temp >= SHUTDOWN_TEMP:
            did_stop = stop_playback()

            now = time.time()
            if did_stop and (now - self._last_crit_notify_ts) >= NOTIFY_COOLDOWN_SEC:
                show_notification(f"CPU Temp {int(temp)}°C — Critical Overheat", "stop.png")
                self._last_crit_notify_ts = now

            self.latched_95 = True
            return 

        # ≥85 °C branch
        if temp >= WARNING_TEMP:
            if not self.warned_85:
                show_notification(f"CPU Temp {int(temp)}°C — System is Overheating", "warn.png")
                self.warned_85 = True
            return

        # Cooling resets (hysteresis)
        if self.warned_85 and temp < (WARNING_TEMP - COOL_HYSTERESIS):
            self.warned_85 = False
        if self.latched_95 and temp < (SHUTDOWN_TEMP - COOL_HYSTERESIS):
            self.latched_95 = False
            self._last_crit_notify_ts = 0.0

    def run(self):
        self.boot_wait()
        _log("Thermal monitor started.")
        while not self.abortRequested():
            temp = get_cpu_temp()
            self.handle_temp(temp)
            if self.waitForAbort(CHECK_INTERVAL):
                break
        _log("Service abort requested. Exiting cleanly.")

if __name__ == "__main__":
    ThermoService().run()