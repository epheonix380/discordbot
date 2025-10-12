#!/bin/bash
# Test script to verify Docker builds work with Python 3.13 and librespot-python

echo "Testing Docker builds with Python 3.13 and librespot-python..."

# Test bot Dockerfile
echo "Building bot Docker image..."
docker build -f Dockerfile.bot -t discord-bot-test .

if [ $? -eq 0 ]; then
    echo "✅ Bot Docker build successful"
else
    echo "❌ Bot Docker build failed"
    exit 1
fi

# Test API Dockerfile
echo "Building API Docker image..."
docker build -f Dockerfile.api -t discord-api-test .

if [ $? -eq 0 ]; then
    echo "✅ API Docker build successful"
else
    echo "❌ API Docker build failed"
    exit 1
fi

echo "🎉 All Docker builds completed successfully!"
echo "You can now run: docker-compose up -d"
