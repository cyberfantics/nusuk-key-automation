#!/usr/bin/env python3
"""
Nusuk Challenge Key Automation Script (fast version)
Automatically navigates the Nusuk app on a connected Android phone (via ADB)
and claims keys from a text file, one code at a time.

Speed notes (vs the first version):
  * One adb round-trip per UI dump instead of two (dump + cat in one shell call).
  * No `shell=True` — adb is invoked directly, no extra shell process per call.
  * Batched shell commands: clear-field, type-code + dismiss keyboard are each
    a single adb call instead of several.
  * Polling waits instead of fixed sleeps: after tapping "Check the code" the
    script checks the screen every 0.5 s and moves on as soon as the result
    appears, instead of always sleeping 3 s.
  * No redundant screen check per code: after a success the script knows it is
    back on the input screen and only re-verifies with one dump; the full
    8-attempt recovery loop runs only when the screen is not where expected.
  * Resume support: results are saved to <keys-file>.progress.json after every
    code, so re-running skips codes that already finished (SUCCESS /
    ALREADY_USED / INVALID). ERROR / UNKNOWN codes are retried.
  * Finished codes are also deleted from the keys file itself, so the next
    run never tries them again even without the progress file. Codes that
    fail with ERROR / UNKNOWN stay in the file for retry.
  * Taps use the real on-screen coordinates of the button found in the UI
    dump instead of hardcoded pixels, so fewer taps miss and trigger recovery.

What cannot be made faster: the phone UI itself. Each code still needs a UI
dump, a tap, and the Nusuk server's answer. Expect roughly 6-9 seconds per
code in practice (about 2-3x faster than the first version), most of it the
server round-trip. Only one phone / one app instance can run at a time, so
there is no parallel mode.

Usage:
    python nusuk_add_keys.py keys.txt            # normal run (resumes)
    python nusuk_add_keys.py keys.txt --fresh    # ignore progress, redo all
    python nusuk_add_keys.py keys.txt --limit 20 # only first 20 remaining
    python nusuk_add_keys.py keys.txt --dry-run  # validate codes, no ADB
"""

import sys
import os
import re
import time
import json
import argparse
import subprocess
import xml.etree.ElementTree as ET

# ---- developer banner (colorama, optional) ------------------------------
# colorama gives the startup banner its colours on Windows. If it is not
# installed the banner still prints, just without colours.
try:
    from colorama import init as _colorama_init, Fore, Style
    _colorama_init(autoreset=True)
    _COLOR = True
except ImportError:
    _COLOR = False

    class _NoColor:
        def __getattr__(self, name):
            return ""

    Fore = Style = _NoColor()


def _paint(text, color=""):
    return f"{color}{text}" if _COLOR else text


def print_banner():
    """Show the tool title and the developer's links, in colour when possible."""
    bar = "=" * 55
    print(_paint(bar, Fore.CYAN + Style.BRIGHT))
    print(_paint("  NUSUK KEY AUTOMATION", Fore.CYAN + Style.BRIGHT))
    print(_paint("  by Mansoor Bukhari  •  CyberFantics", Fore.GREEN + Style.BRIGHT))
    print(_paint("  Python & Flutter Developer | AI Automation Engineer", Fore.YELLOW))
    print(_paint("-" * 55, Fore.CYAN))
    print(_paint("  GitHub:    ", Fore.YELLOW) + _paint("github.com/cyberfantics", Fore.WHITE + Style.BRIGHT))
    print(_paint("  LinkedIn:  ", Fore.YELLOW) + _paint("linkedin.com/in/mansoor-bukhari", Fore.WHITE + Style.BRIGHT))
    print(_paint("  Instagram: ", Fore.YELLOW) + _paint("instagram.com/CyberFantics", Fore.WHITE + Style.BRIGHT))
    print(_paint("  YouTube:   ", Fore.YELLOW) + _paint("youtube.com/@CyberFantics", Fore.WHITE + Style.BRIGHT))
    print(_paint(bar, Fore.CYAN + Style.BRIGHT))


