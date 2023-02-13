import re
import pytz
import datetime
from helpers.timeStrore import getDefaultTimezone, setDefaultTimezone, addTimezone, removeTimezone, getTimezones

async def timeHandler(message):
    instruction = str(message.content).strip().split(" ")
    if (len(instruction) == 1):
        #,time
        content = ""
        timezones = await getTimezones(message.author.id)
        for timezone in timezones:
            if (timezone['time_zone'] == ""):
                continue
            timeZone = pytz.timezone(timezone['time_zone'])
            convertedTime = datetime.datetime.now().astimezone(timeZone)
            cityName = timezone['time_zone']
            if ("/" in timezone['time_zone']):
                cityName = timezone['time_zone'].split('/')[1]
            content += f"Time in {cityName} is " + convertedTime.strftime("%H:%M") + " on " + convertedTime.strftime("%d-%m-%Y") + "\n"
        if (content == ""):
            content = "We found no timezones for your user, please use ,time add <City name> to add timezones"
        await message.channel.send(content)
        

    elif (len(instruction) >= 4 and instruction[1] == "convert"):
        #,time convert 12:00 Singapore to Bangkok
        
        newContent = " ".join(instruction[2::])
        if ("to" in newContent):
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
            hour = int(timeString.split(":")[0])
            minute = int(timeString.split(":")[1][0:2])
            if (len(timeString.split(":")[1])==4 and timeString.split(":")[1][2:4].lower()=="pm"):
                hour = (hour + 12)%24
            fromTimeZone = pytz.timezone(fromCode)
            toTimeZone = pytz.timezone(toCode)
            today = datetime.datetime.now(tz=fromTimeZone)
            fromTime = fromTimeZone.localize(datetime.datetime(year=today.year, month=today.month, day=today.day, hour=hour, minute=minute))
            toTime = fromTime.astimezone(toTimeZone)
            content = f"When it is {timeString} in {cityToConvertFrom} it will be " + toTime.strftime("%H:%M") + " in " + cityToConvertTo
            await message.channel.send(content)
        else:
            cityToConvertFrom = await getDefaultTimezone(message.author.id)
            if (cityToConvertFrom is None):
                content = "No default timezone found:\nThis version of the command requires you to set a default timezone if you do not want to set one you can use this command instead:\n```,time convert <time> <from-city-name> to <to-city-name>```\nOr you can set your default timezone using this command:\n```,time default <city-name>```"
                return await message.channel.send(content)
            timeString =  re.match("\d?\d\:\d\d(am)?(pm)?",newContent).group(0)
            cityToConvertTo = re.sub("\d?\d\:\d\d(am)?(pm)?","",newContent).strip()
            from pytz import all_timezones
            for timezone in all_timezones:
                if cityToConvertTo in timezone:
                    toCode = timezone
                if cityToConvertFrom in timezone:
                    fromCode = timezone
            hour = int(timeString.split(":")[0])
            minute = int(timeString.split(":")[1][0:2])
            if (len(timeString.split(":")[1])==4 and timeString.split(":")[1][2:4].lower()=="pm"):
                hour = (hour + 12)%24
            fromTimeZone = pytz.timezone(fromCode)
            toTimeZone = pytz.timezone(toCode)
            today = datetime.datetime.now(tz=fromTimeZone)
            fromTime = fromTimeZone.localize(datetime.datetime(year=today.year, month=today.month, day=today.day, hour=hour, minute=minute))
            toTime = fromTime.astimezone(toTimeZone)
            fromCity = cityToConvertFrom.split("/")[1]
            content = f"When it is {timeString} in {fromCity} it will be " + toTime.strftime("%H:%M") + " in " + cityToConvertTo
            await message.channel.send(content)
            
            
        
    else:
        #,time Bangkok
        # But also ,time New York
        # But also ,time noneSenseValueHere
        if (instruction[1] == "default"):
            if (len(instruction)==2):
                default = await getDefaultTimezone(message.author.id)
                if default is None:
                    default = "No defaults found, please use ,time default <City name> to set a default"
                await message.channel.send(default)
            else:
                city = "".join(instruction[2::]).strip()
                tempTimeZone = ""
                from pytz import all_timezones
                for timezone in all_timezones:
                    if city in timezone:
                        tempTimeZone = timezone
                        timeZone = pytz.timezone(timezone)
                await setDefaultTimezone(message.author.id, tempTimeZone)  
        elif (instruction[1] == "add"):
            city = "".join(instruction[2::]).strip()
            tempTimeZone = ""
            from pytz import all_timezones
            for timezone in all_timezones:
                if city in timezone:
                    tempTimeZone = timezone
                    timeZone = pytz.timezone(timezone)
            created = await addTimezone(message.author.id, tempTimeZone)  
            if (created):
                await message.channel.send("Added!")
            else:
                await message.channel.send("There was an error")
        elif (instruction[1] == "remove"):
            city = "".join(instruction[2::]).strip()
            tempTimeZone = ""
            from pytz import all_timezones
            for timezone in all_timezones:
                if city in timezone:
                    tempTimeZone = timezone
                    timeZone = pytz.timezone(timezone)
            created = await removeTimezone(message.author.id, tempTimeZone)  
            if (created):
                await message.channel.send("Removed!")
            else:
                await message.channel.send("There was an error")
        else:
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

        
    
