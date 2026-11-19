# TP Auto Clicker

An auto clicker plus a screen-watching automation engine. The clicker does fast,
accurate repeated clicks. Automation watches the screen for buttons and popups
(by image matching) and clicks through a sequence for you, for example: wait
for the **LEVEL CLEARED** popup, click **RETRY**, turn on **2X** speed, click
**START**, and repeat forever.

## Download (Windows)

Grab `TPAutoClicker.exe` from the [Releases page](https://github.com/nichham2/tpautoclicker/releases),
or from the latest **Build Windows exe** run on the Actions tab (Artifacts section).
No Python needed: put the exe in its own folder and double-click it. On first run it
creates `templates/` and `sequences/` next to itself (with the bundled tower-defense
loop) and saves `settings.json` there too. Windows SmartScreen may warn because the exe
isn't signed: click *More info → Run anyway*.

To build the exe yourself on Windows: install Python, then double-click `build.bat`
(or run it from a terminal). It sets up a private environment in `.venv`, runs the
tests, builds `dist\TPAutoClicker.exe` and self-tests it.

To publish a new release: write its notes in `release-notes/vX.Y.Z.md`, then run the
**Build Windows exe** workflow by hand (Actions tab → *Run workflow*) with that tag in
*draft_release*. It builds, tests and attaches the exe to a **draft** release for you to
review and publish. (Pushing a `vX.Y.Z` tag still publishes straight away.)

## Run from source

1. Python 3.9+ (Windows is the main target; macOS/Linux mostly work).
2. `pip install -r requirements.txt`
3. `python tpautoclicker.py`

> On Linux the `keyboard` package needs root. On Windows, run the app as
> administrator if a game ignores the clicks (games running as admin only accept
> input from admin programs).

## Mini controls (always on top)

A small floating bar sits on top of the game with **Click**, **Auto** and **■ stop
everything** buttons plus a live status line (click count, or which loop/step the
automation is on). It never steals focus from the game. Drag it by the grip,
right-click for opacity, hide it with ✕, and turn it back on in *Settings → Appearance*
or the tray menu. Games in exclusive fullscreen draw over everything; use
borderless/windowed fullscreen to see the bar.

## Look

A compact, pro-tool style: charcoal panels with small corners, darker inset
fields, small type and tight spacing, teal/blue highlights, and an icon tool
rail on the left for Clicker, Automation, Log and Settings (the button at the
bottom of the rail shows/hides the mini controls). Dark is the default;
*Settings → Appearance* also has Light and System modes and a choice of accent
colours (or pick your own).

## Clicker page

- **Start/stop** with the button or the hotkey (default **F6**). Stopping is instant.
- **Interval** in milliseconds with presets, live clicks-per-second readout.
- **Random variation** (0-50%) so clicks aren't perfectly regular.
- **Single or double** clicks, **left/right/middle** button.
- **Click where the cursor is**, or at a **fixed spot** (use *Pick…* to choose it on screen).
- **Stop after** N clicks and/or N seconds.
- **Hold key** while clicking (released when you stop), and a **start delay**.
- **Anti-AFK**: nudges the mouse a few pixels every N seconds and puts it back.

## Automation page

A *sequence* is a list of steps saved as JSON in `sequences/`. The images it looks
for are PNGs in `templates/`.

| Step | What it does |
| --- | --- |
| Wait until image appears | Polls the screen until a template shows up (or times out) |
| Wait until image disappears | Polls until it goes away |
| Find image and click it | Clicks the centre of the match (plus an optional offset). *Until gone* re-clicks if the game missed it. *Fallback key* presses a key if the image never appears |
| Click a fixed position | Click at x, y |
| Press a key | e.g. `space`, `enter`, `ctrl+s` |
| Wait | Fixed time with optional random extra |
| Wait until a pixel is a colour | Cheap check for a single pixel |

Every step can be switched off, has a label, a *delay after*, and an **if it fails**
policy: `stop`, `skip` (carry on), or `restart` (back to step 1).

**Making your own:** *Add step → Find image and click it*, then *Capture…* next
to Template. The app hides, waits a few seconds (so you can switch to the game),
takes a screenshot, and lets you drag a box around the button. *Test* tells you
right away whether the image is on screen and how confident the match is.

**Resolution:** positions are stored for the sequence's reference resolution and
scaled to your screen. Templates are scaled the same way, and if *look at other
sizes* is on, nearby sizes are tried too.

**Stopping:** the automation hotkey (default **F7**), the stop-everything hotkey
(default **F8**), or slam the mouse into the **top-left corner** of the screen.

### Bundled: tower defense retry loop

`sequences/tower_defense_retry_loop.json` (built from a screen recording at 1920×1080):

1. Wait for the end-of-level popup, whatever its title (LEVEL CLEARED, THE BASE DROWNED, ...), by looking for its **RETRY** button (no time limit)
2. Click **RETRY** (re-click until the popup goes away)
3. Wait for the setup screen (the **START (SPACE)** button)
4. Click **2X** to turn on double speed (skipped if not found; untick this step if your speed setting persists)
5. Click **START** (press Space if the button can't be found)
6. Repeat

If you start it while already on the setup screen, select step 3 and press
*Start from selected step*. If the game runs at a very different resolution and
the bundled images stop matching, recapture them with *Capture…*.

## Settings tab

Hotkeys, which monitor the game is on, how often to check the screen, match
confidence, the corner failsafe, capture delay, tray/notification/sound options,
update check. Settings save to `settings.json` next to the app (older v3
`settings.json` files are migrated automatically).

## Development

```
pip install -r requirements.txt pytest
QT_QPA_PLATFORM=offscreen pytest
```

The tests drive the bundled sequence against real frames from the recording
(`tests/fixtures/`) with a fake game that reacts to clicks.

Layout: `tpac/clicker.py` (click + AFK engines), `tpac/vision.py` (capture and
matching), `tpac/sequence.py` (step model and runner), `tpac/app.py` (window),
`tpac/editor.py` / `tpac/picker.py` (dialogs and on-screen picker). The previous
version is kept in `stable/`.

## Notes

Use responsibly. Some games forbid automation; check their rules. Provided as-is,
with no responsibility for bans or other consequences.
