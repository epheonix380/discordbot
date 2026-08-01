"""Manual verification script for SPOTIFY_CONNECT_PLAN.md Phase 2.

Not wired into the bot or CI -- run by hand against a real Spotify Premium
account to prove the audio pipeline (creds -> Session -> content_feeder ->
ffmpeg -> PCM file) actually works end to end. This is the check Phase 0
would have covered; it was skipped in the sandbox that wrote this code, so
this script is the acceptance test for whoever has real credentials.

Usage:
    python -m music.phase2_smoke_test <credentials.json> <spotify:track:...> [output.pcm] [duration_seconds]

<credentials.json> must be the JSON blob written by librespot.oauth.OAuth.save_creds(),
i.e. {"client_id", "access_token", "expires_at", "refresh_token", "type"}.

Success looks like: no exceptions, and `output.pcm` contains
sample_rate(48000) * channels(2) * bytes_per_sample(2) * duration_seconds
bytes of audio that plays back correctly (e.g. via
`ffplay -f s16le -ar 48000 -ac 2 output.pcm`).
"""
import json
import sys

from music.content_pipeline import fetch_pcm
from music.session_manager import build_session


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    credentials_path = sys.argv[1]
    track_uri = sys.argv[2]
    output_path = sys.argv[3] if len(sys.argv) > 3 else "phase2_smoke_test_output.pcm"
    duration_seconds = int(sys.argv[4]) if len(sys.argv) > 4 else 10

    with open(credentials_path) as f:
        credentials_json = json.load(f)

    print("Building librespot session...")
    session = build_session(credentials_json)
    try:
        print("Fetching {}s of {} ...".format(duration_seconds, track_uri))
        fetch_pcm(session, track_uri, output_path, duration_seconds=duration_seconds)
        print("Wrote", output_path)
    finally:
        session.close()


if __name__ == "__main__":
    main()
