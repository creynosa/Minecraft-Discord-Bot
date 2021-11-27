import logging
import logging.config
import os
from pathlib import Path

import discord
import yaml
from discord.ext import commands
from dotenv import load_dotenv


def loadEnv() -> None:
    """Reads and loads the environment variables specified in the project directory."""
    load_dotenv('.env')


def getLoggingConfig() -> dict:
    """Returns the logging configurations from the project directory."""
    configPath = str(Path.cwd() / 'configurations' / 'logging.yaml')
    with open(configPath, "r") as f:
        loggingConfig = yaml.safe_load(f)
    return loggingConfig


def createLogger() -> logging.Logger:
    """Returns a logger created using the project's logging configuration file."""
    loggingConfig = getLoggingConfig()
    logging.config.dictConfig(loggingConfig)
    projectLogger = logging.getLogger("main")

    return projectLogger


def getIntents() -> discord.Intents:
    """Returns all user-specified intents."""
    intents = discord.Intents.all()

    return intents


def getBotToken() -> str:
    """Returns the main bot token."""
    return os.environ["BOT_TOKEN"]


def createBot() -> commands.Bot:
    """Constructs and returns the main discord bot."""
    return commands.Bot(command_prefix="*", intents=getIntents())


def initializeBot() -> commands.Bot:
    """Initializes the main discord bot."""
    logger.info("Initializing main bot...")

    discordBot = createBot()
    discordBot.remove_command("help")

    logger.info("Main bot initialized!")

    return discordBot


def getModules() -> list[str]:
    """Returns the module names along with the .py extension for all the main cogs."""
    cogModules = os.listdir("cogs")
    return cogModules


def getModulesInDotFormat() -> list[str]:
    """Returns the filepaths of all the main cogs to be loaded."""
    cogModules = getModules()
    formattedModules = [
        f"cogs.{filename[:-3]}"
        for filename in cogModules
        if filename != "__init__.py" and filename.endswith(".py")
    ]

    return formattedModules


def loadModules(discordBot: commands.Bot) -> None:
    """Loads specified guild modules from the cog directory of the project onto the bot for testing."""
    cogFiles = getModulesInDotFormat()

    logger.info(f"Loading cogs: {cogFiles}")
    for filename in cogFiles:
        discordBot.load_extension(filename)
    logger.info(f"Cogs loaded!")


if __name__ == "__main__":
    loadEnv()
    logger = createLogger()

    token = getBotToken()
    bot = initializeBot()
    loadModules(bot)


    @bot.event
    async def on_ready():
        """Print a console message when the bot is ready and active."""
        logger.info("Bot successfully started!")


    @bot.event
    async def on_message(message: discord.Message):
        """Executes certain code blocks upon a message being sent."""
        if message.author == bot.user:
            return

        await bot.process_commands(message)


    bot.run(token)