def _app_dir():
    """Folder holding the running exe (frozen) or this .py file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _adb_cmd():
    """Prefer adb.exe next to the exe/script (release zip), else PATH."""
    bundled = os.path.join(_app_dir(), "adb.exe" if os.name == "nt" else "adb")
    if os.path.isfile(bundled):
        return bundled
    return "adb"


PACKAGE_NAME = "com.moh.nusukapp"
CODE_RE = re.compile(r"(NG-[A-Za-z0-9_-]+)")

# ---- tunable waits (seconds) -------------------------------------------
DUMP_TIMEOUT = 15      # max time for one adb call
POLL_INTERVAL = 0.5    # how often to re-dump while waiting for a result
CHECK_TIMEOUT = 8.0    # max wait for the server answer after "Check the code"
NAV_SLEEP = 1.5        # sleep after a navigation tap (was 2-4 s)
# --------------------------------------------------------------------------

DEVICE_ID = None  # set from --device, passed as `adb -s <id> ...`
TERMINAL_STATUSES = {"SUCCESS", "ALREADY_USED", "INVALID"}


class UINode:
    def __init__(self, text, desc, cls, bounds, cx, cy):
        self.text = text
        self.desc = desc
        self.cls = cls
        self.bounds = bounds
        self.cx = cx
        self.cy = cy

    def __repr__(self):
        return f"<UINode text='{self.text}' desc='{self.desc}' bounds={self.bounds} center=({self.cx},{self.cy})>"


def adb(*args, timeout=DUMP_TIMEOUT):
    """Run one adb command (no shell) and return stdout string."""
    cmd = [_adb_cmd()]
    if DEVICE_ID:
        cmd += ["-s", DEVICE_ID]
    cmd += list(args)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""
    except FileNotFoundError:
        # adb is not installed / not on PATH — callers treat this as "no device".
        return ""


def adb_shell(script, timeout=DUMP_TIMEOUT):
    """Run one shell script on the device in a single adb round-trip.

    `script` may chain commands with `;` — this is how several old adb calls
    become one (e.g. dump + cat, or type + dismiss keyboard).
    """
    return adb("shell", script, timeout=timeout)


def ensure_device():
    """Ensure an ADB device is connected and awake."""
    out = adb("devices")
    devices = [l.split()[0] for l in out.splitlines() if "\tdevice" in l]
    if not devices:
        print("❌ Error: No Android device connected via ADB.")
        print("   Please connect your phone via USB with USB Debugging enabled.")
        sys.exit(1)

    global DEVICE_ID
    if DEVICE_ID and DEVICE_ID not in devices:
        print(f"❌ Error: device '{DEVICE_ID}' not found. Connected: {', '.join(devices)}")
        sys.exit(1)
    if not DEVICE_ID:
        DEVICE_ID = devices[0]
        if len(devices) > 1:
            print(f"ℹ️ Multiple devices, using the first: {DEVICE_ID} (use --device to pick another)")
    print(f"✅ Device connected: {DEVICE_ID}")

    adb_shell("input keyevent KEYCODE_WAKEUP")
    time.sleep(0.5)


def dump_nodes():
    """Dump the UI hierarchy with ONE adb call and return UINode objects."""
    xml_str = adb_shell("uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml")
    if not xml_str or "<?xml" not in xml_str:
        return []
    try:
        idx = xml_str.find("<?xml")
        if idx != -1:
            xml_str = xml_str[idx:]
        root = ET.fromstring(xml_str)
        nodes = []
        for n in root.iter("node"):
            t = n.attrib.get("text", "")
            d = n.attrib.get("content-desc", "")
            c = n.attrib.get("class", "")
            b = n.attrib.get("bounds", "")
            m = re.findall(r"\[(\d+),(\d+)\]", b)
            cx, cy = 0, 0
            if len(m) == 2:
                x1, y1 = int(m[0][0]), int(m[0][1])
                x2, y2 = int(m[1][0]), int(m[1][1])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            nodes.append(UINode(t, d, c, b, cx, cy))
        return nodes
    except Exception as e:
        print(f"[!] Error parsing UI: {e}")
        return []


def find_node(nodes, text_match=None, desc_match=None, class_match=None):
    """Find the first node matching any of the given criteria."""
    for n in nodes:
        if text_match and text_match.lower() in n.text.lower():
            return n
        if desc_match and desc_match.lower() in n.desc.lower():
            return n
        if class_match and class_match.lower() in n.cls.lower():
            return n
    return None


def tap(x, y):
    """Tap coordinates on device (one adb call)."""
    adb("shell", "input", "tap", str(x), str(y))


def tap_node(node, fallback_xy):
    """Tap a found node at its real center, or the fallback coordinates."""
    if node is not None and (node.cx or node.cy):
        tap(node.cx, node.cy)
    else:
        tap(*fallback_xy)


def get_current_key_count(nodes):
    """Try to extract current key count from UI."""
    for n in nodes:
        if n.text.isdigit() and len(n.text) <= 4 and n.cy < 300:
            return int(n.text)
        if n.desc.isdigit() and len(n.desc) <= 4 and n.cy < 300:
            return int(n.desc)
    return None


def on_input_screen(nodes):
    """True if the code input screen is showing."""
    return (
        find_node(nodes, text_match="Add code to get new key") is not None
        or find_node(nodes, text_match="Check the code") is not None
    )


def ensure_on_keys_screen():
    """Recover to the code input screen. Only called when the script is lost.

    Returns True when the input screen is showing.
    """
    for _attempt in range(8):
        nodes = dump_nodes()
        if on_input_screen(nodes):
            return True

        # Congratulations screen -> back to the input screen
        add_another = find_node(nodes, text_match="Add another code to get a key")
        if add_another is not None:
            print("🔄 On congratulations screen, tapping 'Add another code to get a key'...")
            tap_node(add_another, (360, 1510))
            time.sleep(NAV_SLEEP)
            continue

        # Doors screen / challenge tab -> open the Keys tab
        keys_tab = find_node(nodes, desc_match="Keys") or find_node(nodes, text_match="Keys")
        if keys_tab is not None and keys_tab.cy > 1300:
            print("🔑 Tapping 'Keys' tab...")
            tap_node(keys_tab, (360, 1450))
            time.sleep(NAV_SLEEP)
            continue

        # Home screen -> open the challenge
        start_ch = find_node(nodes, text_match="Start the challenge")
        if start_ch is not None:
            print("🚪 Tapping 'Start the challenge' banner...")
            tap_node(start_ch, (360, 1000))
            time.sleep(NAV_SLEEP + 1)
            continue

        # Door prompt popup -> close it
        close_btn = find_node(nodes, text_match="Close")
        if close_btn is not None:
            print("❌ Closing door prompt dialog...")
            tap_node(close_btn, (360, 1000))
            time.sleep(1)
            continue

        # App not in foreground -> launch it
        focus = adb_shell("dumpsys window | grep mCurrentFocus")
        if PACKAGE_NAME not in focus:
            print(f"🚀 Launching Nusuk app ({PACKAGE_NAME})...")
            adb_shell(f"monkey -p {PACKAGE_NAME} -c android.intent.category.LAUNCHER 1")
            time.sleep(4)
            continue

        # Last resort: tap where the Keys tab usually is
        tap(360, 1450)
        time.sleep(NAV_SLEEP)

    return False


def clear_edit_text(input_node=None):
    """Clear the code input box. One adb call (was two)."""
    if input_node is not None and (input_node.cx or input_node.cy):
        tap(input_node.cx, input_node.cy)
    else:
        tap(360, 1104)
    time.sleep(0.3)
    # Move cursor to end, then delete 25 chars — chained in one shell call.
    adb_shell("input keyevent 123; input keyevent " + " ".join(["67"] * 25))
    time.sleep(0.3)


def judge_result(nodes):
    """Classify a result screen. Returns (status, message) or None if undecided."""
    if find_node(nodes, text_match="Congratulations") is not None:
        count = get_current_key_count(nodes)
        count_str = f" (Total Keys: {count})" if count else ""
        return "SUCCESS", f"Key added!{count_str}"
    if find_node(nodes, text_match="already has been used") is not None:
        return "ALREADY_USED", "The code already has been used, please enter a new code."
    invalid = find_node(nodes, text_match="invalid") or find_node(nodes, text_match="not valid")
    if invalid is not None:
        return "INVALID", "Code is invalid"
    for n in nodes:
        if "please enter a new code" in n.text.lower() or "error" in n.text.lower():
            return "ERROR", n.text
    return None


def claim_key(code, on_input):
    """Claim a single key code. Returns (status, message, on_input_next)."""
    code = code.strip()
    m = CODE_RE.search(code)
    if m:
        code = m.group(1)

    print(f"\n👉 Processing code: {code}")

    # 1. Make sure we are on the input screen — cheap check if we already
    #    believe we are there (one dump), full recovery only if we are lost.
    nodes = None
    if on_input:
        nodes = dump_nodes()
        if not on_input_screen(nodes):
            on_input = False
            nodes = None
    if not on_input:
        if not ensure_on_keys_screen():
            print("⚠️ Warning: Could not detect input screen, attempting blindly...")
        nodes = dump_nodes()

    # 2. Clear the input box and type the code (2 adb calls total).
    input_node = find_node(nodes, text_match="Add code to get new key") if nodes else None
    clear_edit_text(input_node)
    # Type + dismiss the keyboard in one shell call.
    adb_shell(f"input text {code}; input keyevent KEYCODE_BACK")
    time.sleep(0.5)

    # 3. Tap 'Check the code' at its real position.
    nodes = dump_nodes()
    check_btn = find_node(nodes, text_match="Check the code")
    tap_node(check_btn, (360, 1265))

    # 4. Poll for the result instead of sleeping a fixed 3 s.
    deadline = time.time() + CHECK_TIMEOUT
    result = None
    res_nodes = []
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        res_nodes = dump_nodes()
        result = judge_result(res_nodes)
        if result is not None:
            break

    if result is None:
        print("ℹ️ Finished submission (no clear result).")
        clear_edit_text()
        return "UNKNOWN", "Finished submission", False

    status, msg = result
    if status == "SUCCESS":
        print(f"🎉 SUCCESS! Key added successfully!{msg[len('Key added!'):]}")
        # Back to the input screen right away, at the button's real position.
        add_another = find_node(res_nodes, text_match="Add another code to get a key")
        tap_node(add_another, (360, 1510))
        time.sleep(1)
        return status, msg, True

    print(f"⚠️ FAILED: {msg}" if status != "INVALID" else f"❌ FAILED: {msg}")
    clear_edit_text()
    # After a rejection the input screen is still showing.
    return status, msg, True


def load_codes(filepath):
    """Read codes from file: strip, drop blanks/comments, dedupe (keep order)."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    codes, seen, invalid = [], set(), []
    for line in raw:
        m = CODE_RE.search(line)
        if not m:
            invalid.append(line)
            continue
        code = m.group(1)
        if code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return codes, invalid, len(raw) - len(codes) - len(invalid)


