import asyncio
import discord
import functools
import inspect
from .commands import Command
from .errors import CheckAnyFailure, CheckFailure, CommandNotFound, CommandError
from ...role import Role
from ...channel import _threaded_guild_channel_factory
from ...errors import InvalidData
from ...user import User
from ...member import Member
from typing import Any, Callable, Dict, List, Union
from ...application_commands import Option, PartialApplicationCommand, Subcommand, SubcommandGroup
from ...enums import ApplicationCommandOptionType, ApplicationCommandType, ChannelType
from .context import Context
from ...interactions import Interaction, InteractionType
from ...client import Client
from .cog import Cog
import traceback
        

def slash_subcommand(
    *,
    base_command: str,
    base_description: str,
    base_default_permission: bool = True,

    subcommand_group=None,
    subcommand_group_description: str = None,

    name: str,
    description: str,
    options: List[Option] = None,

    guild_ids: Union[List[int], int] = None,
    **settings
):

    def decorator(func):
        if isinstance(func, Command):
            raise TypeError('Callback is already a command.')
        if subcommand_group is not None:
            _options = [SubcommandGroup(name=subcommand_group, description=subcommand_group_description, options=[Subcommand(name, description, options=options)])]
        else:
            _options = [Subcommand(name, description, options=options)]
        appcmd = PartialApplicationCommand(name=base_command, description=base_description, type=ApplicationCommandType.chat_input, default_permission=base_default_permission,
                                        options=_options)
        settings['name'] = base_command + ' ' + (subcommand_group + ' ' if subcommand_group is not None else '') + name
        settings['guild_ids'] = guild_ids
        cmd = Command(func, appcmd, **settings)
        return cmd
    return decorator

def slash_command(
    *,
    name: str,
    description: str,
    options: List[Option] = None,
    default_permission: bool = True,

    guild_ids: List[int] = None,
    **settings
):

    def decorator(func):
        if isinstance(func, Command):
            raise TypeError('Callback is already a command.')
        appcmd = PartialApplicationCommand(name=name, description=description, type=ApplicationCommandType.chat_input, default_permission=default_permission,
                                        options=options)
        settings['name'] = name
        settings['guild_ids'] = guild_ids
        cmd = Command(func, appcmd, **settings)
        return cmd
    return decorator
