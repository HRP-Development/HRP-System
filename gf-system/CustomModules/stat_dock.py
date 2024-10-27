import asyncio
import discord
import pytz
import sqlite3
import logging
from datetime import datetime
from time import time
from typing import Optional, Any, Literal


# Setup
def setup(tree: discord.app_commands.CommandTree, cursor: sqlite3.Cursor, connection: sqlite3.Connection, client:discord.Client, logger: logging.Logger = None):
    global _c, _conn, _bot, _logger
    _c, _conn, _bot = cursor, connection, client

    if tree is None:
        raise ValueError("Command tree cannot be None.")
    if _c is None:
        raise ValueError("Database cursor cannot be None.")
    if _conn is None:
        raise ValueError("Database connection cannot be None.")
    if _bot is None:
        raise ValueError("Discord client cannot be None.")

    if logger is None:
        logger = logging.getLogger("null")
        logger.addHandler(logging.NullHandler)
    _logger = logger

    _setup_database()

    tree.add_command(_statdock_add)
    tree.add_command(_statdock_list)
    tree.add_command(_statdock_update)

def _setup_database():
    _c.executescript('''
    CREATE TABLE IF NOT EXISTS "STATDOCK" (
        `id` integer not null primary key autoincrement,
        `enabled` BOOLEAN not null default 1,
        `guild_id` INT not null,
        `category_id` INT not null,
        `channel_id` INT not null,
        `type` varchar(255) not null,
        `timezone` varchar(255) null,
        `timeformat` varchar(255) null,
        `countbots` BOOLEAN null,
        `role_id` INT null,
        `prefix` varchar(255) null,
        `frequency` INT not null,
        `last_updated` INT not null,
        `countusers` BOOLEAN null
    )
    ''')

async def task():
    # Calling this function in setup_hook(), can/will lead to a deadlock!
    async def _function():
        _c.execute('SELECT * FROM `STATDOCK` WHERE `enabled` = 1 AND (last_updated + frequency * 60) < ?', (int(time()),))
        data = _c.fetchall()
        for entry in data:
            guild_id = entry[2]
            category_id = entry[3]
            channel_id = entry[4]
            stat_type = entry[5]
            timezone = entry[6]
            timeformat = entry[7]
            countbots = entry[8]
            role_id = entry[9]
            prefix = entry[10]
            countusers = entry[13]

            await _update_dock(enabled=True,
                               guild_id=guild_id,
                               category_id=category_id,
                               channel_id=channel_id,
                               stat_type=stat_type,
                               timezone=timezone,
                               timeformat=timeformat,
                               countbots=countbots,
                               countusers=countusers,
                               role_id=role_id,
                               prefix=prefix
                               )

    await _bot.wait_until_ready()

    while True:
        await _function()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            break

