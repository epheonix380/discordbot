# Discord Bot #

## Running in Dev Mode ##

# Warning Dev Mode will affect live bot as well #

Runs in Docker (Python 3.9.13 base image, see `Dockerfile`).

Build the image:
```
docker compose build
```
(or `docker build -t discordbot .`)

Get access token from Nyan and put it in a top level `.env` file:
```
TOKEN=<get from nyan>
```

Run dev bot:
```
docker compose up
```
(or `docker run --env-file .env discordbot`)

### Adding a new package ###

Add a pinned line to `requirements.txt`, then rebuild:
```
docker compose build
```
The pip cache mount plus the layered build (system deps -> requirements -> app source)
keeps rebuilds fast even when adding new packages.

## Pushing to Production ##

Push to the github, the CI/CD pipeline will build and deploy the Docker image onto the server.