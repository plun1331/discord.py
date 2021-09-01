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
from ...application_commands import ApplicationCommandPermission, Option, PartialApplicationCommand, Subcommand, SubcommandGroup
from ...enums import ApplicationCommandOptionType, ApplicationCommandPermissionType, ApplicationCommandType, ChannelType
from .context import Context
from ...interactions import Interaction, InteractionType
from ...client import Client
from .cog import Cog
import traceback
        

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

def user_command(
    *,
    name: str,
    default_permission: bool = True,

    guild_ids: List[int] = None,
    **settings
):

    def decorator(func):
        if isinstance(func, Command):
            raise TypeError('Callback is already a command.')
        appcmd = PartialApplicationCommand(name=name, description=None, type=ApplicationCommandType.user, default_permission=default_permission)
        settings['name'] = name
        settings['guild_ids'] = guild_ids
        cmd = Command(func, appcmd, **settings)
        return cmd
    return decorator

def message_command(
    *,
    name: str,
    default_permission: bool = True,

    guild_ids: List[int] = None,
    **settings
):

    def decorator(func):
        if isinstance(func, Command):
            raise TypeError('Callback is already a command.')
        appcmd = PartialApplicationCommand(name=name, description=None, type=ApplicationCommandType.message, default_permission=default_permission)
        settings['name'] = name
        settings['guild_ids'] = guild_ids
        cmd = Command(func, appcmd, **settings)
        return cmd
    return decorator

def permissions(
    *, 
    id: int, 
    type: ApplicationCommandPermissionType, 
    permission: bool):
    """
    Registers a permission for a command.
    Can only be used for guild commands.
    """

    def decorator(func):
        perm = ApplicationCommandPermission(id, type, permission)
        if isinstance(func, Command):
            func.permissions.append(perm)
        else:
            if not hasattr(func, '__permissions__'):
                func.__permissions__ = []

            func.__permissions__.append(perm)

        return func

    return decorator
