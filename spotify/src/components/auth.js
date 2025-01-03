const dotenv = require("dotenv");
const axios = require("axios");
const fs = require("fs");

// Client id and secret
dotenv.config();
const spotify_client_id = process.env.SPOTIFY_CLIENT_ID;
const spotify_client_secret = process.env.SPOTIFY_CLIENT_SECRET;

// Tokens
const filename = ".token.json";
const data = fs.existsSync(filename)
  ? JSON.parse(fs.readFileSync(filename))
  : {};
let access_token = data.access_token ?? "";
let refresh_token = data.refresh_token ?? "";
let token_expiry = new Date(data.token_expiry ?? 0);

// Login / get access token (from https://developer.spotify.com/documentation/web-playback-sdk/howtos/web-app-player)
const login = (req, res) => {
  const scope = "streaming user-read-private user-read-email";
  const state = Math.random().toString();

  const auth_query_parameters = new URLSearchParams({
    response_type: "code",
    client_id: spotify_client_id,
    scope: scope,
    redirect_uri: `http://${req.get("host")}/auth/callback`,
    state: state,
  });

  res.redirect(
    "https://accounts.spotify.com/authorize/?" +
      auth_query_parameters.toString()
  );
};

// Login callback
const loginCallback = async (req, res) => {
  const code = req.query.code;

  const authOptions = {
    url: "https://accounts.spotify.com/api/token",
    method: "post",
    data: new URLSearchParams({
      code: code,
      redirect_uri: `http://${req.get("host")}/auth/callback`,
      grant_type: "authorization_code",
    }),
    headers: {
      Authorization:
        "Basic " +
        Buffer.from(spotify_client_id + ":" + spotify_client_secret).toString(
          "base64"
        ),
      "Content-Type": "application/x-www-form-urlencoded",
    },
  };

  const response = await axios(authOptions);
  parseResponse(response);
  return { access_token, refresh_token };
};

const parseResponse = (response) => {
  access_token = response.data.access_token;

  if (response.data.refresh_token != undefined) {
    // Only update refresh token if it is returned
    refresh_token = response.data.refresh_token;
  }

  const expiryMilliseconds = response.data.expires_in * 1000;
  const date = new Date(response.headers.date);
  token_expiry = new Date(date.getTime() + expiryMilliseconds);
  fs.writeFileSync(
    filename,
    JSON.stringify({ access_token, refresh_token, token_expiry })
  );
};

const refreshToken = async () => {
  const authOptions = {
    url: "https://accounts.spotify.com/api/token",
    method: "post",
    data: new URLSearchParams({
      refresh_token: refresh_token,
      grant_type: "refresh_token",
    }),
    headers: {
      Authorization:
        "Basic " +
        Buffer.from(spotify_client_id + ":" + spotify_client_secret).toString(
          "base64"
        ),
      "Content-Type": "application/x-www-form-urlencoded",
    },
  };
  const response = await axios(authOptions);
  parseResponse(response);
};

const getToken = () => {
  if (refresh_token.length > 0 && new Date() > token_expiry) {
    refreshToken();
  } else if (access_token.length == 0 && refresh_token.length > 0) {
    refreshToken();
  }
  return access_token;
};

const ready = () => refresh_token != "";

exports.login = login;
exports.loginCallback = loginCallback;
exports.token = getToken;
exports.ready = ready;
