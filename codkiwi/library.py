"""How the original containers group into the library the app presented.

Pure id arithmetic: no RenPy, no filesystem, no game content. The host decides
what to do with the grouping; this module only says which shelf each container
belongs on and what to call it. Extracted from the RenPy adapter so that the
importer and the audit tools can use it without dragging an engine along.
"""
import re


## Volume_102.exp is Volume 10 - confirmed by the project owner, not inferred.
## The id is left as the file names it so that saves and logs keep matching the
## container; only the shelf it sits on is corrected.
VOLUME_NUMBER = {'Volume_102': 10}

## Volume 1 shipped inside the application rather than as a purchasable .exp
## (tools/import_originals.py imports it from the base resource folder), so there
## were never numbered Volume 1 episodes. `1_1_Magic_School` is 'Magic School', a
## Surviving High School crossover - it opens on a school morning and a letter
## from the DMV, not a Cause of Death case - and belongs with the other specials
## rather than at the head of Volume 1.
NOT_A_VOLUME_EPISODE = {'1_1_Magic_School'}

VOLUME = re.compile(r'^Volume_(\d+)$')
EPISODE_OF_VOLUME = re.compile(r'^(\d+)_(\d+)_(.+)$')
EXTRA_OF_VOLUME = re.compile(r'^(\d+)_(?!\d+_)(.+)$')
SIDE_STORY = re.compile(r'^SS(\d+)_(.+)$')
BONUS = re.compile(r'^MTX_(.+)$')

SIDE_STORIES, BONUS_STORIES, SPECIALS, IMPORTED = (
    'Side Stories', 'Bonus Stories', 'Specials', 'Imported')
## Sorts after every numbered volume, before the named groups.
LAST_VOLUME = 10 ** 6


def truncated_ids(episodes):
    """Ids that are a shortened spelling of another id for the same content."""
    by_content = {}
    for ep in episodes:
        key = tuple(sorted(ep.get('resources', {}).values()))
        if key: by_content.setdefault(key, []).append(ep['id'])
    drop = set()
    for ids in by_content.values():
        for short in ids:
            if any(other != short and other.endswith(short) for other in ids):
                drop.add(short)
    return drop


def placement(ident):
    """(volume number, group title, sort key, label) for one episode id."""
    match = VOLUME.match(ident)
    if match:
        volume = VOLUME_NUMBER.get(ident, int(match.group(1)))
        return volume, 'Volume %d' % volume, (0, 0, ''), 'Complete volume'
    if ident in NOT_A_VOLUME_EPISODE:
        return LAST_VOLUME + 3, SPECIALS, (0, 0, ident), spaced(re.sub(r'^\d+_\d+_', '', ident))
    match = EPISODE_OF_VOLUME.match(ident)
    if match:
        volume, number, name = int(match.group(1)), int(match.group(2)), match.group(3)
        return volume, 'Volume %d' % volume, (1, number, name), 'Episode %d: %s' % (number, spaced(name))
    match = EXTRA_OF_VOLUME.match(ident)
    if match:
        volume, name = int(match.group(1)), match.group(2)
        return volume, 'Volume %d' % volume, (2, 0, name), spaced(name)
    match = SIDE_STORY.match(ident)
    if match:
        return LAST_VOLUME + 1, SIDE_STORIES, (0, int(match.group(1)), ''), spaced(match.group(2))
    match = BONUS.match(ident)
    if match:
        return LAST_VOLUME + 2, BONUS_STORIES, (0, 0, match.group(1)), spaced(match.group(1))
    return LAST_VOLUME + 3, SPECIALS, (0, 0, ident), spaced(ident)


def spaced(name):
    return name.replace('_', ' ').strip()
