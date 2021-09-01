"""
The MIT License (MIT)
Copyright (c) 2015-present Rapptz
Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""


from __future__ import annotations
import enum

from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING, Tuple, Type, TypeVar, Union
from .enums import try_enum, ApplicationCommandOptionType, ApplicationCommandType, ApplicationCommandPermissionType
from .partial_emoji import PartialEmoji, _EmojiTag

from .types.interactions import ApplicationCommand as ApplicationCommandPayload, ApplicationCommandOption as ApplicationCommandOptionPayload, \
                                ApplicationCommandPermission as ApplicationCommandPermissionPayload, \
                                ApplicationCommandPermissions as ApplicationCommandPermissionsPayload

if TYPE_CHECKING:
    ...

class Choice:
    __slots__ = ('name', 'value')

    def __init__(self, name: str, value: str):
        self.name = name
        self.value = value


class Option:
    __slots__ = ('type', 'name', 'description', 'required', 'choices', 'options')

    if TYPE_CHECKING:
        type: int
        name: str
        description: str
        required: bool
        choices: Optional[List[str]]
        options: list

    def __init__(self, name: str, description: str, type: ApplicationCommandOptionType, *, required: bool = False, choices: Optional[List[Choice]] = None, options: list = None):
        if options and type not in (1, 2):
            raise ValueError('Options can only be used in options of type 1 or 2 (subcommand or subcommand group)')
        self.name = name
        self.description = description
        self.type = type
        self.required = required
        self.choices = choices
        self.options = options

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'description': self.description,
            'type': self.type.value,
            'required': self.required,
            'choices': self.choices,
            'options': [o.to_dict() for o in (self.options or [])]
        }

    @classmethod
    def from_data(cls, data: ApplicationCommandOptionPayload) -> Option:
        self = cls.__new__(cls)
        self.type = try_enum(ApplicationCommandOptionType, int(data['type']))
        self.name = data.get('name')
        self.description = data.get('description')
        self.required = data.get('required', False)
        self.choices = [Choice(d['name'], d['value']) for d in data.get('choices', [])]
        self.options = [Option(d) for d in data.get('options', [])]
        return self

class Subcommand(Option):
    def __init__(self, name: str, description: str, *, options: List[Option] = None):
        super().__init__(name, description, ApplicationCommandOptionType.subcommand, options=options)


class SubcommandGroup(Option):
    def __init__(self, name: str, description: str, *, options: List[Option] = None):
        super().__init__(name, description, ApplicationCommandOptionType.subcommand_group, options=options)
    

class ApplicationCommand:
    __slots__ = ('id', 'type', 'application_id', 'guild_id', 'guild', 'name', 'description', 'options', 'default_permission', '_state')

    if TYPE_CHECKING:
        id: int
        type: ApplicationCommandType
        application_id: int
        guild_id: int
        name: str
        description: str
        options: Optional[List[Option]]

    def __init__(
        self,
        *,
        state,
        data: ApplicationCommandPayload,
    ):
        self._state = state
        self.id = int(data['id'])
        self.type = try_enum(ApplicationCommandType, int(data['type']))
        self.application_id = int(data.get('application_id')) if data.get('application_id') else None
        self.guild_id = int(data.get('guild_id')) if data.get('guild_id') else None
        self.name = data['name']
        self.description = data.get('description')
        self.options = [Option.from_data(d) for d in data.get('options', [])]
        self.default_permission = data.get('default_permission')
        self.guild = None
        if self.guild_id:
            self.guild = state._get_client().get_guild(self.guild_id)

class PartialApplicationCommand:
    def __init__(self, name: str, description: str, type: ApplicationCommandType, *, options: List[Option] = None, default_permission: bool = True):
        self.type = type
        self.name = name
        self.description = description or ''
        self.options = options or []
        self.default_permission = default_permission

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'type': self.type.value,
            'options': [o.to_dict() for o in self.options],
            'default_permission': self.default_permission
        }

class ApplicationCommandPermission:
    __slots__ = ('id', 'type', 'permission', 'object')

    if TYPE_CHECKING:
        id: int
        type: ApplicationCommandPermissionType
        permission: bool

    def __init__(self, id: int, type: ApplicationCommandPermissionType, permission: bool):
        self.id = id
        self.type = type
        self.permission = permission
        
    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type.value,
            'permission': self.permission,
        }

    @classmethod
    def from_data(cls, data: ApplicationCommandPermissionPayload):
        self = cls.__new__(cls)
        self.id = int(data['id'])
        self.type = try_enum(ApplicationCommandPermissionType, int(data['type']))
        self.permission = data['permission']
        return self

class ApplicationCommandPermissions:
    __slots__ = ('id', 'application_id', 'guild_id', 'permissions')

    def __init__(self, data: ApplicationCommandPermissionsPayload) -> None:
        self.id = int(data['id'])
        self.application_id = int(data['application_id'])
        self.guild_id = int(data['guild_id']) if data['guild_id'] else None
        self.permissions = [ApplicationCommandPermission.from_data(d) for d in data['permissions']]