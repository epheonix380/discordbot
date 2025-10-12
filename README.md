# Discord Bot with Django REST API and Spotify Integration

This Discord bot has been migrated to use a Django REST Framework API server for database operations and includes Spotify integration using librespot for music playback.

## Architecture

- **Discord Bot** (`main.py`): Handles Discord interactions and communicates with the API server
- **Django REST API** (`api_server.py`): Handles all database operations via REST endpoints
- **Spotify Integration**: OAuth flow and librespot for Spotify Connect functionality
- **Python 3.13**: Uses latest Python features and asyncio improvements

## Features

- All existing Discord bot functionality (guild management, activity tracking, etc.)
- Spotify OAuth authentication
- Spotify Connect device integration
- Music playback controls via Discord commands
- RESTful API for all database operations
- Docker containerization support

## Setup

### 1. Environment Configuration

Copy `env.example` to `.env` and configure:

```bash
cp env.example .env
```

Required environment variables:
- `TOKEN`: Your Discord bot token
- `SPOTIFY_CLIENT_ID`: Spotify app client ID
- `SPOTIFY_CLIENT_SECRET`: Spotify app client secret
- `SPOTIFY_REDIRECT_URI`: OAuth callback URL (e.g., `http://localhost:8000/spotify/callback/`)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** `librespot-python` is installed directly from GitHub as it's not available on PyPI:
```bash
pip install git+https://github.com/kokarare1212/librespot-python.git
```

**Important:** `librespot-python` requires `protobuf==3.20.1`. This version is pinned in the requirements files to prevent conflicts with newer protobuf versions.

### 3. Database Setup

Run migrations:
```bash
python manage.py migrate
```

### 4. Running the Services

#### Option A: Separate Processes (Development)

Terminal 1 - Start Django API server:
```bash
python api_server.py
```

Terminal 2 - Start Discord bot:
```bash
python main.py
```

#### Option B: Docker (Production)

```bash
docker-compose up -d
```

## API Endpoints

The Django REST API provides endpoints for all bot functionality:

- `/api/guilds/` - Guild management
- `/api/members/` - Member management
- `/api/guild-activities/` - Activity tracking
- `/api/spotify-tokens/` - Spotify token management
- `/spotify/callback/` - Spotify OAuth callback

## Spotify Commands

- `!spotify_connect` - Connect your Spotify account
- `!spotify_disconnect` - Disconnect your Spotify account
- `!spotify_status` - Check connection status
- `!spotify_play [query]` - Play music from Spotify
- `!spotify_pause` - Pause playback
- `!spotify_stop` - Stop playback and disconnect
- `!spotify_now` - Show currently playing track

## Spotify Setup

1. Create a Spotify app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Add redirect URI: `http://your-domain:8000/spotify/callback/`
3. Copy client ID and secret to environment variables
4. Users can connect their accounts using `!spotify_connect`

## Docker Deployment

### Production Deployment

The `docker-compose.yml` file sets up:
- PostgreSQL database with health checks
- Django REST API server with health checks
- Discord bot with dependency management
- Internal networking for secure communication
- Virtual environments for better isolation
- Separate dependency files for optimized builds

Only the API server port (8000) is exposed externally for OAuth callbacks.

**Deploy with:**
```bash
docker-compose up -d
```

### Development Deployment

Use `docker-compose.dev.yml` for development:
- Source code mounted as volumes for live reloading
- Development database with exposed port
- Debug mode enabled
- Simplified configuration

**Deploy with:**
```bash
docker-compose -f docker-compose.dev.yml up -d
```

### Docker Features

- **Python 3.13**: Latest Python version with improved asyncio performance
- **Virtual Environments**: Each container uses its own Python virtual environment
- **Optimized Dependencies**: Separate requirements files for bot and API
- **Health Checks**: Services wait for dependencies to be healthy
- **Build Caching**: Optimized Docker builds with BuildKit
- **Security**: Non-root users and minimal attack surface

## Migration Notes

The bot has been migrated from direct Django ORM access to REST API calls:
- All helper functions now use the `api_client.py` module
- Database operations are handled by the Django REST API
- The bot communicates with the API server via HTTP requests
- Spotify tokens are stored securely in the database

## Development

- API server runs on `http://localhost:8000`
- Bot connects to API server via `DJANGO_API_URL` environment variable
- CORS is configured for development (restrict in production)
- All API endpoints are documented via Django REST Framework browsable API