_overwrites = discord.PermissionOverwrite(
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



# Main functions
async def _init_dock(guild: discord.Guild,
                     category: discord.CategoryChannel,
                     channel: discord.VoiceChannel,
                     stat_type: Literal['time', 'role', 'member'],
                     timezone: str,
                     timeformat: str,
                     countbots: bool,
                     countusers: bool,
                     role: discord.Role,
                     prefix: str,
                     frequency: int
                     ):
    # Initializes the dock the first time.
    _conn.commit()
    try:
        match stat_type:
            case 'time':
                await channel.edit(name=f"{prefix + " " if prefix else ""}{_get_current_time(timezone=timezone, time_format=timeformat)}")
            case 'role':
                members_in_role = await _count_members_by_role(role=role, count_bots=countbots, count_users=countusers)
                await channel.edit(name=f"{prefix + " " if prefix else ""}{members_in_role}")
            case 'member':
                members_in_guild = await _count_members_in_guild(guild=guild, count_bots=countbots, count_users=countusers)
                await channel.edit(name=f"{prefix + " " if prefix else ""}{members_in_guild}")
    except Exception as e:
        _logger.warning(e)
        return str(e)

    _c.execute(
        'INSERT INTO `STATDOCK` (guild_id, category_id, channel_id, type, timezone, timeformat, prefix, frequency, last_updated, countbots, countusers, role_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', 
        (
            guild.id,
            category.id,
            channel.id,
            stat_type,
            timezone,
            timeformat,
            prefix,
            frequency,
            int(time()),
            countbots,
            countusers,
            None if not role else role.id
        )
    )

async def _re_init_dock(guild_id, category_id, channel_id, stat_type, timezone, timeformat, countbots, countusers, role_id, prefix):
    # Re-initializes the dock, if the channel got deleted and the stat dock not disabled/deleted.
    guild: discord.Guild = await _get_or_fetch('guild', guild_id)
    category: discord.CategoryChannel = await _get_or_fetch('channel', category_id)
    if (guild is None or category is None or (stat_type == 'role' and (role := await _get_or_fetch('role', role_id)) is None)):
        _c.execute('DELETE FROM `STATDOCK` WHERE `channel_id` = ?', (channel_id,))
        _conn.commit()
        return
    try:
        match stat_type:
            case 'time':
                created_channel = await guild.create_voice_channel(name=f"{prefix + " " if prefix else ""}{_get_current_time(timezone=timezone, time_format=timeformat)}", category=category, overwrites={guild.default_role: _overwrites})
            case 'role':
                members_in_role = await _count_members_by_role(role=role, count_bots=countbots, count_users=countusers)
                created_channel = await guild.create_voice_channel(name=f"{prefix + " " if prefix else ""}{members_in_role}", category=category, overwrites={guild.default_role: _overwrites})
            case 'member':
                members_in_guild = await _count_members_in_guild(guild=guild, count_bots=countbots, count_users=countusers)
                created_channel = await guild.create_voice_channel(name=f"{prefix + " " if prefix else ""}{members_in_guild}", category=category, overwrites={guild.default_role: _overwrites})
        _c.execute('UPDATE `STATDOCK` SET `last_updated` = ?, `channel_id` = ? WHERE `channel_id` = ?', (int(time()), created_channel.id, channel_id,))
        _conn.commit()
    except Exception as e:
        _logger.warning(e)

async def _update_dock(enabled, guild_id, category_id, channel_id, stat_type, timezone, timeformat, countbots, countusers, role_id, prefix):
    # Updates a dock.
    channel: discord.VoiceChannel = await _get_or_fetch('channel', channel_id)
    guild: discord.Guild = await _get_or_fetch('guild', guild_id)
    if not channel or not guild:
        if not enabled:
            _c.execute('DELETE FROM `STATDOCK` WHERE `channel_id` = ?', (channel_id,))
            _conn.commit()
            return False
        else:
            await _re_init_dock(guild_id=guild_id,
                                category_id=category_id,
                                channel_id=channel_id,
                                stat_type=stat_type,
                                timezone=timezone,
                                timeformat=timeformat,
                                countbots=countbots,
                                countusers=countusers,
                                role_id=role_id,
                                prefix=prefix
                                )
    else:
        try:
            new_name = None
            match stat_type:
                case 'time':
                    new_name = f"{prefix + ' ' if prefix else ''}{_get_current_time(timezone=timezone, time_format=timeformat)}"
                case 'role':
                    role: discord.Role = guild.get_role(role_id)
                    members_in_role = await _count_members_by_role(role=role, count_bots=countbots, count_users=countusers)
                    new_name = f"{prefix + ' ' if prefix else ''}{members_in_role}"
                case 'member':
                    members_in_guild = await _count_members_in_guild(guild=guild, count_bots=countbots, count_users=countusers)
                    new_name = f"{prefix + ' ' if prefix else ''}{members_in_guild}"

            if new_name and channel.name != new_name:
                await channel.edit(name=new_name)
                _c.execute('UPDATE `STATDOCK` SET `last_updated` = ? WHERE `channel_id` = ?', (int(time()), channel_id,))
                _conn.commit()
        except Exception as e:
            _logger.warning(e)



# Helper functions
async def _count_members_in_guild(guild: discord.Guild, count_bots: bool, count_users: bool):
    members = [
        member for member in guild.members 
        if (count_users and not member.bot) or (count_bots and member.bot)
    ]
    return len(members)

async def _count_members_by_role(role: discord.Role, count_bots: bool, count_users: bool):
    members_in_role = [
        member for member in role.members 
        if (count_users and not member.bot) or (count_bots and member.bot)
    ]
    return len(members_in_role)

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
        except (discord.NotFound, discord.Forbidden):
            pass
    return item_object

def _isValidTimezone(timezone: str) -> bool:
    if timezone not in pytz.all_timezones:
        return False
    return True

def _isValidTimeformat(timeformat: str) -> bool:
    try:
        datetime.now().strftime(timeformat)
        return True
    except ValueError:
        return False

def _get_current_time(timezone: str, time_format: str) -> str:
    if not _isValidTimezone(timezone) or not _isValidTimeformat(time_format):
        raise ValueError("Invalid timezone or format.")
    
    tz = pytz.timezone(timezone)
    current_time = datetime.now(tz)
    return current_time.strftime(time_format)



# Discord AppCommands (/)
@discord.app_commands.command(name='statdock_add', description='Initializes a new stat dock.')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True, manage_channels = True)
@discord.app_commands.describe(category = 'The category you want to create the dock in.',
                               frequency = 'The frequency in which the stat dock updates.',
                               stat_type = 'The kind of dock, you wanna create.',
                               timezone = 'The timezone you wanna use. - Only for type `Time` (Europe/Berlin).',
                               timeformat = 'The time format you wanna use. - Only for type `Time` (%d.%m.%Y | %H:%M:%S)',
                               countbots = 'Should bots be included? - Only used for type `Member in role` and `Member`.',
                               countusers = 'Should users be included? - Only used for type `Member in role` and `Member`.',
                               role = 'Role, whose member count should be tracked. - Only for type `Member in role`.',
                               prefix = 'Text, that is put before the counter.'
                               )
