# codkiwi

A Python interpreter for the KiWi bytecode that ran EA's *Cause of Death*
(2010, iOS). It executes the game's original `.exp` script containers directly
— no transcription, no conversion step, no original binary — and reports what
happened as plain serializable data: a line of dialogue, a menu, a background
change, a sound cue.

It carries no game content. Bring your own `.exp` files.

```python
from codkiwi import StoryRuntime, parse_kiwi
from codkiwi.exp import unpack

resources = unpack(open('Volume_6.exp', 'rb').read())
programs = {rid: parse_kiwi(b) for rid, b in resources.items() if b[:4] == b'kiwi'}

story = StoryRuntime(programs, resource_ids=resources)
story.start(25001)                 # the container's entry script

for _ in range(20):                # print the opening, taking the first option at any menu
    print(story.ui['speaker'], story.ui['text'])
    choices = story.ui['choices']
    story.respond(choices[0]['value'] if choices else 0)
```

`story.ui` is a plain dict — `kind`, `speaker`, `text`, `choices` — and
`story.effects.events` is the ordered list of background, music and sound cues
for the step just taken. Drawing them is the host's job.

To open one chapter rather than the volume's menu, select it the way the game
did and load it:

```python
story.reset(); story.load(25001); story.run()
story.properties['0:1001'] = 25008 - 25001     # the chapter gate
story.load(25008); story.run()
```

## What it is

The original game is a stack machine with a host. `codkiwi` is both halves:

- **`codkiwi/vm.py`** — the machine. 16-bit cells, a 1024-word stack based at
  `0x7bf5`, opcodes `0x00`–`0x62`, eleven host string slots at `0x7ff5`. It
  faults on an uninitialized read, a bounds error or division by zero rather
  than reproducing whatever the original did there.
- **`codkiwi/engine.py`** — the host. The `syscall` method answers the ~60
  engine services the scripts actually call: dialogue, choices and timed
  choices, text entry, the numeric/bit/array property store, character names
  and substitutions, portraits and expressions, backgrounds, music and sound,
  chapter cards, the weighted RNG. It produces a `ui` dict and an ordered list
  of media events; it draws nothing and owns no assets.
- **`codkiwi/exp.py`** — the container format. `.exp` is `CSPUD`: a resource
  table of 16-bit ids and 32-bit offsets, each payload either stored or raw
  LZMA1. Size limits are enforced before allocation.
- **`codkiwi/library.py`** — how the 103 known containers group into volumes,
  side stories, bonus stories and specials. Pure id arithmetic.
- **`codkiwi/text.py`** — presentation-only pagination. Never changes what the
  VM stored.

`StoryRuntime.snapshot()` / `.restore()` round-trip a whole playthrough through
JSON, so saves are host-independent.

## Where the behaviour comes from

The interpreter was reconstructed black-box: run original scripts, watch what
breaks, fix the model, run the whole corpus again. Where a rule could not be
derived from evidence it raises instead of guessing — a deliberately small
number of services are left to a host adapter rather than answered with a
plausible zero.

Two examples of the method, both load-bearing:

- **Chapter entry.** Every script opens with a gate that reads global property
  `1001` and halts unless it equals `rid - entry`. That holds for 317 of 317
  gated programs across the 103-container corpus, so `tools/pack_exp.py` reads
  the gate out of each program rather than assuming it.
- **Typed answers.** The scripts store answers in sentence case — `Hedge hog`,
  `Denture cream` — and 114 of the 126 distinct answers in the corpus are
  exactly that, with all twelve exceptions sitting beside one that is. That is
  only explicable if the comparison folded case, so `engine.fold` does.

`docs/` holds the working notes: `KIWI_OPCODE_REFERENCE.json` and
`KIWI_CALL_REFERENCE.txt` are the opcode and service inventories,
`NATIVE_VM_README.md` describes how this engine was embedded in a Ren'Py
revival of the game, and `validation/` is the log of what was checked against
what.

## Known limits

- Services `9`, `30`, `32`, `87` and `95` raise unless the host passes a
  `host_call`. *Cause of Death* makes none of them: across all 420 scripts in
  the 103 containers there is not one call site, and no script computes a
  service id at runtime. Its sibling *Surviving High School*, on the same
  engine, calls two of them constantly.
- The mini-games — services `71` (timed word choices) and `78` (portrait
  selector) — run; services `94` (football) and `96` (word grids) do not, and
  answer with their neutral branch. *Cause of Death* calls neither.
- Service `100` is answered as a no-op along with everything above `99`. It has
  four call sites in the corpus and an unresolved native effect.
- Linked/previous script segments are parsed but not executed. No container in
  the corpus sets that flag.
- The random stream is the host's, not the original's libc stream, so shuffles
  and weighted draws differ from the 2010 game even though the rules match.
- The stack is 1024 words, as the original's was, and the scripts' menus loop
  back on themselves. A driver that answers every menu with the same option can
  re-enter without returning until the stack fills — roughly 4,700 answers into
  Volume 6. Answering menus normally peaks under 200 words.

## Tools

| | |
| --- | --- |
| `tools/pack_exp.py` | Unpack an `.exp` into a chapter pack: every resource content-addressed on disk, plus a `pack.json` naming the entry script and each chapter's gate |
| `tools/import_originals.py` | Build a library catalogue from a folder of containers, dropping truncated duplicates |
| `tools/check_js_parity.py` | Differential-test this VM against the earlier JavaScript reconstruction |

## Tests

```sh
python3 -m unittest discover -s tests
python3 tests/test_guess.py path/to/Volume_6.exp   # the corpus tests, given a container
```

Tests that need original content skip without it.

## Licence

MIT — see [LICENSE](LICENSE). That covers this interpreter and its tooling
only. *Cause of Death*, its scripts and its artwork remain the property of
their owner; nothing of theirs is included here, and playing an `.exp` with
this engine means supplying your own copy.
