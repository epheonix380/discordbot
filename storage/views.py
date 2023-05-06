from django.shortcuts import render
from django.http import HttpResponse
from .models import Member
import requests
import base64
import os
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

def index(req):
    try:
        code = req.GET.get("code","")
        uid = req.GET.get("state","")
        encoded_credentials = base64.b64encode(str(CLIENT_ID).encode() + b':' + str(CLIENT_SECRET).encode()).decode("utf-8")

        token_headers = {
            "Authorization": "Basic " + encoded_credentials,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        token_data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://127.0.0.1:8000/utils/callback"
        }
        #response = requests.post("https://accounts.spotify.com/api/token", data=token_data, headers=token_headers)
        #token = response.json()["access_token"]
        #user = requests.get("https://api.spotify.com/v1/me", headers={"Authorization": "Bearer " + token,})
        #username = user.json()["id"]
        password = code
        print(code)
        print("\n Spcer \n")
        member, created = Member.objects.update_or_create(member_id=uid,defaults={
           "spotify_authtoken":password})
        return HttpResponse("You have succesfully logged in")
    except:
        return HttpResponse('Error Try again')