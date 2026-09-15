"""Presentation-only pagination; never changes the VM's stored dialogue."""
import re


def dialogue_pages(text, limit=170):
    if limit is None:
        # Native narration sizes its bubble to the entire script string.
        return [str(text)]
    words = re.findall(r'\S+\s*', str(text))
    pages, current, count, emphasis = [], '', 0, False
    for word in words:
        visible = len(word.replace('`', ''))
        if count and count + visible > limit:
            pages.append(current.rstrip() + ('`' if emphasis else ''))
            current = '`' if emphasis else ''
            count = 0
        current += word
        count += visible
        if word.count('`') % 2:
            emphasis = not emphasis
    if current or not pages:
        pages.append(current.rstrip())
    return pages


def story_pages(view, small=False):
    """Keep native narration intact; character-box pagination remains separate."""
    if view.get('speaker'):
        limit = 109 if small else 170
    elif view.get('title'):
        # A titled event line (syscall 15) is the native VOICE box: bounded like
        # the revival's no-image characters, not sized to the whole string. An
        # event line with no title is ordinary narration and stays unbounded.
        limit = 170 if small else 190
    else:
        limit = None
    return dialogue_pages(view['text'], limit)
