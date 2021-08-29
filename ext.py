import discord
from discord.ext import app_commands

class cat(app_commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.slash_command(name='testing', description='balls', guild_ids=[881271010215735316])
    async def testing(self, ctx, *, test: discord.Member):
        await self.bot.sync_commands()

    @app_commands.slash_subcommand(base_command='new', base_description='new command!', name='command', description='new command 2!', guild_ids=[881271010215735316])
    async def new_command(self, ctx):
        await ctx.send('hello!')

def setup(bot):
    bot.add_cog(cat(bot))