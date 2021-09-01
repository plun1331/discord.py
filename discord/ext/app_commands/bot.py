import asyncio
from discord.message import Message
from discord.application_commands import ApplicationCommand
import json
import discord
from .commands import Command
from .errors import CommandNotFound, CommandError, CommandRegistrationError, ExtensionFailed, ExtensionNotFound, NoEntryPointError, ExtensionAlreadyLoaded, ExtensionNotLoaded
from ...role import Role
from ...channel import _threaded_guild_channel_factory
from ...errors import InvalidData
from ...user import User
from ...member import Member
from typing import Any, Callable, Dict, List, Mapping, Optional, Union
from ...enums import ApplicationCommandType, ChannelType
from .context import Context
from ...interactions import MISSING, Interaction, InteractionType
from ...client import Client
from .cog import Cog
import traceback, sys, types, importlib

def _is_submodule(parent: str, child: str) -> bool:
    return parent == child or child.startswith(parent + ".")

class Bot(Client):
    def __init__(self, **options):
        super().__init__(**options)
        self.all_commands = {} # name: Command Object
        self.to_register = {} # partial command: guild ids
        self.extra_events: Dict[str, List] = {}
        self.__cogs: Dict[str, Cog] = {}
        self.__extensions: Dict[str, ] = {}
        self._before_invoke = None
        self._after_invoke = None
        self.owner_id = options.get('owner_id')
        self.owner_ids = options.get('owner_ids', set())
        self.strip_after_prefix = options.get('strip_after_prefix', False)

        if self.owner_id and self.owner_ids:
            raise TypeError('Both owner_id and owner_ids are set.')

        if self.owner_ids and not isinstance(self.owner_ids, set):
            raise TypeError(f'owner_ids must be a set not {self.owner_ids.__class__!r}')

        if self.owner_id and not isinstance(self.owner_id, int):
            raise TypeError(f'owner_id must be an int not {self.owner_id.__class__!r}')

    # internal helpers

    def dispatch(self, event_name: str, *args: Any, **kwargs: Any) -> None:
        # super() will resolve to Client
        super().dispatch(event_name, *args, **kwargs)  # type: ignore
        ev = 'on_' + event_name
        for event in self.extra_events.get(ev, []):
            self._schedule_event(event, ev, *args, **kwargs)  # type: ignore

    @discord.utils.copy_doc(discord.Client.close)
    async def close(self) -> None:
        for extension in tuple(self.__extensions):
            try:
                self.unload_extension(extension)
            except Exception:
                pass

        for cog in tuple(self.__cogs):
            try:
                self.remove_cog(cog)
            except Exception:
                pass

        await super().close()  # type: ignore

    async def on_command_error(self, context: Context, exception: CommandError) -> None:
        """|coro|

        The default command error handler provided by the bot.

        By default this prints to :data:`sys.stderr` however it could be
        overridden to have a different implementation.

        This only fires if you do not specify any listeners for command error.
        """
        if self.extra_events.get('on_command_error', None):
            return

        if hasattr(context.command, 'on_error'):
            return

        cog = context.cog
        if cog and cog.has_error_handler():
            return

        print(f'Ignoring exception in command {context.command}:', file=sys.stderr)
        traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)

    def get_context(self, interaction: Interaction):
        return Context(self, interaction)

    @property
    def commands(self):
        """Set[:class:`.Command`]: A unique, unordered set of commands without aliases that are registered
        with the bot.
        """
        return set(self.all_commands.values())

    async def on_interaction(self, interaction: Interaction):
        """
        This is called when an interaction is received from Discord.
        """
        if interaction.type != InteractionType.application_command:
            return
        ctx = self.get_context(interaction)
        if ctx.command_type == ApplicationCommandType.chat_input:
            return await self.handle_slash_command(ctx)
        elif ctx.command_type == ApplicationCommandType.message:
            return await self.handle_message_command(ctx)
        elif ctx.command_type == ApplicationCommandType.user:
            return await self.handle_user_command(ctx)
        else:
            pass

    async def sync_commands(self) -> None:
        commands = [c.app_command for c in self.commands if c.guild_ids is None]
        await self.overwrite_commands(*commands)
        guilds = {} # guild id: [commands]
        for command in [c for c in self.commands if c.guild_ids is not None]:
            for guild_id in command.guild_ids:
                guilds.setdefault(guild_id, []).append(command)
        for guild, commands in guilds.items():
            payload = [command.app_command.to_dict() for command in commands]
            _cmds = {c.name: c for c in commands}
            commands = await self.http.bulk_upsert_guild_commands(self.application_id, guild, payload)
            for command in commands:
                cmd = ApplicationCommand(state=self._connection, data=command)
                cmd_name = cmd.name
                for option in cmd.options:
                    if option.type.value in (1, 2):
                        cmd_name += ' ' + option.name
                _cmds[cmd_name].app_command = cmd
            perms_payload = []
            for command in _cmds.values():
                if command.permissions:
                    perms_payload.append({
                        'id': command.app_command.id,
                        'permissions': [p.to_dict() for p in command.permissions]
                    })
            await self.http.bulk_edit_guild_application_command_permissions(self.application_id, guild, perms_payload)

    async def handle_slash_command(self, ctx: Context):
        if ctx.command_name not in self.all_commands:
            raise CommandNotFound(f'Command {ctx.command_name} was not found')
        command = self.all_commands[ctx.command_name]
        if command.guild_ids is not None and ctx.guild_id not in command.guild_ids:
            raise CommandNotFound(f'Command {ctx.command_name} was not found in guild {ctx.guild_id}')
        data = ctx._data
        options = [o for o in data['options'] if o['type'] not in (1, 2)]
        args = {}
        resolved = data.get('resolved', {})
        for option in options:
            # attempts to convert values to their respective objects, falls back to int if fails
            v = option['value']
            if option['type'] == 6:
                v = int(option['value'])
                if str(option['value']) in resolved.get('members', []):
                    v = resolved['members'][str(option['value'])]
                    if str(option['value']) in resolved.get('users', []):
                        v['user'] = resolved['users'][str(option['value'])]
                    v = Member(data=v, guild=ctx.guild, state=self._connection)
                else:
                    if str(option['value']) in resolved.get('users', []):
                        v = resolved['users'][str(option['value'])]
                    v = User(data=v, state=self._connection)
            elif option['type'] == 7:
                v = int(option['value'])
                if str(option['value']) in resolved.get('channels', []):
                    data = resolved['channels'][str(option['value'])]
                    factory, ch_type = _threaded_guild_channel_factory(data['type'])
                    if factory is None:
                        raise InvalidData('Unknown channel type {type} for channel ID {id}.'.format_map(data))
                    if ch_type in (ChannelType.group, ChannelType.private):
                        raise InvalidData('Channel ID resolved to a private channel')
                    guild_id = int(data['guild_id'])
                    if self.id != guild_id:
                        raise InvalidData('Guild ID resolved to a different guild')
                    v: GuildChannel = factory(guild=ctx.guild, state=self._connection, data=data)  # type: ignore
            elif option['type'] == 8:
                v = int(option['value'])
                if str(option['value']) in resolved.get('roles', []):
                    data = resolved['roles'][str(option['value'])]
                    v = Role(data=data, state=self._connection, guild=ctx.guild)
            elif option['type'] == 9: # mentionable can be a user or a role
                v = int(option['value'])
                if str(option['value']) in resolved.get('members', []):
                    v = resolved['members'][str(option['value'])]
                    if str(option['value']) in resolved.get('users', []):
                        v['user'] = resolved['users'][str(option['value'])]
                    v = Member(data=v, guild=ctx.guild, state=self._connection)
                else:
                    if str(option['value']) in resolved.get('users', []):
                        v = resolved['users'][str(option['value'])]
                        v = User(data=v, state=self._connection)
                    else:
                        if str(option['value']) in resolved.get('channels', []):
                            data = resolved['channels'][str(option['value'])]
                            factory, ch_type = _threaded_guild_channel_factory(data['type'])
                            if factory is None:
                                raise InvalidData('Unknown channel type {type} for channel ID {id}.'.format_map(data))
                            if ch_type in (ChannelType.group, ChannelType.private):
                                raise InvalidData('Channel ID resolved to a private channel')
                            guild_id = int(data['guild_id'])
                            if self.id != guild_id:
                                raise InvalidData('Guild ID resolved to a different guild')
                            v: GuildChannel = factory(guild=ctx.guild, state=self._connection, data=data)  # type: ignore
            option['value'] = v
            args[option['name']] = option['value']
        ctx.args = args
        self.dispatch('command', ctx)
        try:
            if ctx.cog is None:
                return await ctx.command.callback(ctx, **args)
            return await ctx.command.callback(ctx.cog, ctx, **args)
        except Exception as exc:
            return await ctx.command.dispatch_error(ctx, exc)
        finally:
            self.dispatch('command_completion', ctx)

    async def handle_message_command(self, ctx: Context):
        if ctx.command_name not in self.all_commands:
            raise CommandNotFound(f'Command {ctx.command_name} was not found')
        command = self.all_commands[ctx.command_name]
        if command.guild_ids is not None and ctx.guild_id not in command.guild_ids:
            raise CommandNotFound(f'Command {ctx.command_name} was not found in guild {ctx.guild_id}')
        message = Message(state=self._connection, channel=ctx.channel, data=list(ctx._data['resolved']['messages'].values())[0])
        ctx.args = {'message': message}
        self.dispatch('command', ctx)
        try:
            if ctx.cog is None:
                return await ctx.command.callback(ctx, message=message)
            return await ctx.command.callback(ctx.cog, ctx, message=message)
        except Exception as exc:
            return await ctx.command.dispatch_error(ctx, exc)
        finally:
            self.dispatch('command_completion', ctx)

    async def handle_user_command(self, ctx: Context):
        resolved = ctx._data['resolved']
        user = None
        if resolved.get('members'):
            user = list(resolved['members'].values())[0]
            if resolved.get('users'):
                user['user'] = list(resolved['users'].values())[0]
            user = Member(data=user, guild=ctx.guild, state=self._connection)
        else:
            if resolved.get('users'):
                v = list(resolved['users'].values())[0]
                v = User(data=user, state=self._connection)
        if user is None:
            raise InvalidData('Could not resolve user')
        ctx.args = {'user': user}
        self.dispatch('command', ctx)
        try:
            if ctx.cog is None:
                return await ctx.command.callback(ctx, user=user)
            return await ctx.command.callback(ctx.cog, ctx, user=user)
        except Exception as exc:
            return await ctx.command.dispatch_error(ctx, exc)
        finally:
            self.dispatch('command_completion', ctx)

    def add_command(self, command: Command):
        if command.name in self.all_commands:
            raise CommandRegistrationError(command.name)
        self.all_commands[command.name] = command

    async def is_owner(self, user: discord.User) -> bool:
        """|coro|

        Checks if a :class:`~discord.User` or :class:`~discord.Member` is the owner of
        this bot.

        If an :attr:`owner_id` is not set, it is fetched automatically
        through the use of :meth:`~.Bot.application_info`.

        .. versionchanged:: 1.3
            The function also checks if the application is team-owned if
            :attr:`owner_ids` is not set.

        Parameters
        -----------
        user: :class:`.abc.User`
            The user to check for.

        Returns
        --------
        :class:`bool`
            Whether the user is the owner.
        """

        if self.owner_id:
            return user.id == self.owner_id
        elif self.owner_ids:
            return user.id in self.owner_ids
        else:

            app = await self.application_info()  # type: ignore
            if app.team:
                self.owner_ids = ids = {m.id for m in app.team.members}
                return user.id in ids
            else:
                self.owner_id = owner_id = app.owner.id
                return user.id == owner_id

    # listener registration

    def add_listener(self, func, name: str = MISSING) -> None:
        """The non decorator alternative to :meth:`.listen`.

        Parameters
        -----------
        func: :ref:`coroutine <coroutine>`
            The function to call.
        name: :class:`str`
            The name of the event to listen for. Defaults to ``func.__name__``.

        Example
        --------

        .. code-block:: python3

            async def on_ready(): pass
            async def my_message(message): pass

            bot.add_listener(on_ready)
            bot.add_listener(my_message, 'on_message')

        """
        name = func.__name__ if name is MISSING else name

        if not asyncio.iscoroutinefunction(func):
            raise TypeError('Listeners must be coroutines')

        if name in self.extra_events:
            self.extra_events[name].append(func)
        else:
            self.extra_events[name] = [func]

    def remove_listener(self, func, name: str = MISSING) -> None:
        """Removes a listener from the pool of listeners.

        Parameters
        -----------
        func
            The function that was used as a listener to remove.
        name: :class:`str`
            The name of the event we want to remove. Defaults to
            ``func.__name__``.
        """

        name = func.__name__ if name is MISSING else name

        if name in self.extra_events:
            try:
                self.extra_events[name].remove(func)
            except ValueError:
                pass

    def listen(self, name: str = MISSING) -> Callable:
        """A decorator that registers another function as an external
        event listener. Basically this allows you to listen to multiple
        events from different places e.g. such as :func:`.on_ready`

        The functions being listened to must be a :ref:`coroutine <coroutine>`.

        Example
        --------

        .. code-block:: python3

            @bot.listen()
            async def on_message(message):
                print('one')

            # in some other file...

            @bot.listen('on_message')
            async def my_message(message):
                print('two')

        Would print one and two in an unspecified order.

        Raises
        -------
        TypeError
            The function being listened to is not a coroutine.
        """

        def decorator(func):
            self.add_listener(func, name)
            return func

        return decorator

    # cogs

    def add_cog(self, cog: Cog, *, override: bool = False) -> None:
        """Adds a "cog" to the bot.

        A cog is a class that has its own event listeners and commands.

        .. versionchanged:: 2.0

            :exc:`.ClientException` is raised when a cog with the same name
            is already loaded.

        Parameters
        -----------
        cog: :class:`.Cog`
            The cog to register to the bot.
        override: :class:`bool`
            If a previously loaded cog with the same name should be ejected
            instead of raising an error.

            .. versionadded:: 2.0

        Raises
        -------
        TypeError
            The cog does not inherit from :class:`.Cog`.
        CommandError
            An error happened during loading.
        .ClientException
            A cog with the same name is already loaded.
        """

        if not isinstance(cog, Cog):
            raise TypeError('cogs must derive from Cog')

        cog_name = cog.__cog_name__
        existing = self.__cogs.get(cog_name)

        if existing is not None:
            if not override:
                raise discord.ClientException(f'Cog named {cog_name!r} already loaded')
            self.remove_cog(cog_name)

        cog = cog._inject(self)
        self.__cogs[cog_name] = cog

    def get_cog(self, name: str) -> Optional[Cog]:
        """Gets the cog instance requested.

        If the cog is not found, ``None`` is returned instead.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog you are requesting.
            This is equivalent to the name passed via keyword
            argument in class creation or the class name if unspecified.

        Returns
        --------
        Optional[:class:`Cog`]
            The cog that was requested. If not found, returns ``None``.
        """
        return self.__cogs.get(name)

    def remove_cog(self, name: str) -> Optional[Cog]:
        """Removes a cog from the bot and returns it.

        All registered commands and event listeners that the
        cog has registered will be removed as well.

        If no cog is found then this method has no effect.

        Parameters
        -----------
        name: :class:`str`
            The name of the cog to remove.

        Returns
        -------
        Optional[:class:`.Cog`]
             The cog that was removed. ``None`` if not found.
        """

        cog = self.__cogs.pop(name, None)
        if cog is None:
            return

        help_command = self._help_command
        if help_command and help_command.cog is cog:
            help_command.cog = None
        cog._eject(self)

        return cog

    @property
    def cogs(self) -> Mapping[str, Cog]:
        """Mapping[:class:`str`, :class:`Cog`]: A read-only mapping of cog name to cog."""
        return types.MappingProxyType(self.__cogs)

    # extensions

    def _remove_module_references(self, name: str) -> None:
        # find all references to the module
        # remove the cogs registered from the module
        for cogname, cog in self.__cogs.copy().items():
            if _is_submodule(name, cog.__module__):
                self.remove_cog(cogname)

        # remove all the commands from the module
        for cmd in self.all_commands.copy().values():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                self.remove_command(cmd.name)

        # remove all the listeners from the module
        for event_list in self.extra_events.copy().values():
            remove = []
            for index, event in enumerate(event_list):
                if event.__module__ is not None and _is_submodule(name, event.__module__):
                    remove.append(index)

            for index in reversed(remove):
                del event_list[index]

    def _call_module_finalizers(self, lib: types.ModuleType, key: str) -> None:
        try:
            func = getattr(lib, 'teardown')
        except AttributeError:
            pass
        else:
            try:
                func(self)
            except Exception:
                pass
        finally:
            self.__extensions.pop(key, None)
            sys.modules.pop(key, None)
            name = lib.__name__
            for module in list(sys.modules.keys()):
                if _is_submodule(name, module):
                    del sys.modules[module]

    def _load_from_module_spec(self, spec: importlib.machinery.ModuleSpec, key: str) -> None:
        # precondition: key not in self.__extensions
        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib
        try:
            spec.loader.exec_module(lib)  # type: ignore
        except Exception as e:
            del sys.modules[key]
            raise ExtensionFailed(key, e) from e

        try:
            setup = getattr(lib, 'setup')
        except AttributeError:
            del sys.modules[key]
            raise NoEntryPointError(key)

        try:
            setup(self)
        except Exception as e:
            del sys.modules[key]
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, key)
            raise ExtensionFailed(key, e) from e
        else:
            self.__extensions[key] = lib

    def _resolve_name(self, name: str, package: Optional[str]) -> str:
        try:
            return importlib.util.resolve_name(name, package)
        except ImportError:
            raise ExtensionNotFound(name)

    def load_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """Loads an extension.

        An extension is a python module that contains commands, cogs, or
        listeners.

        An extension must have a global function, ``setup`` defined as
        the entry point on what to do when the extension is loaded. This entry
        point must have a single argument, the ``bot``.

        Parameters
        ------------
        name: :class:`str`
            The extension name to load. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when loading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        --------
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionAlreadyLoaded
            The extension is already loaded.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension or its setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        if name in self.__extensions:
            raise ExtensionAlreadyLoaded(name)

        spec = importlib.util.find_spec(name)
        if spec is None:
            raise ExtensionNotFound(name)

        self._load_from_module_spec(spec, name)

    def unload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """Unloads an extension.

        When the extension is unloaded, all commands, listeners, and cogs are
        removed from the bot and the module is un-imported.

        The extension can provide an optional global function, ``teardown``,
        to do miscellaneous clean-up if necessary. This function takes a single
        parameter, the ``bot``, similar to ``setup`` from
        :meth:`~.Bot.load_extension`.

        Parameters
        ------------
        name: :class:`str`
            The extension name to unload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when unloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        -------
        ExtensionNotFound
            The name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionNotLoaded
            The extension was not loaded.
        """

        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise ExtensionNotLoaded(name)

        self._remove_module_references(lib.__name__)
        self._call_module_finalizers(lib, name)

    def reload_extension(self, name: str, *, package: Optional[str] = None) -> None:
        """Atomically reloads an extension.

        This replaces the extension with the same extension, only refreshed. This is
        equivalent to a :meth:`unload_extension` followed by a :meth:`load_extension`
        except done in an atomic way. That is, if an operation fails mid-reload then
        the bot will roll-back to the prior working state.

        Parameters
        ------------
        name: :class:`str`
            The extension name to reload. It must be dot separated like
            regular Python imports if accessing a sub-module. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when reloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        -------
        ExtensionNotLoaded
            The extension was not loaded.
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension setup function had an execution error.
        """

        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise ExtensionNotLoaded(name)

        # get the previous module states from sys modules
        modules = {
            name: module
            for name, module in sys.modules.items()
            if _is_submodule(lib.__name__, name)
        }

        try:
            # Unload and then load the module...
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, name)
            self.load_extension(name)
        except Exception:
            # if the load failed, the remnants should have been
            # cleaned from the load_extension function call
            # so let's load it from our old compiled library.
            lib.setup(self)  # type: ignore
            self.__extensions[name] = lib

            # revert sys.modules back to normal and raise back to caller
            sys.modules.update(modules)
            raise

    @property
    def extensions(self) -> Mapping[str, types.ModuleType]:
        """Mapping[:class:`str`, :class:`py:types.ModuleType`]: A read-only mapping of extension name to extension."""
        return types.MappingProxyType(self.__extensions)