# Nusuk Key Automation

![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue)
![Android](https://img.shields.io/badge/platform-Android-green)
![ADB](https://img.shields.io/badge/automation-ADB-lightgrey)

I got tired of pasting Nusuk invite codes into the app one by one, so I wrote
this. It connects to your Android phone over ADB, opens the Nusuk app, and
types the codes from `keys.txt` into the Keys screen for you. No root, no
modded app. It just taps the same buttons you would tap yourself.

Not affiliated with Nusuk in any way. Use it at your own risk, and if Nusuk
changes their app screens one day, this will probably need a fix.

## How the challenge works

In the Nusuk app, go to the Challenge (Games Center) and open Keys. Paste
someone else's invite code, like `NG-71ZJ8XiC`, and tap Check the code. If the
code is still good, you both get an extra key. Codes are case-sensitive, and
each one only works once between the same two people. Your own code does
nothing for you, so share it on the code boards instead and let others use it.

The codes in this repo are public codes that people shared themselves on code
boards and in comments. Nobody checked them inside the app, so plenty of them
will already be used or invalid. The script just skips those and moves on.

## What you need

- An Android phone with USB debugging turned on, Nusuk app installed and
  logged in
- A USB cable
- Either the Windows `.exe` from Releases (no Python needed, ADB is included
  in the zip) or, to run the script yourself, Python 3.8 or newer and ADB
  (Android platform-tools) on your PATH. Optional: `pip install colorama`
  for a coloured startup banner — the script works fine without it.

## Running it

**Easiest way, Windows:** download `nusuk-key-automation-windows.zip` from
the [Releases page](https://github.com/cyberfantics/nusuk-key-automation/releases),
unzip it anywhere, plug in your phone, and double-click `run_add_keys.bat`.
No Python to install. Windows may show a SmartScreen warning because the
exe is not signed — click "More info", then "Run anyway".

**From source:**

```bash
git clone https://github.com/cyberfantics/nusuk-key-automation.git
cd nusuk-key-automation
adb devices
python nusuk_add_keys.py keys.txt
```

`adb devices` should list your phone as `device`. If it says `unauthorized`,
accept the prompt on the phone and run it again. On Windows you can also just
double-click `run_add_keys.bat`.

The script prints every code and what happened to it, then a summary at the
end with the total time and the average seconds per code.

## Options

```bash
python nusuk_add_keys.py keys.txt --limit 20    # only the first 20 codes, good for testing
python nusuk_add_keys.py keys.txt --fresh       # ignore saved progress, start from the top
python nusuk_add_keys.py keys.txt --dry-run     # check the keys file, don't touch the phone
python nusuk_add_keys.py keys.txt --device ABC  # pick one phone when two are plugged in
python nusuk_add_keys.py my-codes.txt           # use a different file
```

## What is in here

| File | What it is |
| --- | --- |
| `nusuk_add_keys.py` | The script. Python, ADB and UI Automator. |
| `keys.txt` | The codes. A growing list, new codes added all the time. |
| `run_add_keys.bat` | Double-click runner for Windows. Runs the `.exe` if it is there, Python otherwise. |
| `make_icon.py` | Draws the key icon (`icon.ico` / `icon.png`) used for the `.exe` at build time. |
| `.github/workflows/build-exe.yml` | Builds the Windows `.exe` on every release. |

## One thing to know

Every code the script finishes gets deleted from `keys.txt` straight away.
Added, already used, or invalid, it is gone from the file, so the next run
never tries it again. Codes that fail with an error stay in the file and get
retried next time. That means the file shrinks as you use it, which is normal.

If you want the full record of what happened to each code, that is in
`keys.txt.progress.json` next to the keys file. It is created on your machine
when you run the script, it is not part of the repo.

## Adding your own codes

Just add a line to `keys.txt`. A full invite link works too, the script pulls
the code out of it:

```
NG-vAs47Mvj
NG-QMKx2AjR
https://services.nusuk.sa/app?p=27&id=NG-xxxxxxxx
```

Lines starting with `#` are comments. Duplicates are dropped automatically.

## How it works, briefly

The script dumps the phone screen with UI Automator, finds the input box and
the Check the code button, types the code, taps the button, and reads the
result off the screen. Then it goes again. A few things that make it quicker
than doing it by hand, or than the first version of this script:

- One ADB call per screen dump instead of two.
- Clearing the box and typing the code are batched into single calls.
- After tapping Check, it re-checks the screen every half second and moves on
  as soon as the answer shows up, instead of waiting a fixed 3 seconds.
- It does not re-check the screen before every code. Once it is on the input
  screen, it stays there. The full recovery only runs if it gets lost.
- Taps use the button's real position from the screen dump, not fixed pixels.

Even so, expect around 6 to 9 seconds per code. The phone screen and the
Nusuk server are the slow part, and there is no way around that. One phone,
one code at a time. 100 codes is about 12 minutes, the whole file is hours,
so run it in sessions and let it pick up where it stopped.

## If it breaks

| Problem | What to do |
| --- | --- |
| No Android device connected | Check the cable, turn on USB debugging, accept the prompt on the phone, run `adb devices`. |
| `adb` is not recognized | Install platform-tools and add it to PATH, or drop `adb.exe` in this folder. |
| It cannot find the input screen | Open the Nusuk app to Challenge, Keys yourself, then run it again. |
| Taps land in the wrong place | The script uses the button's real position when it can find it. If your screen is very different, open the Keys screen first and let it start from there. |
| Everything says already used | Normal for public codes. They were used by someone else first. The script moves on. |
| Lots of errors or unknowns | Usually the network or the server having a moment. Those codes stay in the file, wait a bit and run it again. |
| The phone screen turns off | The script wakes it at the start, but keep the phone plugged in for a long run. |

## Where the codes came from

Public boards: umrahcodes.click, nusukkey.xyz, thefaizulquran.online,
paperpoint.netlify.app, nusuk.abdelrahmantanira.com, plus public Facebook and
Instagram comments. If you have more, add them to `keys.txt` or open a pull
request.
