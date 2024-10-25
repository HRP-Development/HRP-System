import discord
import pytz
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Any


def setup(tree: discord.app_commands.CommandTree, cursor: sqlite3.Cursor, connection: sqlite3.Connection, client:discord.Client, logger: logging.Logger):
    global _c, _conn, _bot, _logger
    _c, _conn, _bot, _logger = cursor, connection, client, logger

    _setup_database()
    tree.add_command(_statdock_add)

def _setup_database():
    _c.executescript('''
    CREATE TABLE IF NOT EXISTS "STATDOCK" (
        `id` integer not null primary key autoincrement,
        `enabled` BOOLEAN not null,
        `guild_id` INT not null,
        `category_id` INT not null,
        `channel_id` INT not null,
        `type` varchar(255) not null,
        `timezone` varchar(255) null,
        `timeformat` varchar(255) null,
        `countbots` BOOLEAN null,
        `role_id` varchar(255) null,
        `prefix` varchar(255) null,
        `frequency` INT not null
    )
    ''')

async def _get_or_fetch(item: str, item_id: int) -> Optional[Any]:
    """
    Attempts to retrieve an object using the 'get_<item>' method of the bot class, and
    if not found, attempts to retrieve it using the 'fetch_<item>' method.

    :param item: Name of the object to retrieve
    :param item_id: ID of the object to retrieve
    :return: Object if found, else None
    :raises AttributeError: If the required methods are not found in the bot class
    """
    get_method_name = f'get_{item}'
    fetch_method_name = f'fetch_{item}'

    get_method = getattr(_bot, get_method_name, None)
    fetch_method = getattr(_bot, fetch_method_name, None)

    if get_method is None or fetch_method is None:
        raise AttributeError(f"Methods {get_method_name} or {fetch_method_name} not found on bot object.")

    item_object = get_method(item_id)
    if item_object is None:
        try:
            item_object = await fetch_method(item_id)
        except discord.NotFound:
            pass
    return item_object

def isValidTimezone(timezone: str) -> bool:
    if timezone not in pytz.all_timezones:
        return False
    else:
        return True

def isValidTimeformat(timeformat: str) -> bool:
    try:
        datetime.now().strftime(timeformat)
        return True
    except ValueError:
        return False









@discord.app_commands.command(name='statdock_add', description='Initializes a new statdock.')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.describe(category = 'The category you want to create the dock in.',
                               frequency = 'The frequency in which the statdock updates.',
                               stat_type = 'The kind of dock, you wanna create.',
                               timezone = 'The timezone you wanna use. - Only for type `Time` (Europe/Berlin).',
                               timeformat = 'The timeformat you wanna use. - Only for type `Time` (%d.%m.%Y | %H:%M:%S)',
                               countbots = 'Should bots be included? - Only used for type `Member in role` and `Member`.',
                               role = 'Role, whose member count should be tracked. - Only for type `Member in role`.',
                               prefix = 'Text, that is put before the counter.'
                               )
@discord.app_commands.choices(
    stat_type=[
        discord.app_commands.Choice(name='Time', value='time'),
        discord.app_commands.Choice(name='Member in role', value='role'),
        discord.app_commands.Choice(name='Member', value='member'),
    ],
    frequency=[
        discord.app_commands.Choice(name='5 minutes', value=5),
        discord.app_commands.Choice(name='10 minutes', value=10),
        discord.app_commands.Choice(name='15 minutes', value=15),
        discord.app_commands.Choice(name='20 minutes', value=20),
        discord.app_commands.Choice(name='25 minutes', value=25),
        discord.app_commands.Choice(name='30 minutes', value=30),
    ]
)
async def _statdock_add(
        interaction: discord.Interaction,
        stat_type: str,
        category: discord.CategoryChannel,
        frequency: int,
        prefix: str = None,
        timezone: str = 'Europe/Berlin',
        timeformat: str = '%d.%m.%Y | %H:%M:%S',
        countbots: bool = False,
        role: discord.Role = None
    ):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(
            create_instant_invite=False,
            kick_members=False,
            ban_members=False,
            administrator=False,
            manage_channels=False,
            manage_guild=False,
            add_reactions=False,
            view_audit_log=False,
            priority_speaker=False,
            stream=False,
            read_messages=False,
            view_channel=True,
            send_messages=False,
            send_tts_messages=False,
            manage_messages=False,
            embed_links=False,
            attach_files=False,
            read_message_history=False,
            mention_everyone=False,
            external_emojis=False,
            use_external_emojis=False,
            view_guild_insights=False,
            connect=False,
            speak=False,
            mute_members=False,
            deafen_members=False,
            move_members=False,
            use_voice_activation=False,
            change_nickname=False,
            manage_nicknames=False,
            manage_roles=False,
            manage_permissions=False,
            manage_webhooks=False,
            manage_expressions=False,
            manage_emojis=False,
            manage_emojis_and_stickers=False,
            use_application_commands=False,
            request_to_speak=False,
            manage_events=False,
            manage_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            send_messages_in_threads=False,
            external_stickers=False,
            use_external_stickers=False,
            use_embedded_activities=False,
            moderate_members=False,
            use_soundboard=False,
            use_external_sounds=False,
            send_voice_messages=False,
            create_expressions=False,
            create_events=False,
            send_polls=False,
            create_polls=False,
            use_external_apps=False,
        )
    }

    if not category:
       await interaction.response.send_message("How did we get here?")
       return

    if stat_type == 'role' and role is None:
        await interaction.response.send_message("You need to enter a role, to use this stat dock.", ephemeral=True)
        return

    await interaction.response.send_message("The stat dock is being created...", ephemeral=True)
    try:
        created_channel = await interaction.guild.create_voice_channel(name='Loading...', category=category, overwrites=overwrites)
    except Exception as e:
        _logger.error(e)
        await interaction.edit_original_response(content=f"The channel couldn't be created:\n```txt{e}```")
        return

    match stat_type:
        case 'time':
            if not isValidTimezone(timezone) or not isValidTimeformat(timeformat):
                await interaction.edit_original_response("You either entered a wrong timezone, or format.")
                return
            _c.execute('INSERT INTO `STATDOCK` (enabled, guild_id, category_id, channel_id, type, timezone, timeformat, prefix, frequency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (True, interaction.guild.id, category.id, created_channel.id, stat_type, timezone, timeformat, prefix, frequency))
            _conn.commit()    
    
    




@_statdock_add.autocomplete('timezone')
async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice]:
    return[discord.app_commands.Choice(name=tz, value=tz) for tz in pytz.all_timezones if current.lower() in tz.lower()][:25]