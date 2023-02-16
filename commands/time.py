import re
import pytz
import datetime
from helpers.timeStrore import getDefaultTimezone, setDefaultTimezone, addTimezone, removeTimezone, getTimezones, getFormat, setFormat

async def timeHandler(message):
    instruction = str(message.content).strip().split(" ")
    timeFormat = await getFormat(message.author.id)
    firstInstruction = "ball"
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
            content += f"Time in {cityName} is " + convertedTime.strftime(timeFormat)+ "\n"
        if (content == ""):
            content = "We found no timezones for your user, please use ,time add <City name> to add timezones"
        await message.channel.send(content)
        

    elif (len(instruction) >= 4 and instruction[1] == "convert"):
        #,time convert 12:00 Singapore to Bangkok
        userInAll = re.search("\d{18}",message.content)
        newContent = " ".join(instruction[2::])
        timeStringRaw = re.search("\d?\d\:\d\d(am)?(pm)?",newContent)
        if (timeStringRaw is None):
            content = "Time not found please specify a time using : between the hours and mintues like 13:00 or 01:00pm"
            return await message.channel.send(content)
        if ("to" in newContent):
            cities = newContent.split(" to ")
            cityToConvertTo = "_".join(cities[1].split(" "))
            toCode = ""
            fromCode = ""
            timeString =  timeStringRaw.group(0)
            cityToConvertFrom = "_".join(re.sub("\d?\d\:\d\d(am)?(pm)?","",cities[0]).strip().split(" "))
            from pytz import all_timezones
            for timezone in all_timezones:
                if cityToConvertTo.lower() in timezone.lower():
                    toCode = timezone
                if cityToConvertFrom.lower() in timezone.lower():
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
            content = f"When it is {fromTime.strftime(timeFormat)} in {cityToConvertFrom} it will be " + toTime.strftime(timeFormat) + " in " + cityToConvertTo
            await message.channel.send(content)
        else:
            cityToConvertFrom = await getDefaultTimezone(message.author.id)
            if (cityToConvertFrom is None):
                content = "No default timezone found:\nThis version of the command requires you to set a default timezone if you do not want to set one you can use this command instead:\n```,time convert <time> <from-city-name> to <to-city-name>```\nOr you can set your default timezone using this command:\n```,time default <city-name>```"
                return await message.channel.send(content)
            timeString =  timeStringRaw.group(0)
            cityToConvertTo = "_".join(re.sub("\d?\d\:\d\d(am)?(pm)?","",newContent).strip().split(" "))
            from pytz import all_timezones
            for timezone in all_timezones:
                if cityToConvertTo.lower() in timezone.lower():
                    toCode = timezone
                if cityToConvertFrom.lower() in timezone.lower():
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
            content = f"When it is {fromTime.strftime(timeFormat)} in {fromCity} it will be " + toTime.strftime(timeFormat) + " in " + cityToConvertTo
            await message.channel.send(content)
            
            
        
    else:
        #,time Bangkok
        # But also ,time New York
        # But also ,time noneSenseValueHere
        firstInstruction = re.search("\d{18}",instruction[1])
        if (instruction[1] == "default"):
            if (len(instruction)==2):
                default = await getDefaultTimezone(message.author.id)
                if default is None:
                    default = "No defaults found, please use ,time default <City name> to set a default"
                await message.channel.send(default)
            else:
                city = "_".join(instruction[2::]).strip()
                tempTimeZone = ""
                from pytz import all_timezones
                for timezone in all_timezones:
                    if city.lower() in timezone.lower():
                        tempTimeZone = timezone
                        timeZone = pytz.timezone(timezone)
                await setDefaultTimezone(message.author.id, tempTimeZone)  
        elif (instruction[1] == "add"):
            city = "_".join(instruction[2::]).strip()
            tempTimeZone = ""
            from pytz import all_timezones
            for timezone in all_timezones:
                if city.lower() in timezone.lower():
                    tempTimeZone = timezone
                    timeZone = pytz.timezone(timezone)
            created = await addTimezone(message.author.id, tempTimeZone)  
            if (created):
                await message.channel.send("Added!")
            else:
                await message.channel.send("There was an error")
        elif (instruction[1] == "remove"):
            city = "_".join(instruction[2::]).strip()
            tempTimeZone = ""
            from pytz import all_timezones
            for timezone in all_timezones:
                if city.lower() in timezone.lower():
                    tempTimeZone = timezone
                    timeZone = pytz.timezone(timezone)
            created = await removeTimezone(message.author.id, tempTimeZone)  
            if (created):
                await message.channel.send("Removed!")
            else:
                await message.channel.send("There was an error")
        elif instruction[1] == "format":
            if (len(instruction)==2):
                content = """Add a format by using ,time format <format> command!
        Here are some formats you can use:\n
            %H:%M is a normal 24hr clock eg. 15:34\n
            %I:%M %p is a normal 12hr clock eg. 03:34pm\n
            %Y is the full year eg. 2020\n
            %y is the short year eg. 20\n
            %m is the month in digits eg. 12\n 
            %b is the short month in letters eg. Dec\n
            %B is the long month in letters eg. December\n
            %d is the date eg. 04\n
            %A is the long day of the week eg. Tuesday\n
            %a is the short day of the week eg. Tue\n\n
            The default example is %H:%M on %d-%m-%Y
            You can always use ,time format default
            to get back to the default time format\n
            Here is the reference: https://www.w3schools.com/python/python_datetime.asp#The-strftime()-Method
                                """
                await message.channel.send(content)
            elif (instruction[2] == "default"):
                await setFormat(message.author.id,"%H:%M on %d-%m-%Y")
                await message.channel.send("Success!")
            else:
                format = " ".join(instruction[2::]).strip()
                await setFormat(message.author.id,format)
                timeZone = pytz.timezone("America/Vancouver")
                convertedTime = datetime.datetime.now().astimezone(timeZone)
                content = "Time messages will now be send like this:\n"
                content += f"Time in Vancouver is " + convertedTime.strftime(format)
                await message.channel.send(content)


        elif (firstInstruction is not None and firstInstruction.group(0) != ""):
            uid = firstInstruction.group(0)
            timezone = await getDefaultTimezone(uid)
            content = ""
            if timezone is not None:
                timeZone = pytz.timezone(timezone)
                convertedTime = datetime.datetime.now().astimezone(timeZone)
                content = f"Time for <@___REPLACE___STRING___> is " + convertedTime.strftime(timeFormat)
            else:
                content = f"User <@___REPLACE___STRING___> does not have a default timezone set"
            sentMessage = await message.channel.send(content)
            await sentMessage.edit(content=re.sub("\_\_\_REPLACE\_\_\_STRING\_\_\_",str(uid),sentMessage.content))

        else:
            timeZone = pytz.utc
            city = "_".join(instruction[1::]).strip()
            from pytz import all_timezones
            for timezone in all_timezones:
                if city.lower() in timezone.lower():
                    timeZone = pytz.timezone(timezone)
            convertedTime = datetime.datetime.now().astimezone(timeZone)
            content = f"Time in {city} is " + convertedTime.strftime(timeFormat)
            await message.channel.send(content)
    await message.delete()

        
    
