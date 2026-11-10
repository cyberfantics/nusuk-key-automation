#!/usr/bin/env python3
"""
Nusuk Challenge Key Automation Script
Automatically navigates Nusuk app and claims keys from a text file.
"""

import sys
import os
import re
import time
import subprocess
import xml.etree.ElementTree as ET

PACKAGE_NAME = "com.moh.nusukapp"

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

def run_adb(cmd, timeout=15):
    """Run an adb command and return stdout string."""
    full_cmd = f"adb {cmd}"
    try:
        res = subprocess.run(full_cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return res.stdout.strip()
    except subprocess.TimeoutExpired:
        return ""

def ensure_device():
    """Ensure an ADB device is connected and awake."""
    out = run_adb("devices")
    devices = [l.split()[0] for l in out.splitlines() if "\tdevice" in l]
    if not devices:
        print("❌ Error: No Android device connected via ADB.")
        print("   Please connect your phone via USB with USB Debugging enabled.")
        sys.exit(1)
    
    device_id = devices[0]
    print(f"✅ Device connected: {device_id}")

    # Wake up screen if locked/sleeping
    run_adb("shell input keyevent KEYCODE_WAKEUP")
    time.sleep(0.5)
    return device_id

def dump_nodes():
    """Dump UI hierarchy and return list of UINode objects."""
    run_adb("shell uiautomator dump /sdcard/ui.xml")
    xml_str = run_adb("shell cat /sdcard/ui.xml")
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
            m = re.findall(r'\[(\d+),(\d+)\]', b)
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
    """Find the first matching UINode."""
    for n in nodes:
        if text_match and text_match.lower() in n.text.lower():
            return n
        if desc_match and desc_match.lower() in n.desc.lower():
            return n
        if class_match and class_match.lower() in n.cls.lower():
            return n
    return None

def tap(x, y):
    """Tap coordinates on device."""
    run_adb(f"shell input tap {x} {y}")

def get_current_key_count(nodes):
    """Try to extract current key count from UI."""
    for n in nodes:
        if n.text.isdigit() and len(n.text) <= 4 and n.cy < 300:
            return int(n.text)
        if n.desc.isdigit() and len(n.desc) <= 4 and n.cy < 300:
            return int(n.desc)
    return None

def ensure_on_keys_screen():
    """Ensure the screen is ready with the 'Add code to get new key' input field."""
    for attempt in range(8):
        nodes = dump_nodes()
        
        # Check if already on the input screen
        has_input = find_node(nodes, text_match="Add code to get new key")
        has_check = find_node(nodes, text_match="Check the code")
        if has_input or has_check:
            return True

        # If on Congratulations screen -> click 'Add another code to get a key'
        add_another = find_node(nodes, text_match="Add another code to get a key")
        if add_another is not None:
            print("🔄 On congratulations screen, tapping 'Add another code to get a key'...")
            tap(360, 1510)
            time.sleep(2)
            continue

        # If on doors screen or any challenge tab -> click 'Keys' tab
        keys_tab = find_node(nodes, desc_match="Keys")
        if keys_tab is None:
            keys_tab = find_node(nodes, text_match="Keys")
        if keys_tab is not None and keys_tab.cy > 1300:
            print("🔑 Tapping 'Keys' tab...")
            tap(keys_tab.cx, keys_tab.cy)
            time.sleep(2)
            continue

        # If on Home screen -> click 'Start the challenge'
        start_ch = find_node(nodes, text_match="Start the challenge")
        if start_ch is not None:
            print("🚪 Tapping 'Start the challenge' banner...")
            tap(start_ch.cx, start_ch.cy)
            time.sleep(3)
            continue

        # If on door prompt popup -> Close it
        close_btn = find_node(nodes, text_match="Close")
        if close_btn is not None:
            print("❌ Closing door prompt dialog...")
            tap(close_btn.cx, close_btn.cy)
            time.sleep(1)
            continue

        # Check if app is in foreground
        focus = run_adb("shell dumpsys window | grep mCurrentFocus")
        if PACKAGE_NAME not in focus:
            print(f"🚀 Launching Nusuk app ({PACKAGE_NAME})...")
            run_adb(f"shell monkey -p {PACKAGE_NAME} -c android.intent.category.LAUNCHER 1")
            time.sleep(4)
            continue

        # Fallback tap on Keys tab
        tap(360, 1450)
        time.sleep(2)

    return False

def clear_edit_text():
    """Clear any text currently in the EditText."""
    # Tap input box to focus
    tap(360, 1104)
    time.sleep(0.3)
    # Move cursor to end and delete
    run_adb("shell input keyevent 123") # KEYCODE_MOVE_END
    run_adb("shell input keyevent " + " ".join(["67"] * 25)) # KEYCODE_DEL
    time.sleep(0.3)

def claim_key(code):
    """Claim a single key code and return (status, message)."""
    code = code.strip()
    m = re.search(r'(NG-[A-Za-z0-9_-]+)', code)
    if m:
        code = m.group(1)

    print(f"\n👉 Processing code: {code}")

    # 1. Guarantee we are on the input screen
    if not ensure_on_keys_screen():
        print("⚠️ Warning: Could not detect input screen, attempting blindly...")

    # 2. Clear input box
    clear_edit_text()

    # 3. Enter code text
    run_adb(f"shell input text {code}")
    time.sleep(0.5)

    # 4. Dismiss soft keyboard so it doesn't block 'Check the code' button
    run_adb("shell input keyevent KEYCODE_BACK")
    time.sleep(0.8)

    # 5. Tap 'Check the code'
    nodes = dump_nodes()
    check_btn = find_node(nodes, text_match="Check the code")
    if check_btn is not None:
        tap(check_btn.cx, check_btn.cy)
    else:
        tap(360, 1265)

    # 6. Wait for response from server
    time.sleep(3)

    # 7. Check result
    res_nodes = dump_nodes()
    
    # Check if Congratulations screen appeared
    congrats = find_node(res_nodes, text_match="Congratulations")
    if congrats is not None:
        count = get_current_key_count(res_nodes)
        count_str = f" (Total Keys: {count})" if count else ""
        print(f"🎉 SUCCESS! Key added successfully!{count_str}")
        
        # Click 'Add another code to get a key' to return immediately to input screen
        tap(360, 1510)
        time.sleep(2)
        return "SUCCESS", f"Key added!{count_str}"

    # Check for error messages
    used = find_node(res_nodes, text_match="already has been used")
    if used is not None:
        msg = "The code already has been used, please enter a new code."
        print(f"⚠️ FAILED: {msg}")
        clear_edit_text()
        return "ALREADY_USED", msg

    invalid = find_node(res_nodes, text_match="invalid")
    if invalid is None:
        invalid = find_node(res_nodes, text_match="not valid")
    if invalid is not None:
        print("❌ FAILED: Code is invalid.")
        clear_edit_text()
        return "INVALID", "Code is invalid"

    for n in res_nodes:
        if "please enter a new code" in n.text.lower() or "error" in n.text.lower():
            print(f"⚠️ FAILED: {n.text}")
            clear_edit_text()
            return "ERROR", n.text

    print("ℹ️ Finished submission.")
    clear_edit_text()
    return "UNKNOWN", "Finished submission"

def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else "keys.txt"
    if not os.path.exists(filepath):
        print(f"❌ Error: Keys file '{filepath}' not found.")
        print(f"   Please create '{filepath}' with one key per line.")
        sys.exit(1)

    print("=" * 55)
    print("   NUSUK CHALLENGE AUTOMATED KEY CLAIM SCRIPT")
    print("=" * 55)

    with open(filepath, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]

    if not lines:
        print(f"⚠️ No keys found in '{filepath}'.")
        sys.exit(0)

    print(f"📋 Loaded {len(lines)} key(s) from '{filepath}'.")

    ensure_device()
    ensure_on_keys_screen()

    results = []
    for idx, raw_key in enumerate(lines, 1):
        print(f"\n--- [{idx}/{len(lines)}] ---")
        status, msg = claim_key(raw_key)
        results.append((raw_key, status, msg))
        time.sleep(1)

    print("\n" + "=" * 55)
    print("                 SUMMARY REPORT")
    print("=" * 55)
    successes = sum(1 for _, s, _ in results if s == "SUCCESS")
    print(f"Total processed: {len(results)}")
    print(f"Keys added     : {successes}")
    print(f"Failed / Used  : {len(results) - successes}")
    print("-" * 55)
    for k, s, m in results:
        icon = "✅" if s == "SUCCESS" else ("⚠️" if s == "ALREADY_USED" else "❌")
        print(f"{icon} {k:<20} -> {m}")
    print("=" * 55)

if __name__ == "__main__":
    main()
