import datetime

def getTimeFromString(timeString:str):
    hour = int(timeString.split(":")[0])
    minute = int(timeString.split(":")[1][0:2])
    if (len(timeString.split(":")[1])==4 and timeString.split(":")[1][2:4].lower()=="pm"):
        hour = (hour + 12)%24

    return datetime.time(hour=hour, minute=minute)