from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import requests
import os
from datetime import datetime, timedelta
import base64

from .models import (
    Guild, Member, Channel, GuildActivity, MemberGuildActivity, WeightedGuildActivity,
    GuessTheHero, ListOfChoices, Item, MemberReminder, MemberGymDay, GameVersion,
    GameVersionSubscriptions, MemberPlaylist, PlaylistElement, ComplexFrequecy,
    BotIgnoreChannels, SpotifyToken, TimeZone, MemberTimeZoneMap
)
from .serializers import (
    GuildSerializer, MemberSerializer, ChannelSerializer, GuildActivitySerializer,
    MemberGuildActivitySerializer, WeightedGuildActivitySerializer, GuessTheHeroSerializer,
    ListOfChoicesSerializer, ItemSerializer, MemberReminderSerializer, MemberGymDaySerializer,
    GameSerializer, GameSubscriptionSerializer, MemberPlaylistSerializer, PlaylistElementSerializer,
    ComplexFrequecySerializer, BotIgnoreChannelsSerializer, SpotifyTokenSerializer,
    TimezoneSerializer, TimeMapSerializer
)

# Create your views here.

class GuildViewSet(viewsets.ModelViewSet):
    queryset = Guild.objects.all()
    serializer_class = GuildSerializer
    
    @action(detail=False, methods=['get'])
    def by_guild_id(self, request):
        guild_id = request.query_params.get('guild_id')
        if guild_id:
            guild = Guild.objects.filter(guild_id=guild_id).first()
            if guild:
                serializer = self.get_serializer(guild)
                return Response(serializer.data)
        return Response({'error': 'Guild not found'}, status=status.HTTP_404_NOT_FOUND)

