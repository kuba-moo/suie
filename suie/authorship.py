"""Who wrote a patch, as opposed to who sent it"""

import re
from email.utils import parseaddr

# In-body headers git am understands, at the very top of the body
INBODY_HDR_RE = re.compile(r'^(From|Date|Subject):\s*(.*)$')
# Separator line of git format-patch output, if someone pasted it in whole
MBOX_FROM_RE = re.compile(r'^From [0-9a-f]{40} ')


def get_inbody_author(content: str) -> tuple[str, str] | None:
    """
    Get the author of a patch sent on behalf of someone else, from the
    From: line git send-email puts at the top of the body. Parsed the same
    way ml-stat.py does, so the stats and the scores agree on who wrote what.

    Args:
        content: Patch content (commit message) as Patchwork stores it

    Returns:
        (name, email) of the author, or None if there is no in-body From:
    """
    lines = (content or '').lstrip('\n').splitlines()
    if lines and MBOX_FROM_RE.match(lines[0]):
        lines = lines[1:]

    for line in lines:
        m = INBODY_HDR_RE.match(line)
        if not m:
            break
        if m.group(1) != 'From':
            continue
        name, addr = parseaddr(m.group(2))
        # git writes "Name <addr>", anything else is likely hand-typed garbage
        if '<' in m.group(2) and '@' in addr:
            return name, addr
        break
    return None