@discord.app_commands.choices(
    stat_type=[
        discord.app_commands.Choice(name='Time', value='time'),
        discord.app_commands.Choice(name='Member in role', value='role'),
        discord.app_commands.Choice(name='Member', value='member'),
    ],
    frequency = [
        discord.app_commands.Choice(name='6 minutes', value=6),
        discord.app_commands.Choice(name='10 minutes', value=10),
        discord.app_commands.Choice(name='15 minutes', value=15),
        discord.app_commands.Choice(name='20 minutes', value=20),
        discord.app_commands.Choice(name='25 minutes', value=25),
        discord.app_commands.Choice(name='30 minutes', value=30),
        discord.app_commands.Choice(name='45 minutes', value=45),
        discord.app_commands.Choice(name='2 hours', value=120),
        discord.app_commands.Choice(name='3 hours', value=180),
        discord.app_commands.Choice(name='4 hours', value=240),
        discord.app_commands.Choice(name='6 hours', value=360),
        discord.app_commands.Choice(name='8 hours', value=480),
        discord.app_commands.Choice(name='12 hours', value=720),
        discord.app_commands.Choice(name='1 day', value=1440)
    ]
)
async def _statdock_add(
        interaction: discord.Interaction,
        stat_type: str,
        category: discord.CategoryChannel,
        frequency: int,
        prefix: str = None,
        timezone: str = 'Europe/Berlin',
        timeformat: str = '%H:%M',
        countbots: bool = False,
        countusers: bool = False,
        role: discord.Role = None
    ):

    if not category:
       await interaction.response.send_message("How did we get here?", ephemeral=True)
       return

    if stat_type in ['role', 'member']:
        if not (countbots or countusers):
            await interaction.response.send_message(content="You need to enable `countbots`, `countusers`, or both, to use this stat dock.", ephemeral=True)
            return   
        if stat_type == 'role':
            if role is None:
                await interaction.response.send_message(content="You need to enter a role, to use this stat dock.", ephemeral=True)
                return

    await interaction.response.send_message("The stat dock is being created...", ephemeral=True)
    try:
        created_channel = await interaction.guild.create_voice_channel(name='Loading...', category=category, overwrites={interaction.guild.default_role: _overwrites})
    except Exception as e:
        _logger.error(e)
        await interaction.edit_original_response(content=f"The channel couldn't be created:\n```txt{e}```")
        return

    if stat_type == 'time' and (not _isValidTimezone(timezone) or not _isValidTimeformat(timeformat)):
        await interaction.edit_original_response("You either entered a wrong timezone, or format.")
        return
    
    result = await _init_dock(guild=interaction.guild,
                              category=category,
                              channel=created_channel,
                              stat_type=stat_type,
                              timezone=timezone,
                              timeformat=timeformat,
                              countbots=countbots,
                              countusers=countusers,
                              role=None if not role else role,
                              prefix=None if not prefix else prefix.strip(),
                              frequency=frequency,
                              )
    if isinstance(result, str):
        await created_channel.delete(reason="Dock creation failed!")
        await interaction.edit_original_response(content=f"Dock creation failed!\n```txt{result}```")
    else:
        await interaction.edit_original_response(content="Stat dock created.")
    
@_statdock_add.autocomplete('timezone')
async def timezone_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice]:
    return[discord.app_commands.Choice(name=tz, value=tz) for tz in pytz.all_timezones if current.lower() in tz.lower()][:25]



@discord.app_commands.command(name='statdock_update', description='Updates a dock [enable/disable/delete/prefix].')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True, manage_channels = True)
@discord.app_commands.describe(dock = 'The dock you want to update.',
                               action = 'The action you wanna perform.',
                               prefix = 'The new prefix. - Only if `action` is `prefix`. Enter `DELETE to remove.`'
                               )