class MemberViewSet(viewsets.ModelViewSet):
    queryset = Member.objects.all()
    serializer_class = MemberSerializer
    
    @action(detail=False, methods=['get'])
    def by_member_id(self, request):
        member_id = request.query_params.get('member_id')
        if member_id:
            member = Member.objects.filter(member_id=member_id).first()
            if member:
                serializer = self.get_serializer(member)
                return Response(serializer.data)
        return Response({'error': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

class ChannelViewSet(viewsets.ModelViewSet):
    queryset = Channel.objects.all()
    serializer_class = ChannelSerializer

class GuildActivityViewSet(viewsets.ModelViewSet):
    queryset = GuildActivity.objects.all()
    serializer_class = GuildActivitySerializer
    
    @action(detail=False, methods=['get'])
    def by_guild(self, request):
        guild_id = request.query_params.get('guild_id')
        if guild_id:
            activities = GuildActivity.objects.filter(guild__guild_id=guild_id).order_by('-date')
            serializer = self.get_serializer(activities, many=True)
            return Response(serializer.data)
        return Response({'error': 'Guild ID required'}, status=status.HTTP_400_BAD_REQUEST)

class MemberGuildActivityViewSet(viewsets.ModelViewSet):
    queryset = MemberGuildActivity.objects.all()
    serializer_class = MemberGuildActivitySerializer

class WeightedGuildActivityViewSet(viewsets.ModelViewSet):
    queryset = WeightedGuildActivity.objects.all()
    serializer_class = WeightedGuildActivitySerializer

class GuessTheHeroViewSet(viewsets.ModelViewSet):
    queryset = GuessTheHero.objects.all()
    serializer_class = GuessTheHeroSerializer

class ListOfChoicesViewSet(viewsets.ModelViewSet):
    queryset = ListOfChoices.objects.all()
    serializer_class = ListOfChoicesSerializer

class ItemViewSet(viewsets.ModelViewSet):
    queryset = Item.objects.all()
    serializer_class = ItemSerializer

class MemberReminderViewSet(viewsets.ModelViewSet):
    queryset = MemberReminder.objects.all()
    serializer_class = MemberReminderSerializer

class MemberGymDayViewSet(viewsets.ModelViewSet):
    queryset = MemberGymDay.objects.all()
    serializer_class = MemberGymDaySerializer

class GameVersionViewSet(viewsets.ModelViewSet):
    queryset = GameVersion.objects.all()
    serializer_class = GameSerializer

class GameVersionSubscriptionsViewSet(viewsets.ModelViewSet):
    queryset = GameVersionSubscriptions.objects.all()
    serializer_class = GameSubscriptionSerializer

class MemberPlaylistViewSet(viewsets.ModelViewSet):
    queryset = MemberPlaylist.objects.all()
    serializer_class = MemberPlaylistSerializer

class PlaylistElementViewSet(viewsets.ModelViewSet):
    queryset = PlaylistElement.objects.all()
    serializer_class = PlaylistElementSerializer

class ComplexFrequecyViewSet(viewsets.ModelViewSet):
    queryset = ComplexFrequecy.objects.all()
    serializer_class = ComplexFrequecySerializer

class BotIgnoreChannelsViewSet(viewsets.ModelViewSet):
    queryset = BotIgnoreChannels.objects.all()
    serializer_class = BotIgnoreChannelsSerializer

class SpotifyTokenViewSet(viewsets.ModelViewSet):
    queryset = SpotifyToken.objects.all()
    serializer_class = SpotifyTokenSerializer
    
    @action(detail=False, methods=['get'])
    def by_member(self, request):
        member_id = request.query_params.get('member_id')
        if member_id:
            token = SpotifyToken.objects.filter(member__member_id=member_id).first()
            if token:
                serializer = self.get_serializer(token)
                return Response(serializer.data)
        return Response({'error': 'Token not found'}, status=status.HTTP_404_NOT_FOUND)

class TimeZoneViewSet(viewsets.ModelViewSet):
    queryset = TimeZone.objects.all()
    serializer_class = TimezoneSerializer

class MemberTimeZoneMapViewSet(viewsets.ModelViewSet):
    queryset = MemberTimeZoneMap.objects.all()
    serializer_class = TimeMapSerializer

# Spotify OAuth callback view
@method_decorator(csrf_exempt, name='dispatch')
def spotify_oauth_callback(request):
    """
    Handle Spotify OAuth callback and store tokens
    """
    if request.method == 'GET':
        code = request.GET.get('code')
        state = request.GET.get('state')  # Should contain member_id
        
        if not code or not state:
            return HttpResponse('<html><body><h1>Authentication failed!</h1><p>Missing authorization code or state.</p></body></html>', status=400)
        
        try:
            # Exchange code for tokens
            client_id = os.getenv('SPOTIFY_CLIENT_ID')
            client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
            redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
            
            if not all([client_id, client_secret, redirect_uri]):
                return HttpResponse('<html><body><h1>Server configuration error!</h1><p>Missing Spotify credentials.</p></body></html>', status=500)
            
            # Prepare token exchange request
            token_url = 'https://accounts.spotify.com/api/token'
            auth_string = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
            
            headers = {
                'Authorization': f'Basic {auth_string}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri
            }
            
            response = requests.post(token_url, headers=headers, data=data)
            
            if response.status_code == 200:
                token_data = response.json()
                
                # Get or create member
                member, created = Member.objects.get_or_create(member_id=state)
                
                # Calculate expiration time
                expires_in = token_data.get('expires_in', 3600)
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                # Store or update token
                spotify_token, token_created = SpotifyToken.objects.update_or_create(
                    member=member,
                    defaults={
                        'access_token': token_data.get('access_token'),
                        'refresh_token': token_data.get('refresh_token'),
                        'expires_at': expires_at,
                        'scope': token_data.get('scope', '')
                    }
                )
                
                return HttpResponse('<html><body><h1>Authentication successful!</h1><p>You can close this window and return to Discord.</p></body></html>')
            else:
                return HttpResponse('<html><body><h1>Authentication failed!</h1><p>Failed to exchange authorization code for tokens.</p></body></html>', status=400)
                
        except Exception as e:
            return HttpResponse(f'<html><body><h1>Authentication error!</h1><p>Error: {str(e)}</p></body></html>', status=500)
    
    return HttpResponse('<html><body><h1>Method not allowed</h1></body></html>', status=405)
