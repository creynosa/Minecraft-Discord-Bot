import re
from logging import getLogger
from pathlib import Path
from typing import Optional

import discord
import yaml
from discord.ext import commands, tasks

from aws import s3

logger = getLogger("main.locations")


class Locations(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.dataFilepath = str(Path.cwd() / 'data' / 'locations.yaml')
        self.data = self.getData()

    images = {
        'dirtBlock': 'https://cdn.pixabay.com/photo/2013/07/12/19/25/minecraft-154749__480.png',
        'creeper': 'https://i.imgur.com/NipxpY1.jpg',
        'house': 'https://cdn.iconscout.com/icon/free/png-256/house-home-building-infrastructure-real-estate-resident-emoj-symbol-1-30743.png',
        'wheat': 'https://static.wikia.nocookie.net/minecraft_gamepedia/images/c/c0/Wonderful_Wheat_%28MCD%29.png/revision/latest?cb=20210111171738',
        'pearl': "https://static.wikia.nocookie.net/minecraft_gamepedia/images/f/f6/Ender_Pearl_JE3_BE2.png/revision/latest?cb=20200512195721",
    }

    @commands.command()
    async def add(self, ctx, locationType: str, *, name: str):
        user = ctx.author
        userID = user.id
        self.validateUser(user)
        locationData = self.data['users'][userID]['locations']

        try:
            assert locationType.lower() in ('farm', 'home', 'other')
        except AssertionError:
            await ctx.send(embed=self.makeAddInvalidLocationTypeEmbed())
            return

        if locationType == 'home':
            data = locationData['homes']
        elif locationType == 'farm':
            data = locationData['farms']
        elif locationType == 'farm':
            data = locationData['other']
        else:
            data = None

        invalidNames = ('all', 'farms', 'homes', 'other')
        while (nameExists := self.nameExists(name, user)) or (invalidName := name in invalidNames):
            if nameExists:
                message = "That location name already exists. Please enter a new name for this location."
                embed = self.makeEditPromptEmbed(message)
                await ctx.send(embed=embed)

                try:
                    msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                except Exception as e:
                    logger.error(e)
                    await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                    return
                content = msg.content.lower()
                if content == 'cancel':
                    await ctx.send(embed=self.makeAddCancelledEmbed())
                    return
                else:
                    name = msg.content
            elif invalidName:
                message = 'That location name is invalid. Please enter a new name for this location.'
                embed = self.makeEditPromptEmbed(message)
                await ctx.send(embed=embed)

                try:
                    msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                except Exception as e:
                    logger.error(e)
                    await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                    return
                content = msg.content.lower()
                if content == 'cancel':
                    await ctx.send(embed=self.makeAddCancelledEmbed())
                    return
                else:
                    name = msg.content

        coordinateTypeText = """What type of coordinates do you wish to enter?
        
        `1.` Overworld
        `2.` Nether
        `3.` End"""
        embed = self.makeAddPromptEmbed(text=coordinateTypeText)
        await ctx.send(embed=embed)

        while True:
            try:
                msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            except Exception as e:
                logger.error(e)
                await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                return

            content = msg.content.lower()
            if content == 'cancel':
                await ctx.send(embed=self.makeAddCancelledEmbed())
                return
            elif content not in ('1', '2', '3'):
                await ctx.send(embed=self.makeAddInvalidSelection())
            else:
                break

        if content == '1':
            coordType = 'overworld'
        elif content == '2':
            coordType = 'nether'
        elif content == '3':
            coordType = 'end'
        else:
            coordType = None

        coordinateText = """Please enter your coordinates in parentheses. Example: `(-25, 300, 69)`"""
        embed = self.makeAddPromptEmbed(text=coordinateText)
        await ctx.send(embed=embed)

        while True:
            try:
                msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            except Exception as e:
                logger.error(e)
                await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                return

            content = msg.content.lower()
            if content == 'cancel':
                await ctx.send(embed=self.makeAddCancelledEmbed())
                return
            elif not self.areValidCoords(content):
                await ctx.send(embed=self.makeAddInvalidSelection())
            else:
                break

        coordinates = self.extractCoords(content)

        if coordType == 'overworld':
            overworldCoords = coordinates
            netherCoords = self.getNetherCoords(coordinates)
            endCoords = None
        elif coordType == 'nether':
            overworldCoords = self.getOverworldCoords(coordinates)
            netherCoords = coordinates
            endCoords = None
        elif coordType == 'end':
            overworldCoords = None
            netherCoords = None
            endCoords = coordinates
        else:
            overworldCoords = None
            netherCoords = None
            endCoords = None

        data[name] = {
            'overworld': str(overworldCoords),
            'nether': str(netherCoords),
            'end': str(endCoords)
        }
        self.saveData()

        await ctx.send(embed=self.makeAddSuccessfullyAddedEmbed())

    @commands.command()
    async def remove(self, ctx, *, locationName: str) -> None:
        user = ctx.author
        userID = user.id
        self.validateUser(user)
        userData = self.data['users'][userID]['locations']

        if self.locationExists(locationName, user):
            locationType = self.getLocationCategory(locationName, user)
            userData[locationType].pop(locationName)
            self.saveData()

            await ctx.send(embed=self.makeRemoveSuccessEmbed())
        else:
            await ctx.send(embed=self.makeLocationDoesNotExistEmbed())

    @commands.command()
    async def edit(self, ctx, *, locationName: str) -> None:
        user = ctx.author
        userID = user.id
        self.validateUser(user)
        userData = self.data['users'][userID]['locations']

        if self.locationExists(locationName, user):
            locationType = self.getLocationCategory(locationName, user)
            locationData = userData[locationType][locationName]
        else:
            await ctx.send(embed=self.makeLocationDoesNotExistEmbed())

        changePrompt = """What would you like to change?

                `1.` Name
                `2.` Coordinates"""
        embed = self.makeAddPromptEmbed(text=changePrompt)
        await ctx.send(embed=embed)
        while True:
            try:
                msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            except Exception as e:
                logger.error(e)
                await ctx.send(content=f"{ctx.author.mention}", embed=self.makeEditTimeoutEmbed())
                return

            content = msg.content.lower()
            if content == 'cancel':
                await ctx.send(embed=self.makeEditCancelledEmbed())
                return
            elif content not in ('1', '2'):
                await ctx.send(embed=self.makeEditInvalidSelection())
            else:
                break

        if content == '1':
            changePrompt = """Please enter the new name of this location."""
            embed = self.makeEditPromptEmbed(text=changePrompt)
            await ctx.send(embed=embed)

            try:
                msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
            except Exception as e:
                logger.error(e)
                await ctx.send(content=f"{ctx.author.mention}", embed=self.makeEditTimeoutEmbed())
                return
            content = msg.content.lower()
            if content == 'cancel':
                await ctx.send(embed=self.makeEditCancelledEmbed())
                return
            else:
                name = content

            invalidNames = ('all', 'farms', 'homes', 'other')
            while (nameExists := self.nameExists(name, user)) or (invalidName := name in invalidNames):
                if nameExists:
                    message = "That location name already exists. Please enter a new name for this location."
                    embed = self.makeEditPromptEmbed(message)
                    await ctx.send(embed=embed)

                    try:
                        msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                    except Exception as e:
                        logger.error(e)
                        await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                        return
                    content = msg.content.lower()
                    if content == 'cancel':
                        await ctx.send(embed=self.makeAddCancelledEmbed())
                        return
                    else:
                        name = msg.content
                elif invalidName:
                    message = 'That location name is invalid. Please enter a new name for this location.'
                    embed = self.makeEditPromptEmbed(message)
                    await ctx.send(embed=embed)

                    try:
                        msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                    except Exception as e:
                        logger.error(e)
                        await ctx.send(content=f"{ctx.author.mention}", embed=self.makeAddTimeoutEmbed())
                        return
                    content = msg.content.lower()
                    if content == 'cancel':
                        await ctx.send(embed=self.makeAddCancelledEmbed())
                        return
                    else:
                        name = msg.content

            newName = msg.content
            userData[locationType].pop(locationName)
            userData[locationType][newName] = locationData
            self.saveData()

            await ctx.send(embed=self.makeEditNameSuccessEmbed())
        elif content == '2':
            coordinateTypeText = """What type of coordinates do you wish to enter?

                        `1.` Overworld
                        `2.` Nether
                        `3.` End"""
            embed = self.makeEditPromptEmbed(text=coordinateTypeText)
            await ctx.send(embed=embed)

            while True:
                try:
                    msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                except Exception as e:
                    logger.error(e)
                    await ctx.send(content=f"{ctx.author.mention}", embed=self.makeEditTimeoutEmbed())
                    return

                content = msg.content.lower()
                if content == 'cancel':
                    await ctx.send(embed=self.makeEditCancelledEmbed())
                    return
                elif content not in ('1', '2', '3'):
                    await ctx.send(embed=self.makeEditInvalidSelection())
                else:
                    break

            if content == '1':
                coordType = 'overworld'
            elif content == '2':
                coordType = 'nether'
            elif content == '3':
                coordType = 'end'
            else:
                coordType = None

            changePrompt = """Please enter the new coordinates for this location. Example: `(-25, 300, 69)`"""
            embed = self.makeAddPromptEmbed(text=changePrompt)
            await ctx.send(embed=embed)
            while True:
                try:
                    msg = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author, timeout=30)
                except Exception as e:
                    logger.error(e)
                    await ctx.send(content=f"{ctx.author.mention}", embed=self.makeEditTimeoutEmbed())
                    return

                content = msg.content.lower()
                if content == 'cancel':
                    await ctx.send(embed=self.makeEditCancelledEmbed())
                    return
                elif not self.areValidCoords(content):
                    await ctx.send(embed=self.makeEditInvalidSelection())
                else:
                    break

            coordinates = self.extractCoords(content)

            if coordType == 'overworld':
                overworldCoords = coordinates
                netherCoords = self.getNetherCoords(coordinates)
                endCoords = None
            elif coordType == 'nether':
                overworldCoords = self.getOverworldCoords(coordinates)
                netherCoords = coordinates
                endCoords = None
            elif coordType == 'end':
                overworldCoords = None
                netherCoords = None
                endCoords = coordinates
            else:
                overworldCoords = None
                netherCoords = None
                endCoords = None

            locationData['overworld'] = str(overworldCoords)
            locationData['nether'] = str(netherCoords)
            locationData['end'] = str(endCoords)

            self.saveData()

            await ctx.send(embed=self.makeEditCoordinatesSuccessEmbed())

    @commands.command()
    async def view(self, ctx, *, location: str):
        """Command used to view user's own saved locations."""
        user = ctx.author
        self.validateUser(user)

        if location == 'all':
            await ctx.send(embed=self.makeViewAllEmbed(user))
        elif location == 'farms':
            await ctx.send(embed=self.makeViewFarmsEmbed(user))
        elif location == 'homes':
            await ctx.send(embed=self.makeViewHomesEmbed(user))
        elif location == 'other':
            await ctx.send(embed=self.makeViewOtherEmbed(user))
        else:
            try:
                await ctx.send(embed=self.makeViewEmbed(user, location))
            except ValueError:
                await ctx.send(embed=self.makeLocationDoesNotExistEmbed())

    @commands.Cog.listener()
    async def on_ready(self):
        self.downloadFromAWS()

        self.uploadData.start()

    @tasks.loop(hours=1)
    async def uploadData(self):
        self.uploadToAWS()

    def makeAddPromptEmbed(self, text: str) -> discord.Embed:
        """Generates an embed containing specified text and title."""
        embed = discord.Embed(color=0x52A435, description=text)
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])
        embed.set_footer(text='Please enter a response within 30 seconds. Type "cancel" to cancel at any time.')

        return embed

    def makeAddInvalidLocationTypeEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user of an invalid location type."""
        embed = discord.Embed(color=0x52A435,
                              description='Invalid location type. Please try again.'
                                          '\n\n Examples: `*add farm Slime Farm`, `*add home Main`, '
                                          '`*add other Stronghold`')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeAddTimeoutEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user they were timed out."""
        embed = discord.Embed(color=0x52A435, description='You were timed out. Please try again.')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeAddCancelledEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that their command was successfully cancelled."""
        embed = discord.Embed(color=0x52A435, description='Cancelled. Have a nice day!')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeAddInvalidSelection(self) -> discord.Embed:
        """Generates an embed notifying the user of invalid input."""
        embed = discord.Embed(color=0x52A435, description='Invalid input. Please try again.')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])
        embed.set_footer(text='Please enter a response within 30 seconds. Type "cancel" to cancel at any time.')

        return embed

    def makeAddSuccessfullyAddedEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that the location was successfully added."""
        embed = discord.Embed(color=0x52A435, description='Location added!')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeViewFarmsEmbed(self, user: discord.User) -> discord.Embed:
        farmData = self.data['users'][user.id]['locations']['farms']

        if farmData == {}:
            farmNames = 'None'
        else:
            farmNames = ''
            for name, _ in farmData.items():
                farmNames += name + '\n'

        embed = discord.Embed(color=0x52A435)
        embed.set_author(name=f"{user.name}'s Farms", icon_url=self.images['dirtBlock'])
        embed.add_field(name='Name', value=farmNames)
        embed.set_footer(text='To view coordinates, please use: !view <name>')

        return embed

    def makeViewHomesEmbed(self, user: discord.User) -> discord.Embed:
        homeData = self.data['users'][user.id]['locations']['homes']

        if homeData == {}:
            homeNames = 'None'
        else:
            homeNames = ''
            for name, _ in homeData.items():
                homeNames += name + '\n'

        embed = discord.Embed(color=0x52A435)
        embed.set_author(name=f"{user.name}'s Homes", icon_url=self.images['dirtBlock'])
        embed.add_field(name='Name', value=homeNames)
        embed.set_footer(text='To view coordinates, please use: !view <name>')

        return embed

    def makeViewOtherEmbed(self, user: discord.User) -> discord.Embed:
        otherData = self.data['users'][user.id]['locations']['other']

        if otherData == {}:
            otherNames = 'None'
        else:
            otherNames = ''
            for name, _ in otherData.items():
                otherNames += name + '\n'

        embed = discord.Embed(color=0x52A435)
        embed.set_author(name=f"{user.name}'s Other Locations", icon_url=self.images['dirtBlock'])
        embed.add_field(name='Name', value=otherNames)
        embed.set_footer(text='To view coordinates, please use: !view <name>')

        return embed

    def makeViewAllEmbed(self, user: discord.User) -> discord.Embed:
        """Generates an embed displaying all of a user's saved locations."""
        homeData = self.data['users'][user.id]['locations']['homes']
        farmsData = self.data['users'][user.id]['locations']['farms']
        otherData = self.data['users'][user.id]['locations']['other']

        if otherData == {}:
            otherNames = 'None'
        else:
            otherNames = ''
            for name, _ in otherData.items():
                otherNames += name + '\n'

        if homeData == {}:
            homeNames = 'None'
        else:
            homeNames = ''
            for name, _ in homeData.items():
                homeNames += name + '\n'

        if farmsData == {}:
            farmNames = 'None'
        else:
            farmNames = ''
            for name, _ in farmsData.items():
                farmNames += name + '\n'

        embed = discord.Embed(color=0x52A435)
        embed.set_author(name=f"{user.name}'s Locations", icon_url=self.images['dirtBlock'])
        embed.add_field(name='Homes', value=homeNames)
        embed.add_field(name='Farms', value=farmNames)
        embed.add_field(name='Other', value=otherNames)
        embed.set_footer(text='To view coordinates, please use: !view <name>')

        return embed

    def makeViewEmbed(self, user: discord.User, locationName: str) -> discord.Embed:
        locationData = self.getLocationData(locationName, user)
        overworldCoords = locationData['overworld']
        netherCoords = locationData['nether']
        endCoords = locationData['end']

        embed = discord.Embed(color=0x52A435)
        embed.set_author(name=f"Coordinates for {locationName}", icon_url=self.images['dirtBlock'])
        embed.add_field(name='Overworld', value=overworldCoords)
        embed.add_field(name='Nether', value=netherCoords)
        embed.add_field(name='End', value=endCoords)

        return embed

    def makeRemoveSuccessEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that the location was successfully removed."""
        embed = discord.Embed(color=0x52A435, description='Location has been removed!')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeEditInvalidSelection(self) -> discord.Embed:
        """Generates an embed notifying the user of invalid input."""
        embed = discord.Embed(color=0x52A435, description='Invalid input. Please try again.')
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])
        embed.set_footer(text='Please enter a response within 30 seconds. Type "cancel" to cancel at any time.')

        return embed

    def makeEditCancelledEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that their command was successfully cancelled."""
        embed = discord.Embed(color=0x52A435, description='Cancelled. Have a nice day!')
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeEditTimeoutEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user they were timed out."""
        embed = discord.Embed(color=0x52A435, description='You were timed out. Please try again.')
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeEditPromptEmbed(self, text: str) -> discord.Embed:
        """Generates an embed containing specified text and title."""
        embed = discord.Embed(color=0x52A435, description=text)
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])
        embed.set_footer(text='Please enter a response within 30 seconds. Type "cancel" to cancel at any time.')

        return embed

    def makeLocationDoesNotExistEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user of a non-existent location."""
        embed = discord.Embed(color=0x52A435,
                              description='That location does not exist. Please try again and ensure that the '
                                          'capitalization '
                                          'is correct.')
        embed.set_author(name='Add Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeEditNameSuccessEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that the location's name was successfully changed."""
        embed = discord.Embed(color=0x52A435, description="The name for this location has been changed!")
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])

        return embed

    def makeEditCoordinatesSuccessEmbed(self) -> discord.Embed:
        """Generates an embed notifying the user that the location's coordinates were successfully changed."""
        embed = discord.Embed(color=0x52A435, description="The coordinates for this location has been changed!")
        embed.set_author(name='Edit Location', icon_url=self.images['dirtBlock'])

        return embed

    @staticmethod
    def areValidCoords(coordinates: str) -> bool:
        """Determines if the given coordinates are in the proper format."""
        validCoordRegex = re.compile(r"^\(\s*(-?\d*)\s*,\s*(-?\d*)\s*,\s*(-?\d*)\s*\)$")
        match = re.search(validCoordRegex, coordinates)
        if match:
            return True
        else:
            return False

    @staticmethod
    def extractCoords(coordinates: str) -> tuple[int, int, int]:
        """Extracts and returns a location's coordinates from a string."""
        validCoordRegex = re.compile(r"^\(\s*(-?\d*)\s*,\s*(-?\d*)\s*,\s*(-?\d*)\s*\)$")
        match = re.search(validCoordRegex, coordinates)
        x = int(match.group(1))
        z = int(match.group(2))
        y = int(match.group(3))

        return x, z, y

    @staticmethod
    def getOverworldCoords(netherCoordinates: tuple) -> tuple:
        """Converts a set of nether coordinates to overworld coordinates."""
        x, z, y = (coord * 8 for coord in netherCoordinates)
        return x, z, y

    @staticmethod
    def getNetherCoords(overworldCoordinates: tuple) -> tuple:
        """Converts a set of overworld coordinates to nether coordinates."""
        x, z, y = (round(coord / 8) for coord in overworldCoordinates)
        return x, z, y

    def validateUser(self, user: discord.User):
        try:
            assert user.id in self.data['users']
        except AssertionError:
            self.data['users'][user.id] = {
                'locations': {
                    'homes': {},
                    'farms': {},
                    'other': {}
                }
            }

    def nameExists(self, locationName: str, user: discord.User) -> bool:
        """Determines if the location name already exists in a location data set."""
        userLocationData = self.data['users'][user.id]['locations']

        for locationCategory, categoryData in userLocationData.items():
            names = categoryData.keys()
            if locationName in names:
                return True
        return False

    def locationExists(self, locationName: str, user: discord.User) -> bool:
        userData = self.data['users'][user.id]['locations']
        for locationCategory, locationData in userData.items():
            names = list(locationData.keys())
            if locationName in names:
                return True
        return False

    def getLocationCategory(self, locationName: str, user: discord.User) -> Optional[str]:
        userData = self.data['users'][user.id]['locations']
        for locationCategory, locationData in userData.items():
            names = list(locationData.keys())
            if locationName in names:
                return locationCategory
        return None

    def getLocationData(self, locationName: str, user: discord.User) -> dict:
        userData = self.data['users'][user.id]['locations']

        homeData = userData['homes']
        if locationName in list(homeData.keys()):
            return homeData[locationName]

        farmData = userData['farms']
        if locationName in list(farmData.keys()):
            return farmData[locationName]

        otherData = userData['other']
        if locationName in list(otherData.keys()):
            return otherData[locationName]

        raise ValueError

    def getData(self) -> dict:
        """Returns the saved location data for all users."""
        with open(self.dataFilepath, 'r') as f:
            config = yaml.safe_load(f)
        return config

    def saveData(self) -> None:
        """Saves the data to the location data file."""
        with open(self.dataFilepath, 'w') as f:
            yaml.dump(self.data, f)

    def downloadFromAWS(self) -> None:
        """Downloads and saves the location data from AWS."""
        s3.download_file('minecraft-bot', 'locations.yaml', self.dataFilepath)

    def uploadToAWS(self) -> None:
        """Uploads the saved location data to AWS."""
        s3.upload_file(self.dataFilepath, 'minecraft-bot', 'locations.yaml')


def setup(bot):
    bot.add_cog(Locations(bot))
