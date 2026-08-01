import logging
import subprocess
import threading

from librespot.audio.decoders import AudioQuality, VorbisOnlyAudioQuality
from librespot.metadata import TrackId

logger = logging.getLogger("music.content_pipeline")

CHUNK_SIZE = 128 * 1024


def fetch_pcm(session, track_uri, output_path, quality=AudioQuality.VERY_HIGH, duration_seconds=None):
    """Pull a track from Spotify via librespot and decode it to raw PCM (s16le, 48kHz, stereo).

    Blocking -- performs network reads and drives an ffmpeg subprocess. Must be
    run off the asyncio loop, e.g. via loop.run_in_executor(...).

    Returns output_path on success.
    """
    track_id = TrackId.from_uri(track_uri)
    loaded = session.content_feeder().load(track_id, VorbisOnlyAudioQuality(quality), False, None)
    ogg_stream = loaded.input_stream.stream()

    ffmpeg_cmd = ["ffmpeg", "-y", "-i", "pipe:0", "-f", "s16le", "-ar", "48000", "-ac", "2"]
    if duration_seconds is not None:
        ffmpeg_cmd += ["-t", str(duration_seconds)]
    ffmpeg_cmd.append(output_path)

    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    def feed():
        try:
            while True:
                chunk = ogg_stream.read(CHUNK_SIZE)
                if not chunk:
                    break
                proc.stdin.write(chunk)
        except BrokenPipeError:
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    proc.wait()
    feeder.join()
    ogg_stream.close()

    if proc.returncode != 0:
        raise RuntimeError("ffmpeg exited with code {}".format(proc.returncode))

    return output_path
