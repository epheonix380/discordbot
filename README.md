# Discord Bot #

## Running in Dev Mode ##

# Warning Dev Mode will affect live bot as well #

Python version 3.9
Install Dependencies:
```
pipenv shell
pipenv install
```
Get access token from Nyan and put it in top level .env file:
```
TOKEN=<get from nyan>
```
Run dev bot:
```
python main.py
```

## Pushing to Production ##

Push to the github the CI/CD pipeline will autoload it onto the server