# Original narration layout

The 109-character small-screen pagination limit was introduced by this RenPy port. It is not an original narration limit.

ARMv7 evidence from CoD 1.3.4:

- `SHSUIDialog::setCurrentSpeaker` at `0x3d1ac`: the event-speaker comparison at `0x3d258..0x3d27a` selects speaker type 4.
- `SHSUIDialog::animateTextLayer` at `0x3c4e4`: the type-4 branch at `0x3c5e4` obtains the complete text at dialog +0x2c and the narration font at +0xcc.
- `0x3c60a..0x3c60e` calls `CSFont::getBlockWidth` with a width of 220 original logical units.
- `0x3c624..0x3c62e` calls `CSFont::getTextHeight` with float width 220 (0x435c0000), then uses that measured height to size the narration bubble. This path does not divide the string at a fixed number of characters.
- `CSFont::getTextHeight` at `0x48ac` measures using the font drawing/layout implementation. Exact glyph metrics are a separate requirement for pixel-identical wrapping.

The RenPy player now passes each complete narration string to its existing wrapping and bubble renderer on both small and desktop variants. It preserves explicit script dialogue boundaries, text, and backtick emphasis. Character dialogue still uses the prior 109/170 presentation limits; those are not claimed to match original character-box pagination. The revival fonts and dimensions remain in use, so this change matches narration block boundaries, not every original line break or pixel measurement.

Regression: Volume 5 script 25009 contains the complete 120-character docks/EMT sentence ending in “her shoulders.” The old small-screen paginator split precisely before that phrase. The narration path now returns one page for the entire string. See `tests/test_text.py`.
