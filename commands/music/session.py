from .constants import GENERATE_SCREEN_ID, GET_LOUNGE_TOKEN_BATCH, GET_PAIRING_CODE, REGISTER_PAIRING_CODE
import requests

class PlayerSession:

    screen_id: str = None
    screen_name: str = None
    screen_app: str = None
    lounge_token: str = None
    loungeTokenRefreshTimer: int = None
    pairingTokenRefreshTime: int = None
    pairingToken: str = None


    def __init__(self, guild_name, channel_name) -> None:
        _screen_id = requests.get(GENERATE_SCREEN_ID)
        self.screen_id = _screen_id.text
        self.screen_name = f"{guild_name}: {channel_name}"
        self.screen_app = "ytcr"
        _lounge_token = requests.post(f"{GET_LOUNGE_TOKEN_BATCH}?screen_ids={self.screen_id}")
        _lounge_screen = _lounge_token.json()["screens"][0]
        self.lounge_token = _lounge_screen["loungeToken"]
        _pairing_code = requests.post(url=GET_PAIRING_CODE,data={'access_type': 'permanent','app':self.screen_app,'lounge_token':self.lounge_token, 'screen_id':self.screen_id, 'screen_name':self.screen_name,'device_id':'1'})
        print(_pairing_code)
        print(_pairing_code.json())
        self.pairingToken = _pairing_code.json()        
        _idk_what_this_is = requests.post(url=REGISTER_PAIRING_CODE,data={'access_type': 'permanent','app':self.screen_app,'pairing_code':self.pairingToken, 'screen_id':self.screen_id, 'screen_name':self.screen_name,'device_id':'1'})
        print(_idk_what_this_is)
        print(_idk_what_this_is.text)



