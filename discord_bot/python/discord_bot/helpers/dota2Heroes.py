import requests


def getDota2HeroesList():
    response = requests.get("https://api.opendota.com/api/heroes")
    heroes = response.json()
    hero_names = []
    for hero in heroes:
        hero_names.append(hero["localized_name"])
    return hero_names

def getHeroAttr(hero_name):
    response = requests.get("https://api.opendota.com/api/heroes")
    heroes = response.json()
    for hero in heroes:
        if hero["localized_name"] == hero_name:
            return hero["primary_attr"]
    return None
        
def getHeroAttack(hero_name):
    response = requests.get("https://api.opendota.com/api/heroes")
    heroes = response.json()
    for hero in heroes:
        if hero["localized_name"] == hero_name:
            return hero["attack_type"]
    return None

def getHeroLegs(hero_name):
    response = requests.get("https://api.opendota.com/api/heroes")
    heroes = response.json()
    for hero in heroes:
        if hero["localized_name"] == hero_name:
            return hero["legs"]
    return None
