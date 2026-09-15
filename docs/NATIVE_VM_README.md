# Original .EXP playback inside CodV1 / RenPy

This is a RenPy project. Its Python Kiwi interpreter executes the original scripts directly. No transcript conversion or separate Mac application is required. The Desktop original has not been edited.

## Play an .EXP

1. Open this `CodV1-native` project in the RenPy Launcher and launch it. Development and live checks used RenPy 8.5.3.
2. Choose **Original scripts**, then **Import .EXP…**. Browse to the original file and select it. It starts playing immediately.
3. The import keeps an exact copy in the project's RenPy save directory under `kiwi-exp-library`. It appears in the episode library on subsequent launches. Importing the same bytes again does not create a second entry.

Alternatively, put files in `game/episodes/` and restart the game. Files there are discovered through RenPy's file loader, including packaged game files. Desktop file browsing has been tested; Android/iOS document pickers and web upload controls are not implemented.

The included library also offers the 103 previously extracted containers. Imported entries appear first. The shared original application assets are included: an .EXP is an expansion container and does not contain every common portrait, sound, or music track by itself. Keep `game/kiwi_assets/catalog.json` and its referenced files with the project.

The ordinary **Play** button still opens the handmade revival. Original-script play uses a separate save namespace from the Desktop project: `CoDv1-Kiwi-Native-20260913`.

## Your presentation, original script decisions

- Normal and chapter-selection choices use CodV1's existing `choice` screen. Timed choices use its `timedChoice` screen, with a VM-controlled deadline. Original return values, disabled entries, and branches are preserved. The interpreter does not jump into the handwritten chapter labels.
- **Choice interface: CodV1** in the library switches to the basic backup layout. Specialized portrait menus and score minigames currently use that backup.
- Dialogue uses the existing narrator/character styles, name positions, fonts, continuation indicators, and portrait coordinates. Runtime portraits have a circular frame to match the handmade presentation. Native backtick emphasis is translated to the existing italic styles.
- Long dialogue is paginated with balanced emphasis using the revival's desktop/small-screen length conventions. The VM advances only after the final presentation page. Long menu captions wrap inside the buttons.
- Backgrounds are centered with the revival's contain/cover setting. Chapter cards use its title/subtitle styling.
- Original music and sound cues go through RenPy's audio channels. The interpreter retains ordered media events and original resource IDs.
- Syscall **88** emits auxiliary text. In Volume 2, the exact text `Detective Score Up!` accompanies an increment of property `0:2002`; this invokes the existing `detective_score_up` screen. The script owns the score. Showing the banner does not independently add points.

Only the new VM files, main-menu entry, save namespace, and small shared-choice-screen changes were added. Handwritten chapter text and `tag_map` were not changed. The shared screen changes support disabled choices, wrap long labels, and let the VM own timed-choice expiration.

## Files and integration boundary

| File | Responsibility |
| --- | --- |
| `game/python-packages/codkiwi/vm.py` | Kiwi parser, 16-bit interpreter, stack, strings, pending syscalls |
| `game/python-packages/codkiwi/engine.py` | Engine calls, story queues, properties, choices, RNG tape, media events |
| `game/python-packages/codkiwi/exp.py` | Validated CSPUD/LZMA reader, import library, virtual media files |
| `game/python-packages/codkiwi/renpy_adapter.py` | Program cache, immutable JSON state, RenPy file hooks and media dispatch |
| `game/python-packages/codkiwi/text.py` | Presentation-only dialogue pagination |
| `game/kiwi_native.rpy` | RenPy screens, actions, characters, and interaction loop |
| `tools/import_originals.py` | Optional bulk packaging of the known corpus; not needed for in-game imports |
| `docs/validation/` | Test results and comparison reports |

Mutable interpreter objects live outside RenPy's store. Each interaction restores an interpreter from `kiwi_snapshot`, executes an action, then replaces the snapshot with a new JSON string. Program and imported-resource caches remain module-local. Save/rollback state contains no open resource streams or generator objects. RNG uses `renpy.random` when the VM needs more random words.

The existing full syscall reference is [KIWI_CALL_REFERENCE.txt](docs/KIWI_CALL_REFERENCE.txt), with opcode details in [KIWI_OPCODE_REFERENCE.json](docs/KIWI_OPCODE_REFERENCE.json). This port follows that reconstruction; the score-banner mapping above adds direct Volume 2 script evidence for the role of call 88.

## Validation completed

- JavaScript/Python parity: **12,245 matching interaction states across 103 containers**, including VM registers, stack, mutable data, properties, UI, media events, and random cursor. This is a migration check against the reconstructed JavaScript VM, not an original iPhone oracle.
- Direct EXP import: **8,617 resources and 420 scripts across 103 containers** matched the earlier extracted bytes; no differences.
- Six Python integration tests: malformed container rejection; import/restart/resource access; deduplication; snapshot replay and immutability through the first score cue; score banner dispatch; adapter import/replay.
- Four text tests: emphasis across page boundaries, unchanged short text, long words, empty text.
- RenPy lint: no new diagnostics after normalizing changed line numbers. The handmade revival already has lint findings; this is not a claim that the entire project has clean lint.
- Live RenPy SDK: imported the original Volume 2 EXP through the in-game picker; opened its introductory prompt and chapter card; compared the handmade Chapter 1 presentation; checked character positions and background centering; navigated chapter groups and chapter choices using the existing CodV1 screen; observed disabled chapter entries; exercised the original timed-choice timeout branch.
- Live score/save/rollback: observed the score-up banner, inspected `0:2002 == 1`, rolled back to `0`, saved and loaded the scoring state, and confirmed the loaded value was `1` with the corresponding dialogue. A temporary test fixture initially retained an open file object in store; that fixture was corrected, and the clean test passed. That fixture is not included in this project.

