from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'guilds', views.GuildViewSet)
router.register(r'members', views.MemberViewSet)
router.register(r'channels', views.ChannelViewSet)
router.register(r'guild-activities', views.GuildActivityViewSet)
router.register(r'member-guild-activities', views.MemberGuildActivityViewSet)
router.register(r'weighted-guild-activities', views.WeightedGuildActivityViewSet)
router.register(r'guess-the-hero', views.GuessTheHeroViewSet)
router.register(r'list-of-choices', views.ListOfChoicesViewSet)
router.register(r'items', views.ItemViewSet)
router.register(r'member-reminders', views.MemberReminderViewSet)
router.register(r'member-gym-days', views.MemberGymDayViewSet)
router.register(r'game-versions', views.GameVersionViewSet)
router.register(r'game-subscriptions', views.GameVersionSubscriptionsViewSet)
router.register(r'member-playlists', views.MemberPlaylistViewSet)
router.register(r'playlist-elements', views.PlaylistElementViewSet)
router.register(r'complex-frequencies', views.ComplexFrequecyViewSet)
router.register(r'bot-ignore-channels', views.BotIgnoreChannelsViewSet)
router.register(r'spotify-tokens', views.SpotifyTokenViewSet)
router.register(r'timezones', views.TimeZoneViewSet)
router.register(r'member-timezone-maps', views.MemberTimeZoneMapViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('spotify/callback/', views.spotify_oauth_callback, name='spotify_oauth_callback'),
]