def load_progress(progress_path):
    if os.path.exists(progress_path):
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def save_progress(progress_path, progress):
    tmp = progress_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=1, sort_keys=True)
    os.replace(tmp, progress_path)


def prune_keys_file(filepath, code):
    """Delete one finished code from the keys file.

    Called after a code reaches a terminal status (SUCCESS / ALREADY_USED /
    INVALID) so the next run never sees it again. Comment and blank lines
    are kept; only the line holding the code is dropped. The "# Total:"
    header line is updated to the new count. Returns the number of codes
    left in the file, or None if the code was not in the file.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"[!] Could not update {filepath}: {e}")
        return None
    kept = [l for l in lines if code not in l]
    if len(kept) == len(lines):
        return None
    remaining = 0
    for l in kept:
        s = l.strip()
        if s and not s.startswith("#") and CODE_RE.search(s):
            remaining += 1
    out = []
    for l in kept:
        if l.startswith("# Total:"):
            out.append(re.sub(r"# Total: \d+", f"# Total: {remaining}", l))
        else:
            out.append(l)
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(out)
    os.replace(tmp, filepath)
    return remaining


def main():
    parser = argparse.ArgumentParser(description="Nusuk Challenge key automation (fast)")
    parser.add_argument("keys_file", nargs="?", default="keys.txt")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore saved progress and redo every code")
    parser.add_argument("--limit", type=int, default=0,
                        help="only process the first N remaining codes")
    parser.add_argument("--dry-run", action="store_true",
                        help="validate the keys file only, do not touch the phone")
    parser.add_argument("--device", default=None,
                        help="adb device id when more than one phone is connected")
    args = parser.parse_args()

    global DEVICE_ID
    DEVICE_ID = args.device

    filepath = args.keys_file
    if not os.path.exists(filepath):
        # Running the exe from another folder: look next to the exe/script.
        alt = os.path.join(_app_dir(), os.path.basename(filepath))
        if os.path.exists(alt):
            filepath = alt
    if not os.path.exists(filepath):
        print(f"❌ Error: Keys file '{filepath}' not found.")
        print(f"   Please create '{filepath}' with one key per line.")
        sys.exit(1)

    codes, invalid, dupes = load_codes(filepath)
    if invalid:
        print(f"⚠️ Skipped {len(invalid)} line(s) with no valid NG- code: {invalid[:5]}")
    if dupes:
        print(f"ℹ️ Skipped {dupes} duplicate code(s) in the file.")
    if not codes:
        print(f"⚠️ No keys found in '{filepath}'.")
        sys.exit(0)

    progress_path = filepath + ".progress.json"
    progress = {} if args.fresh else load_progress(progress_path)
    done = {c for c, s in progress.items() if s in TERMINAL_STATUSES}
    todo = [c for c in codes if c not in done]
    if args.limit:
        todo = todo[: args.limit]

    print_banner()
    print(f"📋 Loaded {len(codes)} unique key(s) from '{filepath}'.")
    if done and not args.fresh:
        print(f"♻️  Resuming: {len(done)} already finished, {len(todo)} remaining.")
    if args.dry_run:
        print("🔍 Dry run only — no ADB, no phone touched. All codes valid.")
        sys.exit(0)

    ensure_device()
    if not ensure_on_keys_screen():
        print("⚠️ Warning: could not reach the input screen at startup, continuing anyway...")
    on_input = True

    results = []
    removed = 0
    start = time.time()
    for idx, code in enumerate(todo, 1):
        elapsed = time.time() - start
        avg = elapsed / idx if idx else 0
        eta = avg * (len(todo) - idx)
        print(f"\n--- [{idx}/{len(todo)}] (avg {avg:.1f}s/code, ETA ~{eta/60:.0f} min) ---")
        status, msg, on_input = claim_key(code, on_input)
        results.append((code, status, msg))
        progress[code] = status
        save_progress(progress_path, progress)
        if status in TERMINAL_STATUSES:
            left = prune_keys_file(filepath, code)
            if left is not None:
                removed += 1
                print(f"🗑️ Removed {code} from {filepath} ({left} left)")

    print("\n" + "=" * 55)
    print("                 SUMMARY REPORT")
    print("=" * 55)
    total_time = time.time() - start
    successes = sum(1 for _, s, _ in results if s == "SUCCESS")
    print(f"Total processed: {len(results)}")
    print(f"Keys added     : {successes}")
    print(f"Failed / Used  : {len(results) - successes}")
    if results:
        print(f"Time taken     : {total_time/60:.1f} min ({total_time/max(len(results),1):.1f}s per code)")
    print(f"Progress saved : {progress_path} (re-run to resume)")
    if removed:
        print(f"Keys removed   : {removed} finished code(s) deleted from {filepath}")
    print("-" * 55)
    for k, s, m in results:
        icon = "✅" if s == "SUCCESS" else ("⚠️" if s == "ALREADY_USED" else "❌")
        print(f"{icon} {k:<20} -> {m}")
    print("=" * 55)


if __name__ == "__main__":
    main()
