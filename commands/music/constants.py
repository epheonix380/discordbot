from enum import Enum

YOUTUBE_URL = "https://www.youtube.com/"
GENERATE_SCREEN_ID = f"{YOUTUBE_URL}/api/lounge/pairing/generate_screen_id"
GET_LOUNGE_TOKEN_BATCH = f"{YOUTUBE_URL}/api/lounge/pairing/get_lounge_token_batch"
REGISTER_PAIRING_CODE = f"{YOUTUBE_URL}/api/lounge/pairing/register_pairing_code"
GET_PAIRING_CODE = f"{YOUTUBE_URL}/api/lounge/pairing/get_pairing_code?ctx=pair"
BIND = f"{YOUTUBE_URL}/api/lounge/bc/bind"


class PlayerState(Enum):
    IDLE = 0
    PLAYING = 1
    PAUSED = 2
    LOADING = 3
    STOPPED = 4

class STATUSES(Enum):
    STOPPED = "stopped"
    STOPPING = "stopping"
    STARTING = "starting"
    RUNNING = "running"