import discord
import sqlite3
import logging





class StatCounter():
    def __init__(self, bot: discord.Client, c: sqlite3.Cursor, conn: sqlite3.Connection, program_logger: logging.Logger, tree: discord.app_commands.CommandTree):
        """
        Initializes the class.

        Args:
            bot (aclient): The bot instance.
            c (sqlite3.Cursor): The SQLite cursor.
            conn (sqlite3.Connection): The SQLite connection.
            program_logger (logging.Logger): The logger instance for the program.
        """
        self.bot = bot
        self.program_logger = program_logger
        self.c = c
        self.conn = conn
        self.tree = tree
        self._setup()

    def _setup(self):
        self._setup_database()
        self.tree.add_command(statdock_add)

    def _setup_database(self):
        self.c.executescript('''
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



@discord.app_commands.command(name='statdock_add', description='Initializes a new statdock.')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.describe(category = 'The category you want to create the dock in.',
                               frequency = 'The frequency in which the statdock updates.',
                               stat_type = 'The kind of dock, you wanna create.',
                               timezone = 'The timezone you wanna use. - Only for type `time` (Europe/Berlin).',
                               timeformat = 'The timeformat you wanna use. - Only for type `time` (%d.%m.%Y | %H:%M:%S)',
                               countbots = 'Should bots be included? - Only used for type `role` and `member`.',
                               role = 'Role, whose member count should be tracked. - Only for type `role`.',
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
async def statdock_add(interaction: discord.Interaction, stat_type: str, category: discord.CategoryChannel, frequency: int, prefix: str = None, timezone: str = 'Europe/Berlin', timeformat: str = '%d.%m.%Y | %H:%M:%S', countbots: bool = False, role: discord.Role = None):
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

    if category is None or '':
       await interaction.response.send_message("How did we get here?")
       return

    if stat_type == 'role' and role is None:
        await interaction.response.send_message("You need to enter a role, to use this stat dock.", ephemeral=True)
        return

    await interaction.response.send_message("The stat dock is being created...", ephemeral=True)
    await interaction.guild.create_voice_channel(name='Loading...', category=category, overwrites=overwrites)

