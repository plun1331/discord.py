import asyncio
from typing import Optional
from .cooldown import BucketType, CooldownMapping, MaxConcurrency
import inspect


class Command:
    """A command object for the bot."""

    def __init__(self, func, application_command, **kwargs):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError('Callback must be a coroutine.')

        self.__original_kwargs__ = kwargs.copy()

        self.app_command = application_command
        self.guild_ids = kwargs.get('guild_ids')

        name = kwargs.get('name') or func.__name__
        if not isinstance(name, str):
            raise TypeError('Name of a command must be a string.')
        self.name: str = name

        self.callback = func
        self.enabled: bool = kwargs.get('enabled', True)

        try:
            permissions: list = func.__permissions__
            permissions.reverse()
        except AttributeError:
            permissions = []

        self.permissions = permissions

        self.cog = None

    def _update_copy(self, kwargs):
        if kwargs:
            kw = kwargs.copy()
            kw.update(self.__original_kwargs__)
            copy = self.__class__(self.callback, self.app_command, **kw)
            return self._ensure_assignment_on_copy(copy)
        else:
            return self.copy()

    def _ensure_assignment_on_copy(self, other):
        if self.checks != other.checks:
            other.checks = self.checks.copy()
        if self._buckets.valid and not other._buckets.valid:
            other._buckets = self._buckets.copy()
        if self._max_concurrency != other._max_concurrency:
            # _max_concurrency won't be None at this point
            other._max_concurrency = self._max_concurrency.copy()  # type: ignore

        try:
            other.on_error = self.on_error
        except AttributeError:
            pass
        return other

    def copy(self):
        ret = self.__class__(self.callback, self.app_command, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)

    def __str__(self) -> str:
        return self.name

    async def dispatch_error(self, ctx, error: Exception) -> None:
        from .cog import Cog
        ctx.command_failed = True
        cog = self.cog
        try:
            coro = self.on_error
        except AttributeError:
            pass
        else:
            try:
                if cog is not None:
                    await coro(cog, ctx, error)
                else:
                    await coro(ctx, error)
            except Exception:
                return await ctx.bot.on_error(str(coro.__name__), error)

        try:
            if cog is not None:
                local = Cog._get_overridden_method(cog.cog_command_error)
                if local is not None:
                    try:
                        await cog.cog_command_error(ctx, error)
                    except Exception:
                        return await ctx.bot.on_error(str(cog.cog_command_error.__name__), error)
        finally:
            ctx.bot.dispatch('command_error', ctx, error)

    def error(self, coro):
        """A decorator that registers a coroutine as a local error handler.

        A local error handler is an :func:`.on_command_error` event limited to
        a single command. However, the :func:`.on_command_error` is still
        invoked afterwards as the catch-all.

        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """

        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        self.on_error = coro
        return coro