@discord.app_commands.choices(
    action=[
        discord.app_commands.Choice(name='enable', value='enable'),
        discord.app_commands.Choice(name='disable', value='disable'),
        discord.app_commands.Choice(name='delete', value='delete'),
        discord.app_commands.Choice(name='prefix', value='prefix')
    ]
)
async def _statdock_update(interaction: discord.Interaction, dock: discord.VoiceChannel, action: str, prefix: str = None):
    await interaction.response.defer(ephemeral=True)

    is_dock = _c.execute("SELECT EXISTS(SELECT 1 FROM STATDOCK WHERE `channel_id` = ?)", (dock.id,)).fetchone()[0]
    if not is_dock:
        await interaction.followup.send(content=f"The channel {dock.mention} isn't a dock.")
        return

    match action:
        case 'enable':
            enabled = _c.execute("SELECT `enabled` FROM `STATDOCK` WHERE `channel_id` = ?", (dock.id,)).fetchone()[0]
            if enabled:
                await interaction.followup.send("This dock is already enabled.")
                return
            _c.execute('UPDATE `STATDOCK` SET `enabled` = 1 WHERE `channel_id` = ?', (dock.id,))
            await interaction.followup.send("Dock enabled.")

        case 'disable':
            enabled = _c.execute("SELECT `enabled` FROM `STATDOCK` WHERE `channel_id` = ?", (dock.id,)).fetchone()[0]
            if not enabled:
                await interaction.followup.send("This dock is already disabled.")
                return
            _c.execute('UPDATE `STATDOCK` SET `enabled` = 0 WHERE `channel_id` = ?', (dock.id,))
            await interaction.followup.send("Dock disabled.")

        case 'delete':
            _c.execute('DELETE FROM `STATDOCK` WHERE `channel_id` = ?', (dock.id,))
            await dock.delete()
            await interaction.followup.send("Dock deleted.")

        case 'prefix':
            _c.execute('UPDATE `STATDOCK` SET `prefix` = ? WHERE `channel_id` = ?', (prefix if prefix != 'DELETE' else None, dock.id,))
            if prefix == 'DELETE':
                await interaction.followup.send("Prefix removed.")
            else:
                await interaction.followup.send(f"Prefix changed to `{prefix}`.")

    _conn.commit()



@discord.app_commands.command(name='statdock_list', description='Lists every created stat dock.')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
async def _statdock_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    _c.execute('SELECT * FROM STATDOCK WHERE `guild_id` = ?', (interaction.guild.id,))
    data = _c.fetchall()
    
    if not data:
        await interaction.followup.send("No embeds found for this server.")
        return

    embeds = []
    for entry in data:
        embed_color = discord.Color.green() if entry[1] else discord.Color.red()
        embed_title = f"Embed ID: {entry[0]} - {str(entry[5]).capitalize()}"

        embed = discord.Embed(title=embed_title, color=embed_color)

        if entry[5] == 'member':
            embed.add_field(name="Channel", value=f"<#{entry[4]}>")
            embed.add_field(name="Frequency", value=f"{entry[11]} min")
            embed.add_field(name="Last Updated", value=f"<t:{entry[12]}:F>")
            embed.add_field(name="Prefix", value=entry[10])
            embed.add_field(name="Count Members", value=bool(entry[13]))
            embed.add_field(name="Count Bots", value=bool(entry[8]))
        elif entry[5] == 'role':
            embed.add_field(name="Channel", value=f"<#{entry[4]}>")
            embed.add_field(name="Frequency", value=f"{entry[11]} min")
            embed.add_field(name="Last Updated", value=f"<t:{entry[12]}:F>")
            embed.add_field(name="Prefix", value=entry[10])
            embed.add_field(name="Count Members", value=bool(entry[13]))
            embed.add_field(name="Count Bots", value=bool(entry[8]))
            role = interaction.guild.get_role(entry[9])
            if role:
                embed.add_field(name="Role", value=role.mention, inline=False)
        elif entry[5] == 'time':
            embed.add_field(name="Channel", value=f"<#{entry[4]}>")
            embed.add_field(name="Frequency", value=f"{entry[11]} min")
            embed.add_field(name="Last Updated", value=f"<t:{entry[12]}:F>")
            embed.add_field(name="Prefix", value=entry[10])
            embed.add_field(name="Timezone", value=entry[6])
            embed.add_field(name="Time Format", value=entry[7])

        embeds.append(embed)

        if len(embeds) == 10:
            await interaction.followup.send(embeds=embeds)
            embeds = []

    if embeds:
        await interaction.followup.send(embeds=embeds)








if __name__ == '__main__':
    print(_get_current_time('Europe/Berlin', '%d.%m.%Y | %H:%M:%S'))