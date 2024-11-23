release: python3 manage.py migrate
release: cd spotify-headless-client && npm install
release: cd spotify-headless-client && npx puppeteer browsers install chrome
worker: python3 main.py
spotify: cd spotify-headless-client && npm start