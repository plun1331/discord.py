from ...application_commands import ApplicationCommand
from ...webhook.async_ import _WebhookState, handle_message_parameters, async_context
from ...errors import InvalidArgument
from ...interactions import Interaction
from ...webhook import Webhook
from ...http import Route
from ...utils import MISSING

class Context:
    def __init__(self, bot, interaction: Interaction):
        self.interaction = interaction
        self.bot = bot
        self.channel = interaction.channel
        self.channel_id = interaction.channel_id
        self.guild = interaction.guild
        self.guild_id = interaction.guild_id
        self.author = interaction.user
        self.message = interaction.message
        self.permissions = interaction.permissions
        self._data = interaction.data
        self.app_command = ApplicationCommand(state=self.bot._connection, data=self._data)
        self.command_name = self.app_command.name
        self.command = bot.all_commands[self.command_name]
        self.cog = self.command.cog
        for option in self.app_command.options:
            if option.type.value in (1, 2):
                self.command_name += ' ' + option.name

    async def defer(self, *, ephemeral: bool = False):
        await self.interaction.response.defer(ephemeral = ephemeral)

    async def send(self, content: str = MISSING,
        *,
        tts: bool = False,
        ephemeral: bool = False,
        file = MISSING,  # file and files arent supported by the initial response,
        files = MISSING, # but are still sendable with the followup webhook
        embed = MISSING,
        embeds = MISSING,
        allowed_mentions = MISSING,
        view = MISSING,
    ):
        if not self.interaction.response.is_done():
            return await self.interaction.response.send_message(
                content, tts=tts, ephemeral=ephemeral, embed=embed, 
                embeds=embeds, allowed_mentions=allowed_mentions, view=view
            )
        followup: Webhook = self.interaction.followup
        if followup.token is None:
            raise InvalidArgument('This webhook does not have a token associated with it')

        previous_mentions = getattr(followup._state, 'allowed_mentions', None)
        if content is None:
            content = MISSING

        if view is not MISSING:
            if isinstance(followup._state, _WebhookState):
                raise InvalidArgument('Webhook views require an associated state with the webhook')
            if ephemeral is True and view.timeout is None:
                view.timeout = 15 * 60.0

        params = handle_message_parameters(
            content=content,
            tts=tts,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            ephemeral=ephemeral,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
        )
        adapter = async_context.get()
        _params = {'wait': int(True)}
        route = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=followup.id, webhook_token=followup.token)
        data = await adapter.request(route, followup.session, payload=params.payload, multipart=params.multipart, files=files, params=_params)

        msg = followup._create_message(data)

        if view is not MISSING and not view.is_finished():
            message_id = None if msg is None else msg.id
            followup._state.prevent_view_updates_for(message_id)
            followup._state.store_view(view, message_id)

        return msg
        
    async def delete(self):
        if not self.interaction.response.is_done():
            raise RuntimeError('Cannot delete an incomplete response')
        followup: Webhook = self.interaction.followup
        if followup.token is None:
            raise InvalidArgument('This webhook does not have a token associated with it')
        route = Route('DELETE', '/webhooks/{webhook_id}/{webhook_token}/messages/@original', webhook_id=followup.id, webhook_token=followup.token)
        adapter = async_context.get()
        await adapter.request(route, followup.session)

    async def edit_message(self, 
        message_id: int,
        *,
        content = MISSING,
        embeds = MISSING,
        embed = MISSING,
        file = MISSING,
        files = MISSING,
        view = MISSING,
        allowed_mentions = None,
    ):
        followup: Webhook = self.interaction.followup
        if followup.token is None:
            raise InvalidArgument('This webhook does not have a token associated with it')

        if view is not MISSING:
            if isinstance(followup._state, _WebhookState):
                raise InvalidArgument('This webhook does not have state associated with it')

        previous_mentions = getattr(followup._state, 'allowed_mentions', None)
        params = handle_message_parameters(
            content=content,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
        )
        adapter = async_context.get()

        _params = {'wait': int(True)}
        route = Route('PATCH', '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}', webhook_id=followup.id, webhook_token=followup.token, message_id=message_id)
        data = await adapter.request(route, followup.session, payload=params.payload, multipart=params.multipart, files=files, params=_params)

        msg = followup._create_message(data)

        if view is not MISSING and not view.is_finished():
            message_id = None if msg is None else msg.id
            followup._state.prevent_view_updates_for(message_id)
            followup._state.store_view(view, message_id)

        return msg

    async def delete_message(self, message_id):
        followup: Webhook = self.interaction.followup
        if followup.token is None:
            raise InvalidArgument('This webhook does not have a token associated with it')
        route = Route('DELETE', '/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}', webhook_id=followup.id, webhook_token=followup.token, message_id=message_id)
        adapter = async_context.get()
        await adapter.request(route, followup.session)

    async def edit(self, 
        *,
        content = MISSING,
        embeds = MISSING,
        embed = MISSING,
        file = MISSING,
        files = MISSING,
        view = MISSING,
        allowed_mentions = None,
    ):
        if not self.interaction.response.is_done():
            raise RuntimeError('Cannot edit an incomplete response')
        followup: Webhook = self.interaction.followup
        if followup.token is None:
            raise InvalidArgument('This webhook does not have a token associated with it')

        if view is not MISSING:
            if isinstance(followup._state, _WebhookState):
                raise InvalidArgument('This webhook does not have state associated with it')

        previous_mentions = getattr(followup._state, 'allowed_mentions', None)
        params = handle_message_parameters(
            content=content,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
        )
        adapter = async_context.get()

        _params = {'wait': int(True)}
        route = Route('PATCH', '/webhooks/{webhook_id}/{webhook_token}/messages/@original', webhook_id=followup.id, webhook_token=followup.token)
        data = await adapter.request(route, followup.session, payload=params.payload, multipart=params.multipart, files=files, params=_params)

        msg = followup._create_message(data)

        if view is not MISSING and not view.is_finished():
            message_id = None if msg is None else msg.id
            followup._state.prevent_view_updates_for(message_id)
            followup._state.store_view(view, message_id)

        return msg