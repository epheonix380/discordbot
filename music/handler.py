from librespot.core import Session

# This will pass the auth url to the method

def auth_url_callback(url):
    print(url)

session = Session.Builder() \
    .oauth(auth_url_callback) \
    .create()