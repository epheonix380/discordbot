import re

# SPOTIFY_CONNECT_PLAN.md §7 assigns this module free-text search via the Web
# API too, but that's explicitly Phase 6 ("Search & queue") -- not implemented
# here. This only resolves a query that's already a direct Spotify track
# URI/URL, which is what Phase 4's `,play` needs.

_TRACK_URI_RE = re.compile(r"^spotify:track:([A-Za-z0-9]{22})$")
_TRACK_URL_RE = re.compile(r"open\.spotify\.com/track/([A-Za-z0-9]{22})")


def resolve_track_uri(query):
    """Resolve a ,play argument to a spotify:track:<id> URI, or None if it
    isn't a recognizable direct track URI/URL (e.g. a free-text search)."""
    query = query.strip()
    match = _TRACK_URI_RE.match(query)
    if match:
        return "spotify:track:{}".format(match.group(1))
    match = _TRACK_URL_RE.search(query)
    if match:
        return "spotify:track:{}".format(match.group(1))
    return None