Run the focused tests from this project directory:

```sh
python3 tests/test_text.py
python3 tests/test_integration.py /path/to/Volume_2.exp
```

The parity scripts in `tools/` require the earlier JavaScript reconstruction/corpus fixtures; the reports are included here.

## Fidelity still to verify

This is an operational interpreter integration, not a certification of perfect original-app playback.

- Original iPhone differential testing remains necessary for exact animation, audio fades, captions, panning, and scheduling. Volume 2's handmade scenes are a visual reference, not a timing oracle.
- The time adapter currently uses 1,000 native units per second. Action minigame round transitions/input gaps and remaining-time behavior around save/load need further original-device validation.
- Optional Kiwi library/external instruction sets are rejected explicitly. None occurs in the supplied 420 scripts. Bare VM yields and unimplemented platform calls stop with a diagnostic rather than inventing results.
- Native platform calls 9/30/32/87/95 need explicit adapters if encountered. Forms/loading use a basic continuation. Network/ads and unresolved presentation calls are not reproduced as native platform services. Explicit vibration cues use RenPy’s Android vibration API; desktop and iOS vibration are not provided by that API.
- Imported native iPhone `.sav` files are not supported. RenPy saves are supported. Changing this interpreter's schema or scripts may require a save migration.
- Dynamic portrait-menu layouts and score minigames retain the basic interface. Exact native audio/visual transitions and all branch paths have not been exhaustively validated in RenPy.
- EXP imports are loaded into memory and reference shared original resources. Files from another game or an unknown container/version are not promised to work.

Keep improving fidelity at the engine-call boundary. Avoid replacing VM branches, property updates, or score arithmetic with handwritten RenPy equivalents: the original scripts already provide those decisions.

## Volume 9 menu correction

The pipe-menu portrait selector identifies an actor, not a raw image resource. The adapter resolves it through the actor portrait map. Volume 9 Chapter 1 actor 15 maps to portrait 26010. Older development menu views are also resolved when their stored value points to a non-image. The reused timed-choice screen now updates its local countdown variable with `SetLocalVariable`, so the visible bar decreases alongside the VM deadline. Regression: `python3 tests/test_volume9_menu.py`.

## Dialogue emphasis and vibration

Original call 89 (the model flag at +0x400) now sets a one-interaction dialogue emphasis cue. Volume 3 Chapter 1 corroborates the mapping: the opening gunshot and “Oh god... Oh god...” set it, while the intervening ordinary narration does not. RenPy combines the revival’s character/narrator shake with a short 1.12 → 0.97 → 1.0 scale pulse. The cue applies only to the first presentation page of that native dialogue and resets afterward. This is a presentation mapping based on script/reference correspondence; exact original animation timing remains unmeasured.

Call 82 separately invokes `renpy.vibrate(kiwi_vibration_seconds)`. The duration defaults to 0.2 seconds because the original call supplies no duration argument. The installed RenPy 8.5.3 API supports vibration on Android only; desktop and iOS do not vibrate through it. Physical-device vibration has not been tested. Tests: `python3 tests/test_emphasis.py`.


## Script fades and portrait proportions (2026-09-13)

Call 16 queues the next UI-exit transition. Its style 6 now fades through black when that UI is dismissed, including the new dialogue and portrait on fade-in. The pending cue lives in the VM snapshot, is consumed once, and replays after rollback. Advancing Volume 5 Chapter 1's "You are dead." now fades to Mal's street scene. No fade is inferred from a background change or vibration. The native fade duration is 1.5 seconds per half; exact opacity keyframes/easing and style 1/2/20 blinds remain outstanding. See call 16 in `docs/KIWI_CALL_REFERENCE.txt` for native addresses.

Portraits now use aspect-preserving containment within the existing 300-pixel circular composition. Backup-menu thumbnails also preserve proportions. Live RenPy checks covered the Volume 5 fade and the Volume 9 choice portrait. `tests/test_fade.py` verifies original-bytecode cue ordering, one-shot consumption, and snapshot replay. Lint introduced no new diagnostics relative to the handmade baseline. Existing saves created before queued fades were recorded may need a rollback to before the call, or a chapter restart, to pick up that cue.

Android portrait orientation belongs in `android.json`, not as an XML attribute in `options.rpy`. Generated signing keystores and local launcher state are excluded from Git.


## Text-entry layout (2026-09-14)

VM text entry reuses the revival's `input` screen with `show_kiwi_layout=True`: the same font and textbox asset, a centered field at dialogue height, and local padding instead of absolute dialogue offsets. The handmade chapters keep their existing layout. As in the handmade Volume 5 Chapters 4 and 5, an already-delivered dialogue question is followed by only the editable `Guess`/`Name` field, not a repeated question inside it. Standalone inputs without prior dialogue retain their prompt. Original prompt metadata, the native 20-character limit, and script answer comparisons remain unchanged.

`tests/test_input.py` reaches both prompts through original chapter-selection bytecode and verifies their presentation metadata and correct-answer branches. The live name-entry check accepted `Fuentes` and returned the original Patrick response. Tests use the original capitalization (`Father`, `Fuentes`), not the handmade scripts' additional lowercase normalization.

## Narration pagination (2026-09-14)

Removed the port's 109/170-character cutoff for narration. Original narration measures a complete text block at a 220-unit width and sizes its bubble to the measured height; it does not use our character-count rule. Complete script narration now wraps in one RenPy bubble, including the Volume 5 Chapter 4 docks/EMT sentence. Character dialogue pagination remains separate and approximate. See `docs/NATIVE_TEXT_LAYOUT.md` for the native addresses and fidelity limits.
