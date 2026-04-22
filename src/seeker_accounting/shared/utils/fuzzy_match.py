"""Lightweight fuzzy-matching utility for the command palette.

Scores how well *query* matches *target* using character-subsequence matching
with bonuses for consecutive runs, word-boundary alignment and prefix hits.

Returns ``None`` when there is no viable match — callers should treat that as
"doesn't match at all".  Otherwise returns a ``float`` in roughly the 0-1
range (higher is better).  Scores may exceed 1.0 when many bonuses stack.
"""

from __future__ import annotations


def fuzzy_score(query: str, target: str) -> float | None:
    """Return a relevance score for *query* against *target*, or ``None``.

    The algorithm walks each query character and tries to find it (case-
    insensitively) in the remaining portion of *target*.  Bonuses are awarded
    for:

    * **Consecutive** characters that align next to each other.
    * **Word-boundary** hits (start of word after space / underscore / camelCase).
    * **Prefix** alignment (query[0] matches target[0]).
    * **Exact** full-string match.

    If any query character cannot be found the function returns ``None``.
    """
    if not query:
        return 0.0
    if not target:
        return None

    q = query.lower()
    t = target.lower()

    # Fast path — exact / substring match.
    if q == t:
        return 2.0
    if q in t:
        idx = t.index(q)
        return 1.5 + (0.3 if idx == 0 else 0.0)

    q_len = len(q)
    t_len = len(t)

    # Build set of word-boundary positions in target.
    boundaries: set[int] = {0}
    for i in range(1, t_len):
        prev = target[i - 1]
        curr = target[i]
        if prev in (" ", "_", "-", "/", ".", "("):
            boundaries.add(i)
        elif prev.islower() and curr.isupper():
            boundaries.add(i)

    score = 0.0
    t_idx = 0
    prev_match_idx = -2  # sentinel — not adjacent

    for qi in range(q_len):
        ch = q[qi]
        found = False
        while t_idx < t_len:
            if t[t_idx] == ch:
                # Award base point.
                score += 1.0
                # Consecutive bonus.
                if t_idx == prev_match_idx + 1:
                    score += 0.8
                # Word-boundary bonus.
                if t_idx in boundaries:
                    score += 0.6
                # Prefix bonus — first query char hits first target char.
                if qi == 0 and t_idx == 0:
                    score += 0.5
                prev_match_idx = t_idx
                t_idx += 1
                found = True
                break
            t_idx += 1

        if not found:
            return None

    # Normalise so a perfect prefix match of N chars on a length-N target → ~1.0.
    return score / (q_len + t_len) * 2.0
