import re
import pytz
import datetime

async def timeHandler(message):
    instruction = str(message.content).strip().split(" ")
    if (False and len(instruction) == 1):
        #,time
        print("we are working on this")
    elif (False and len(instruction) >= 5 and instruction[1] == "convert"):
        #,time convert 12:00 Singapore to Bangkok
        
        newContent = "".join(instruction[2::])
        cities = newContent.split(" to ")
        cityToConvertTo = cities[1]
        toCode = ""
        fromCode = ""
        timeString =  re.match("\d?\d\:\d\d(am)?(pm)?",cities[0]).group(0)
        cityToConvertFrom = re.sub("\d?\d\:\d\d(am)?(pm)?","",cities[0]).strip()
        from pytz import all_timezones
        for timezone in all_timezones:
            if cityToConvertTo in timezone:
                toCode = timezone
            if cityToConvertFrom in timezone:
                fromCode = timezone
        
        
    else:
        #,time Bangkok
        # But also ,time New York
        # But also ,time noneSenseValueHere
        timeZone = pytz.utc
        city = "".join(instruction[1::]).strip()
        from pytz import all_timezones
        for timezone in all_timezones:
            if city in timezone:
                timeZone = pytz.timezone(timezone)
        convertedTime = datetime.datetime.now().astimezone(timeZone)
        content = f"Time in {city} is " + convertedTime.strftime("%H:%M") + " on " + convertedTime.strftime("%d-%m-%Y")
        await message.channel.send(content)
    
    await message.delete()

        
    
