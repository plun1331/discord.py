from discord.application_commands import ApplicationCommandPermission, Option, Subcommand
from discord.enums import ApplicationCommandOptionType
import discord
from discord.ext import app_commands
import asyncio

client = app_commands.Bot(intents=discord.Intents.all())

command = None

@client.event
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')
    #await client.get_guild(881271010215735316).create_slash_command('testing', description='Testing commands.', options=[Option('test', 'Test option.', ApplicationCommandOptionType.user, required=True)])

token = "NzY2MTU3NDcxMjY5Mzg4MzU5.X4fRvw.bLkX83rBX37usq85IYn1u0uu9Wo"

client.load_extension('ext')

client.run(token)