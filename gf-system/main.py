# Todo: • Abmeldungen für TB

import time
startupTime_start = time.time()
import a2s
import asyncio
import datetime
import discord
import io
import json
import jsonschema
import os
import platform
import random
import sentry_sdk
import signal
import sys
import sqlite3
import string

from CustomModules import database_setup
from CustomModules import log_handler
from CustomModules import steam_api
from CustomModules.steam_api import Errors as steam_errors
from CustomModules import context_commands
from CustomModules.ticket_transcript import TicketHTML
from CustomModules import epic_games_api
from CustomModules import stat_dock
from CustomModules import private_voice as pvoice
from CustomModules import server_updater as supdater

from aiohttp import web
from dotenv import load_dotenv
from typing import Optional, Any
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile
from captcha.image import ImageCaptcha
from pytimeparse.timeparse import timeparse

discord.VoiceClient.warn_nacl = False
load_dotenv()
image_captcha = ImageCaptcha()
APP_FOLDER_NAME = 'HRP-Sys'
BOT_NAME = 'HRP-Sys'
os.makedirs(f'{APP_FOLDER_NAME}//Logs', exist_ok=True)
os.makedirs(f'{APP_FOLDER_NAME}//Buffer', exist_ok=True)
LOG_FOLDER = f'{APP_FOLDER_NAME}//Logs//'
BUFFER_FOLDER = f'{APP_FOLDER_NAME}//Buffer//'
ACTIVITY_FILE = f'{APP_FOLDER_NAME}//activity.json'
SQL_FILE = os.path.join(APP_FOLDER_NAME, f'{BOT_NAME}.db')
BOT_VERSION = "1.12.8"

TOKEN = os.getenv('TOKEN')
OWNERID = os.getenv('OWNER_ID')
LOG_LEVEL = os.getenv('LOG_LEVEL')
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
STEAM_REDIRECT_URL = os.getenv('STEAM_REDIRECT_URL')
PANEL_API_KEY = os.getenv('PANEL_API_KEY')
GAMESERVER_IP = os.getenv('GAMESERVER_IP')
SSHKEY_PW = os.getenv('SSHKEY_PW')

#Init sentry
sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment='Production',
    release=f'{BOT_NAME}@{BOT_VERSION}'
)

log_manager = log_handler.LogManager(LOG_FOLDER, BOT_NAME, LOG_LEVEL)
discord_logger = log_manager.get_logger('discord')
program_logger = log_manager.get_logger('Program')
program_logger.info('Starte Discord Bot...')

SteamAPI = steam_api.API(STEAM_API_KEY)

class JSONValidator:
    schema = {
        "type" : "object",
        "properties" : {
            "activity_type" : {
                "type" : "string",
                "enum" : ["Playing", "Streaming", "Listening", "Watching", "Competing"]
            },
            "activity_title" : {"type" : "string"},
            "activity_url" : {"type" : "string"},
            "status" : {
                "type" : "string",
                "enum" : ["online", "idle", "dnd", "invisible"]
            },
        },
    }

    default_content = {
        "activity_type": "Watching",
        "activity_title": "Über die HRP Infrastruktur",
        "activity_url": "https://status.hrp-community.net",
        "status": "dnd"
    }

    def __init__(self, file_path):
        self.file_path = file_path

    def validate_and_fix_json(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r') as file:
                try:
                    data = json.load(file)
                    jsonschema.validate(instance=data, schema=self.schema)
                except (jsonschema.exceptions.ValidationError, json.decoder.JSONDecodeError) as e:
                    program_logger.error(f'ValidationError: {e}')
                    self.write_default_content()
        else:
            self.write_default_content()

    def write_default_content(self):
        with open(self.file_path, 'w') as file:
            json.dump(self.default_content, file, indent=4)
validator = JSONValidator(ACTIVITY_FILE)
validator.validate_and_fix_json()


try:
    conn = sqlite3.connect(SQL_FILE)
    c = conn.cursor()
    database_setup.database(c).setup_database()
except sqlite3.Error as e:
    program_logger.critical(f"Error while connecting to the database: {e}")
    sys.exit(f"Error while connecting to the database: {e}")


class DiscordEvents():
    class _AddUserModal(discord.ui.Modal):
        def __init__(self, channel):
            super().__init__(title="Benutzer zum Ticket hinzufügen")
            self.channel = channel

            self.user_id_input = discord.ui.TextInput(
                label='Benutzer-ID',
                placeholder='Benutzer-ID',
                min_length=17,
                max_length=21
            )
            self.add_item(self.user_id_input)

        async def on_submit(self, interaction: discord.Interaction):
            user_id = self.user_id_input.value
            if not user_id.isdigit():
                await interaction.response.send_message(content="Die ID darf ausschließlich aus Zahlen bestehen!", ephemeral=True)
                return

            try:
                user = await Functions.get_or_fetch('user', int(user_id))
                await self.channel.set_permissions(user, read_messages=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True)
                await interaction.response.send_message(f'{user.mention} wurde zum Ticket hinzugefügt.', ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f'Fehler beim Hinzufügen eines Nutzers zu einem Ticket: {e}', ephemeral=True)

    class _RemoveUserModal(discord.ui.Modal):
        def __init__(self, channel):
            super().__init__(title="Benutzer zum Entfernen des Tickets")
            self.channel = channel

            self.user_id_input = discord.ui.TextInput(
                label='Benutzer-ID',
                placeholder='Benutzer-ID',
                min_length=17,
                max_length=21
            )
            self.add_item(self.user_id_input)

        async def on_submit(self, interaction: discord.Interaction):
            user_id = self.user_id_input.value
            if not user_id.isdigit():
                await interaction.response.send_message(content="Die ID darf ausschließlich aus Zahlen bestehen!", ephemeral=True)
                return

            user_id = int(user_id)
            if user_id == interaction.user.id:
                await interaction.response.send_message(f'Du kannst dich nicht selbst entfernen.', ephemeral=True)
                return

            try:
                user = await Functions.get_or_fetch('user', user_id)
                await self.channel.set_permissions(user, read_messages=False, send_messages=False, read_message_history=False)
                await interaction.response.send_message(f'{user.mention} wurde vom Ticket entfernt.', ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f'Fehler beim Entfernen eines Nutzers von einem Ticket: {e}', ephemeral=True)

    class _TicketModal(discord.ui.Modal):
        def __init__(self, category, user):
            super().__init__(title='Erstelle ein Ticket')
            self.category = category
            self.user = user

            self.title_input = discord.ui.TextInput(
                label='Titel',
                placeholder='Titel des Tickets',
                min_length=6,
                max_length=30
            )
            self.add_item(self.title_input)

            self.description_input = discord.ui.TextInput(
                label='Beschreibung',
                placeholder='Beschreibung des Tickets',
                style=discord.TextStyle.paragraph,
                min_length=40
            )
            self.add_item(self.description_input)

        async def on_submit(self, interaction: discord.Interaction):
            # Check for existing Ticket
            c.execute('SELECT CHANNEL_ID FROM CREATED_TICKETS WHERE USER_ID = ? AND GUILD_ID = ? AND CATEGORY = ?', (interaction.user.id, interaction.guild.id, self.category))
            data = c.fetchone()
            if data:
                channel = await Functions.get_or_fetch('channel', int(data[0]))
                if channel:
                    await interaction.response.send_message(content=f"Du hast bereits ein offenes Ticket für die Kategorie {self.category}.: <#{data[0]}>\nDu kannst nur ein Ticket pro Kategorie zur selben Zeit offen haben.", ephemeral=True)
                    return
                else:
                    c.execute('DELETE FROM CREATED_TICKETS WHERE USER_ID = ? AND GUILD_ID = ? AND CATEGORY = ?', (interaction.user.id, interaction.guild.id, self.category))
                    conn.commit()

            title = self.title_input.value
            description = self.description_input.value
            category = discord.utils.get(interaction.guild.categories, name=f'Ticket-{self.category}')

            if not category:
                category = await interaction.guild.create_category(f'Ticket-{self.category}')

            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
                self.user: discord.PermissionOverwrite(read_messages=True, embed_links=True, attach_files=True)
            }

            c.execute(f'SELECT SUPPORT_ROLE_ID_{str(self.category).upper()} FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild.id,))
            support_role_id = c.fetchone()[0]
            if support_role_id:
                support_role = interaction.guild.get_role(int(support_role_id))
                if support_role:
                    overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, embed_links=True, attach_files=True)

            channel_name = f"⚠ {self.user.name}"
            ticket_channel = await interaction.guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            await ticket_channel.edit(topic='NICHT LÖSCHEN!')

            ticket_embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            ticket_embed.set_footer(text=f"Ticket erstellt von {self.user}", icon_url=self.user.avatar.url if self.user.avatar else '')

            admin_embed = discord.Embed(
                title="Admincommands",
                description="Das sind die Admincommands für das Ticketsystem.",
                color=discord.Color.purple(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            admin_embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

            close_button = discord.ui.Button(label="✅ Schließen", style=discord.ButtonStyle.blurple, custom_id="close_ticket")
            add_button = discord.ui.Button(label="➕ Hinzufügen", style=discord.ButtonStyle.green, custom_id="add_ticket")
            remove_button = discord.ui.Button(label="➖ Entfernen", style=discord.ButtonStyle.red, custom_id="remove_ticket")

            admin_view = discord.ui.View()
            admin_view.add_item(close_button)
            admin_view.add_item(add_button)
            admin_view.add_item(remove_button)

            await ticket_channel.send(embed=admin_embed, view=admin_view)
            await ticket_channel.send(embed=ticket_embed)
            await ticket_channel.send(content=f"Hey listen <@&{support_role_id}>, es gibt ein neues Ticket.")  # Wenn geändert, ändere Text in ticket.py, um vom Transcript auszunehmen.
            try:
                c.execute('INSERT INTO CREATED_TICKETS (USER_ID, CHANNEL_ID, GUILD_ID, CATEGORY) VALUES (?, ?, ?, ?)', (self.user.id, ticket_channel.id, interaction.guild.id, self.category))
                conn.commit()
                program_logger.debug(f'Ticket wurde erfolgreich erstellt ({self.user.id}, {ticket_channel.id}, {interaction.guild.id}, {self.category}).')
            except Exception as e:
                program_logger.error(f'Fehler beim einfügen in die Datenbank: {e}')
            await interaction.response.send_message(f'Dein Ticket wurde erstellt: {ticket_channel.mention}', ephemeral=True)

    async def on_interaction(interaction: discord.Interaction):
        class WhyView(discord.ui.View):
            def __init__(self, *, timeout=None):
                super().__init__(timeout=timeout)

                self.add_item(discord.ui.Button(label='Secure your server', url = f'https://discord.com/api/oauth2/authorize?client_id=1251187046329094314&permissions=268503046&scope=bot%20applications.commands', style=discord.ButtonStyle.link))

        if interaction.response.is_done():
            return

        component_type = interaction.data.get('component_type')
        button_id = interaction.data.get('custom_id')

        if component_type == 3 and button_id == "support_menu":  # 3 is Dropdown
            selected_value = interaction.data.get('values', [None])[0]
            program_logger.debug(f"Support Menu gewählt: {selected_value}")
            modal = DiscordEvents._TicketModal(selected_value, interaction.user)
            await interaction.response.send_modal(modal)

        elif component_type == 2:  # 2 is Button
            if button_id == "close_ticket":
                if not await Functions.isAdminOrSupport(interaction):
                    await interaction.response.send_message(content="Du hast nicht das Recht diesen Button zu verwenden!", ephemeral=True)
                    return

                updated_view = discord.ui.View.from_message(interaction.message)
                for item in updated_view.children:
                    if isinstance(item, discord.ui.Button) and item.custom_id == "close_ticket":
                        item.disabled = True
                await interaction.message.edit(view=updated_view)

                channel = interaction.channel
                c.execute('SELECT * FROM CREATED_TICKETS WHERE CHANNEL_ID = ?', (channel.id,))
                data_created_tickets = c.fetchone()
                if data_created_tickets is None:
                    return
                await interaction.response.defer(ephemeral=True)

                overwrite = discord.PermissionOverwrite(send_messages=False, add_reactions=False, read_messages=False)
                await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
                await interaction.channel.send(f'Das Ticket wurde von {interaction.user.mention} geschlossen.')

                transcript = await TicketTranscript.create_transcript(interaction.channel.id, data_created_tickets[1])
                user: discord.User = await Functions.get_or_fetch('user', data_created_tickets[1])
                with open(transcript, 'rb') as f:
                    try:
                        await user.send(file=discord.File(f))
                    except Exception as e:
                        if not e.code == 50007:
                            program_logger.error(f'Fehler beim Senden der Nachricht an {user}: {e}')

                c.execute('SELECT ARCHIVE_CHANNEL_ID FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild.id,))
                archive_channel_id = c.fetchone()[0]
                if archive_channel_id is None:
                    return
                archive_channel: discord.TextChannel = await Functions.get_or_fetch('channel', archive_channel_id)
                try:
                    await archive_channel.send(content=f'Kategorie: {data_created_tickets[4]}\nUser: <@{data_created_tickets[1]}>', file=discord.File(transcript))
                except Exception as e:
                    program_logger.warning(f"Transcript couldn't be send to archive. -> {e}")

                os.remove(transcript)
                c.execute('DELETE FROM CREATED_TICKETS WHERE CHANNEL_ID = ?', (channel.id,))
                conn.commit()
                await channel.delete()

            elif button_id == "add_ticket":
                if not await Functions.isAdminOrSupport(interaction):
                    await interaction.response.send_message(content="Du hast nicht das Recht, diesen Button zu verwenden!", ephemeral=True)
                    return

                modal = DiscordEvents._AddUserModal(interaction.channel)
                await interaction.response.send_modal(modal)

            elif button_id == "remove_ticket":
                if not await Functions.isAdminOrSupport(interaction):
                    await interaction.response.send_message(content="Du hast nicht das Recht, diesen Button zu verwenden!", ephemeral=True)
                    return

                modal = DiscordEvents._RemoveUserModal(interaction.channel)
                await interaction.response.send_modal(modal)

            elif button_id == 'verify':
                if interaction.user.id in bot.captcha_timeout:
                    try:
                        await interaction.response.send_message('Please wait a few seconds before trying again.', ephemeral=True)
                    except discord.NotFound:
                        try:
                            await interaction.followup.send('Please wait a few seconds before trying again.', ephemeral=True)
                        except discord.NotFound:
                            pass
                    return
                else:
                    await Functions.verify(interaction)
                    return
            elif button_id == 'why':
                try:
                    await interaction.response.send_message(f'This serever is protected by <@!{bot.user.id}> to prevent raids & malicious users.\n\nTo gain access to this server, you\'ll need to verify yourself by completing a captcha.\n\nYou don\'t need to connect your account for that.', view = WhyView(), ephemeral=True)
                except discord.NotFound:
                    try:
                        await interaction.followup.send(f'This serever is protected by <@!{bot.user.id}> to prevent raids & malicious users.\n\nTo gain access to this server, you\'ll need to verify yourself by completing a captcha.\n\nYou don\'t need to connect your account for that.', view = WhyView(), ephemeral=True)
                    except discord.NotFound:
                        pass

    async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError) -> None:
        options = interaction.data.get("options", [])
        option_values = ", ".join(f"{option['name']}: {option['value']}" for option in options)

        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f'This command is on cooldown.\nTime left: `{str(datetime.timedelta(seconds=int(error.retry_after)))}`',
                ephemeral=True
            )
        elif isinstance(error, discord.app_commands.MissingPermissions):
            missing_permissions = ", ".join(perm.replace("_", " ").capitalize() for perm in error.missing_permissions)
            await interaction.response.send_message(
                f"You are missing the following permissions to execute this command: {missing_permissions}",
                ephemeral=True
            )
        else:
            try:
                await interaction.response.send_message("Error! Try again.", ephemeral=True)
            except (discord.NotFound, discord.HTTPException):
                try:
                    await interaction.followup.send("Error! Try again.", ephemeral=True)
                except (discord.NotFound, discord.HTTPException):
                    pass

            if isinstance(error, discord.Forbidden):
                bot_member = interaction.guild.me
                missing_permissions = [
                    perm.replace("_", " ").capitalize()
                    for perm, value in bot_member.guild_permissions if not value
                ] if bot_member else []

                missing_text = (
                    f"I am missing the following permissions: {', '.join(missing_permissions)}"
                    if missing_permissions else "I am missing required permissions."
                )

                try:
                    await interaction.followup.send(
                        f"{error}\n\n{missing_text}\n\n{option_values}",
                        ephemeral=True
                    )
                except (discord.NotFound, discord.HTTPException):
                    pass

            discord_logger.warning(f"Unexpected error while sending message: {error}")

        program_logger.warning(
            f"{error} -> {option_values} | Invoked by {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({interaction.guild.id}) with Language {interaction.locale[1]}"
        )
        sentry_sdk.capture_exception(error)

    async def on_guild_join(guild: discord.Guild):
        if not bot.synced:
            return
        discord_logger.info(f'Ich wurde zu {guild} hinzugefügt. (ID: {guild.id})')

    async def on_guild_remove(guild):
        if not bot.synced:
            return
        program_logger.info(f'Ich wurde von {guild} gekickt. (ID: {guild.id})')

    async def on_guild_channel_update(before, after):
        if before.position == after.position and before.name == after.name:
            return
        row = c.execute('SELECT channel_id FROM STATDOCK WHERE guild_id = ?', (after.id,)).fetchone()
        if not row:
            return

        embed = discord.Embed(
            title="🔧 Channel aktualisiert",
            description=f"Channel **{before.name}** wurde bearbeitet.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        if before.name != after.name:
            embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
        if row:
            channel = await Functions.get_or_fetch('channel', row[0])
            if channel:
                await channel.send(embed=embed)

    async def on_guild_update(before, after):
        changes = []
        embed = discord.Embed(
            title="⚙️ Server-Einstellungen geändert",
            description=f"Der Server **{before.name}** hat Änderungen erfahren.",
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        if before.name != after.name:
            changes.append(("Servername geändert", f"Von **{before.name}** zu **{after.name}**"))
        if before.icon != after.icon:
            changes.append(("Server-Icon geändert", "Das Server-Icon wurde geändert"))
            embed.set_thumbnail(url=after.icon.url if after.icon else discord.Embed.Empty)
        if before.afk_timeout != after.afk_timeout:
            changes.append(("AFK-Timeout geändert", f"Von **{before.afk_timeout//60} Minuten** zu **{after.afk_timeout//60} Minuten**"))
        if before.system_channel != after.system_channel:
            changes.append(("System-Channel geändert", f"Von **{before.system_channel}** zu **{after.system_channel}**"))
        if before.premium_tier != after.premium_tier:
            changes.append(("Boost-Level geändert", f"Von **Stufe {before.premium_tier}** zu **Stufe {after.premium_tier}**"))
        if before.premium_subscription_count != after.premium_subscription_count:
            changes.append(("Anzahl der Server-Boosts geändert", f"Von **{before.premium_subscription_count}** zu **{after.premium_subscription_count}**"))

        for name, value in changes:
            embed.add_field(name=name, value=value, inline=False)

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.id,)).fetchone()
        if row:
            channel = await Functions.get_or_fetch('channel', row[0])
            if channel:
                await channel.send(embed=embed)

    async def on_guild_channel_create(channel):
        category = channel.category.name if channel.category else "Keine Kategorie"
        embed = discord.Embed(
            title="📁 Neuer Channel erstellt",
            description=f"Channel **{channel.name}** wurde erstellt.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Kategorie:", value=category, inline=False)
        overwrites = channel.overwrites

        if overwrites:
            for entity, overwrite in overwrites.items():
                role_or_user = entity.name if isinstance(entity, discord.Role) else entity.display_name
                permissions = {
                    "read_messages": overwrite.read_messages,
                    "send_messages": overwrite.send_messages,
                    "manage_messages": overwrite.manage_messages,
                    "manage_channels": overwrite.manage_channels,
                    "embed_links": overwrite.embed_links,
                    "attach_files": overwrite.attach_files,
                    "add_reactions": overwrite.add_reactions,
                }
                permission_lines = [f"{perm.replace('_', ' ').capitalize()}: {'✅' if value else '❌'}" for perm, value in permissions.items() if value]

                if permission_lines:
                    embed.add_field(name=f"Rollenüberschreibung für {role_or_user}", value="\n".join(permission_lines), inline=False)

                if len(embed.fields) >= 24:
                    embed.add_field(name="Info", value="Zu viele Berechtigungen, um sie alle anzuzeigen.", inline=False)
                    break

        embed.add_field(name="Channel ID:", value=channel.id)
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (channel.guild.id,)).fetchone()
        log_channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if log_channel:
            await log_channel.send(embed=embed)

    async def on_guild_channel_delete(channel):
        embed = discord.Embed(
            title="🗑️ Channel gelöscht",
            description=f"Channel **{channel.name}** wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (channel.guild.id,)).fetchone()
        if row:
            log_channel = await Functions.get_or_fetch('channel', row[0])
            if log_channel:
                await log_channel.send(embed=embed)

    async def on_guild_role_create(role):
        embed = discord.Embed(
            title="➕ Neue Rolle erstellt",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name="Name:", value=role.name, inline=False)
        embed.add_field(name="Farbe:", value=f"#{role.color.value:06x}", inline=False)
        embed.add_field(name="Erwähnbar:", value="✅" if role.mentionable else "❌", inline=False)
        embed.add_field(name="Getrennt angezeigt:", value="✅" if role.hoist else "❌", inline=False)
        embed.add_field(name="Rollen ID:", value=role.id, inline=False)

        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (role.guild.id,)).fetchone()
        if row:
            channel = await Functions.get_or_fetch('channel', row[0])
            if channel:
                await channel.send(embed=embed)

    async def on_guild_role_delete(role):
        embed = discord.Embed(
            title="➖ Rolle gelöscht",
            description=f"Rolle **{role.name}** wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (role.guild.id,)).fetchone()
        if row:
            channel = await Functions.get_or_fetch('channel', row[0])
            if channel:
                await channel.send(embed=embed)

    async def on_guild_role_update(before, after):
        if before.position == after.position and before.name == after.name:
            return

        embed = discord.Embed(
            title="🔄 Rolle aktualisiert",
            description=f"Rolle **{before.name}** wurde aktualisiert.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        changes = []

        if before.name != after.name:
            embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)

        if before.color != after.color:
            embed.add_field(name="Farbe geändert", value=f"Von {before.color} zu {after.color}", inline=False)

        if before.mentionable != after.mentionable:
            embed.add_field(name="Erwähnbar geändert", value=f"Von {'Erwähnbar' if before.mentionable else 'Nicht erwähnbar'} zu {'Erwähnbar' if after.mentionable else 'Nicht erwähnbar'}", inline=False)

        before_permissions = before.permissions
        after_permissions = after.permissions

        for perm in dir(after_permissions):
            if not perm.startswith("_"):
                before_value = getattr(before_permissions, perm)
                after_value = getattr(after_permissions, perm)

                if before_value != after_value:
                    changes.append(f"**{perm.replace('_', ' ').capitalize()}**: {'✅' if after_value else '❌'}")

        if changes:
            embed.add_field(name="Berechtigungsänderung", value="\n".join(changes), inline=False)

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None

        if channel:
            try:
                await channel.send(embed=embed)
            except Exception as e:
                program_logger.error(f"Error while sending role update log: {e}")

    async def on_message_delete(message):
        try:
            logging_channel_id = c.execute('SELECT `logging_channel` FROM `GUILD_SETTINGS` WHERE `GUILD_ID` = ?', (message.guild.id,)).fetchone()
            if not logging_channel_id or logging_channel_id[0] == message.channel.id:
                return
            logging_channel_id = logging_channel_id[0]
        except TypeError:
            return

        embed = discord.Embed(
            title="🗑️ Nachricht gelöscht",
            description=f"Nachricht von {message.author.mention} wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if message.content:
            embed.add_field(name="Inhalt", value=message.content, inline=False)
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        try:
            async for entry in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete):
                if entry.target.id == message.author.id and entry.extra.channel.id == message.channel.id:
                    embed.description = f"Nachricht von {message.author.mention} wurde durch {entry.user.mention} gelöscht."
                    break
        except discord.Forbidden as e:
            program_logger.warning(f"Couldn't read the audit logs: -> {e}")

        channel = await Functions.get_or_fetch('channel', logging_channel_id)
        if channel:
            try:
                await channel.send(embed=embed)
            except discord.DiscordException as e:
                program_logger.error(f"Error while sending logging message: -> {e}")

    async def on_member_update(before, after):
        changes = []

        if before.roles != after.roles:
            added_roles = [role.name for role in after.roles if role not in before.roles]
            removed_roles = [role.name for role in before.roles if role not in after.roles]

            if added_roles:
                changes.append(f"Hinzugefügt: {', '.join(added_roles)}")
            if removed_roles:
                changes.append(f"Entfernt: {', '.join(removed_roles)}")

        if before.nick != after.nick:
            changes.append(f"Nickname geändert: **{before.nick or 'kein Nickname'}** zu **{after.nick or 'kein Nickname'}**")

        if changes:
            embed = discord.Embed(
                title="🔄 Mitglied aktualisiert",
                description=f"Änderungen an **{after.name}** (ID: {after.id})",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
            embed.add_field(name="Änderungen:", value="\n".join(changes), inline=False)

            row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
            if row:
                channel = await Functions.get_or_fetch('channel', row[0])
                if channel:
                    await channel.send(embed=embed)

    async def on_message(message):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'Commands:\n'
                                       'help - Shows this message\n'
                                       'log - Get the log\n'
                                       'activity - Set the activity of the bot\n'
                                       'status - Set the status of the bot\n'
                                       'shutdown - Shutdown the bot\n'
                                       '```')

        if message.guild is None and message.author.id == int(OWNERID):
            args = message.content.split(' ')
            program_logger.debug(args)
            command, *args = args
            match command:
                case 'help':
                    await __wrong_selection()
                    return
                case 'log':
                    await Owner.log(message, args)
                    return
                case 'activity':
                    await Owner.activity(message, args)
                    return
                case 'status':
                    await Owner.status(message, args)
                    return
                case 'shutdown':
                    await Owner.shutdown(message)
                    return
                case _:
                    await __wrong_selection()
            return

        if not message.author.bot:
            await Functions.check_message(message)
            return
        if message.channel.type == discord.ChannelType.news:
            message_types = [6, 19, 20]
            if message.type.value in message_types:
                return
            await Functions.auto_publish(message)

    async def on_message_edit(before, after):
        def _add_content_field(embed, name, content):
            if len(content) <= 1018:
                embed.add_field(name=name, value=f"```{content}```" or "*(N/A)*", inline=False)
            else:
                embed.add_field(name="\u2007", value="```Änderung von zu großem Text!```" or "*(N/A)*", inline=False)

        if before.content == after.content or before.author.bot:
            return

        embed = discord.Embed(
            title="Nachricht wurde bearbeitet.",
            color=0x2f3136,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        _add_content_field(embed, "Alt", before.content)
        _add_content_field(embed, "Neu", after.content)

        embed.set_author(name=after.author.nick if after.author.nick is not None else after.author.name, icon_url=after.author.avatar.url)
        embed.description = (f"✏️ **Nachricht von** {after.author.mention} **wurde in** {after.channel.mention} **bearbeitet**.\n[Jump to Message]({after.jump_url})")
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_member_join(member: discord.Member):
        def account_age_in_seconds(member: discord.Member) -> int:
            return (datetime.datetime.now(datetime.UTC) - member.created_at).total_seconds()

        if not bot.initialized or member.bot:
            return

        guild_id = member.guild.id
        c.execute('SELECT account_age_min, action, welcome_channel FROM servers LEFT JOIN GUILD_SETTINGS ON servers.guild_id = GUILD_SETTINGS.guild_id WHERE servers.guild_id = ?', (guild_id,))
        result = c.fetchone()
        if not result:
            return

        account_age_min, action, welcome_channel = result
        if account_age_min and account_age_in_seconds(member) < account_age_min:
            try:
                await member.kick(reason=f'Account age is less than {Functions.format_seconds(account_age_min)}.')
                await Functions.send_logging_message(member=member, kind='account_too_young')
            except discord.Forbidden:
                pass
            return

        c.execute('INSERT INTO processing_joined VALUES (?, ?, ?)', (guild_id, member.id, int(time.time())))
        conn.commit()

        member_anzahl = len(member.guild.members)
        welcome_embed = discord.Embed(
            title='👋 Willkommen',
            description=f'Willkommen auf dem Server {member.guild.name}, {member.mention}!\nWir sind nun {member_anzahl} Member.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        welcome_embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        welcome_embed.set_thumbnail(url=member.avatar.url if member.avatar else '')

        if welcome_channel:
            channel = await Functions.get_or_fetch('channel', welcome_channel)
            if channel:
                try:
                    await channel.send(embed=welcome_embed)
                except Exception as e:
                    program_logger.error(f"Error while sending welcome message: {e}")

    async def on_member_remove(member: discord.Member):
        c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (member.guild.id, member.id,))

        member_anzahl = len(member.guild.members)
        leave_embed = discord.Embed(
            title='👋 Auf Wiedersehen',
            description=f'{member.mention} hat den Server verlassen.\nWir sind nun {member_anzahl} Member.',
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        leave_embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        leave_embed.set_thumbnail(url=member.avatar.url if member.avatar else '')

        guild = c.execute("SELECT leave_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (member.guild.id,)).fetchone()
        if guild is not None:
            channel = await Functions.get_or_fetch('channel', guild[0])
            try:
                await channel.send(embed=leave_embed)
            except Exception as e:
                program_logger.error(f"Error while sending leave message: {e}")

        #Close open tickets
        c.execute('SELECT ARCHIVE_CHANNEL_ID FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (member.guild.id,))
        archive_channel_id = c.fetchone()[0]
        if archive_channel_id is None:
            return
        archive_channel: discord.TextChannel = await Functions.get_or_fetch('channel', archive_channel_id)

        c.execute('SELECT `CHANNEL_ID`, `CATEGORY` FROM `CREATED_TICKETS` WHERE `USER_ID` = ?', (member.id,))
        open_tickets = c.fetchall()
        for entry in open_tickets:
            transcript = await TicketTranscript.create_transcript(channel_id=entry[0], creator_id=member.id)
            try:
                await archive_channel.send(content=f'Kategorie: {entry[1]}\nUser: <@{member.id}>', file=discord.File(transcript))
            except Exception as e:
                program_logger.warning(f"Transcript couldn't be send to archive. -> {e}")

            os.remove(transcript)
            c.execute('DELETE FROM CREATED_TICKETS WHERE CHANNEL_ID = ?', (entry[0],))
            try:
                ticket_channel = await Functions.get_or_fetch('channel', entry[0])
                await ticket_channel.delete()
            except (discord.NotFound, discord.Forbidden):
                continue
            except Exception as e:
                program_logger.warning(f"Couldn't delete ticket channel -> {e}")
        conn.commit()


class aclient(discord.AutoShardedClient):
    def __init__(self):

        intents = discord.Intents.default()
        intents.members = True
        intents.dm_messages = True
        intents.message_content = True
        intents.guild_messages = True

        super().__init__(owner_id = OWNERID,
                              intents = intents,
                              status = discord.Status.invisible,
                              auto_reconnect = True
                        )
        self.synced = False
        self.initialized = False
        self.captcha_timeout = []
        self.message_cache = {}

    class Presence():
        @staticmethod
        def get_activity() -> discord.Activity:
            with open(ACTIVITY_FILE) as f:
                data = json.load(f)
                activity_type = data['activity_type']
                activity_title = data['activity_title']
                activity_url = data['activity_url']
            if activity_type == 'Playing':
                return discord.Game(name=activity_title)
            elif activity_type == 'Streaming':
                return discord.Streaming(name=activity_title, url=activity_url)
            elif activity_type == 'Listening':
                return discord.Activity(type=discord.ActivityType.listening, name=activity_title)
            elif activity_type == 'Watching':
                return discord.Activity(type=discord.ActivityType.watching, name=activity_title)
            elif activity_type == 'Competing':
                return discord.Activity(type=discord.ActivityType.competing, name=activity_title)

        @staticmethod
        def get_status() -> discord.Status:
            with open(ACTIVITY_FILE) as f:
                data = json.load(f)
                status = data['status']
            if status == 'online':
                return discord.Status.online
            elif status == 'idle':
                return discord.Status.idle
            elif status == 'dnd':
                return discord.Status.dnd
            elif status == 'invisible':
                return discord.Status.invisible

    async def setup_hook(self):
        global owner, shutdown
        shutdown = False
        try:
            owner = await self.fetch_user(OWNERID)
            if owner is None:
                program_logger.critical(f"Fehlerhafte OwnerID: {OWNERID}")
                sys.exit(f"Fehlerhafte OwnerID: {OWNERID}")
        except discord.HTTPException as e:
            program_logger.critical(f"Fehler bei dem Finden des Owners: {e}")
            sys.exit(f"Fehler bei dem Finden des Owners: {e}")
        discord_logger.info(f'Angemeldet als {bot.user} (ID: {bot.user.id})')
        discord_logger.info('Synchronisierung...')
        await tree.sync()
        discord_logger.info('Synchronisiert.')
        self.synced = True
        #Background shit
        bot.loop.create_task(Tasks.update_embeds_task())
        bot.loop.create_task(Tasks.CheckGameDuration())
        bot.loop.create_task(Tasks.CheckFreeGames())
        bot.loop.create_task(Tasks.check_team())
        bot.loop.create_task(Tasks.health_server())
        bot.loop.create_task(Tasks.process_latest_joined())
        bot.loop.create_task(Tasks.check_and_process_temp_bans())

    async def on_ready(self):
        await bot.change_presence(activity = self.Presence.get_activity(), status = self.Presence.get_status())
        if self.initialized:
            return
        await pvoice.add_listener()
        await pvoice.start_garbage_collector()
        bot.loop.create_task(stat_dock.task())
        global start_time
        start_time = datetime.datetime.now(datetime.UTC)
        program_logger.info(f"Fertig geladen in {time.time() - startupTime_start:.2f} Sekunden.")
        self.initialized = True
bot = aclient()
bot.on_message = DiscordEvents.on_message
bot.on_message_edit = DiscordEvents.on_message_edit
bot.on_app_command_error = DiscordEvents.on_app_command_error
bot.on_member_remove = DiscordEvents.on_member_remove
bot.on_member_join = DiscordEvents.on_member_join
bot.on_guild_remove = DiscordEvents.on_guild_remove
bot.on_member_update = DiscordEvents.on_member_update
bot.on_message_delete = DiscordEvents.on_message_delete
bot.on_guild_role_update = DiscordEvents.on_guild_role_update
bot.on_guild_role_delete = DiscordEvents.on_guild_role_delete
bot.on_guild_role_create = DiscordEvents.on_guild_role_create
bot.on_guild_channel_delete = DiscordEvents.on_guild_channel_delete
bot.on_guild_channel_create = DiscordEvents.on_guild_channel_create
bot.on_guild_update = DiscordEvents.on_guild_update
bot.on_guild_channel_update = DiscordEvents.on_guild_channel_update
bot.on_guild_join = DiscordEvents.on_guild_join
bot.on_interaction = DiscordEvents.on_interaction
tree = discord.app_commands.CommandTree(bot)
tree.on_error = bot.on_app_command_error


context_commands.setup(tree)

stat_dock.setup(tree=tree, connection=conn, client=bot, logger=program_logger)
pvoice.setup(tree=tree, connection=conn, client=bot, logger=program_logger)
supdater.setup(client=bot, tree=tree, server_ip=GAMESERVER_IP, api_token=PANEL_API_KEY, sshKey_pw=SSHKEY_PW, logger=program_logger)
TicketTranscript = TicketHTML(bot=bot, buffer_folder=BUFFER_FOLDER)

class SignalHandler:
    def __init__(self):
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        program_logger.info('Signal für das Herunterfahren erhalten...')
        bot.loop.create_task(Owner.shutdown(owner))

if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



class Functions():
    def format_seconds(seconds):
        years, remainder = divmod(seconds, 31536000)
        days, remainder = divmod(remainder, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if years:
            parts.append(f"{years}y")
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    def create_captcha():
        captcha_text = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        data = image_captcha.generate(captcha_text)
        return io.BytesIO(data.read()), captcha_text

    def load_teams():
        try:
            with open(f'teams.json', 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except Exception as e:
            program_logger.error(f'Fehler beim laden der Teams: {e}')
            return {}

    async def auto_publish(message: discord.Message):
        channel = message.channel
        permissions = channel.permissions_for(channel.guild.me)
        if permissions.add_reactions:
            await message.add_reaction("\U0001F4E2")
        if permissions.send_messages and permissions.manage_messages:
            try:
                await message.publish()
            except Exception as e:
                if not message.flags.crossposted:
                    discord_logger.error(f"Error publishing message in {channel}: {e}")
                    if permissions.add_reactions:
                        await message.add_reaction("\u26A0")
            finally:
                await message.remove_reaction("\U0001F4E2", bot.user)
        else:
            discord_logger.warning(f"No permission to publish in {channel}.")
            await message.remove_reaction("\U0001F4E2", bot.user)
            if permissions.add_reactions:
                await message.add_reaction("\u26D4")

    async def verify(interaction: discord.Interaction):
        class CaptchaInput(discord.ui.Modal, title='Verification'):
            def __init__(self):
                super().__init__()
                self.verification_successful = False

            answer = discord.ui.TextInput(
                label='Please enter the captcha text:',
                placeholder='Captcha text',
                min_length=6,
                max_length=6,
                style=discord.TextStyle.short,
                required=True
            )

            async def on_submit(self, interaction: discord.Interaction):
                if self.answer.value.upper() == captcha_text:
                    try:
                        await interaction.user.add_roles(interaction.guild.get_role(int(verified_role_id)))
                        await Functions.send_logging_message(interaction=interaction, kind='verify_success')
                        await interaction.response.edit_message(content='You have successfully verified yourself.', view=None)
                        c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (interaction.guild.id, interaction.user.id))
                        conn.commit()
                    except discord.Forbidden:
                        await interaction.response.edit_message(content='I do not have the permission to add the verified role.', view=None)
                    except discord.errors.NotFound:
                        pass
                    if interaction.user.id in bot.captcha_timeout:
                        bot.captcha_timeout.remove(interaction.user.id)
                    self.verification_successful = True
                else:
                    await Functions.send_logging_message(interaction=interaction, kind='verify_fail')
                    await interaction.response.edit_message(content='The captcha text you entered is incorrect.', view=None)

        captcha_input = CaptchaInput()

        class SubmitButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label='Enter Captcha', custom_id='captcha_submit', style=discord.ButtonStyle.blurple)

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.send_modal(captcha_input)

        class SubmitView(discord.ui.View):
            def __init__(self, *, timeout=60):
                super().__init__(timeout=timeout)
                self.add_item(SubmitButton())

            async def on_timeout(self):
                if not captcha_input.verification_successful:
                    self.clear_items()
                    await interaction.edit_original_response(content='Captcha timed out. Request a new one.', view=None)
                    if interaction.user.id in bot.captcha_timeout:
                        bot.captcha_timeout.remove(interaction.user.id)

        # Load verify_role from db
        c.execute('SELECT verify_role FROM servers WHERE guild_id = ?', (interaction.guild_id,))
        verified_role_id = c.fetchone()
        if not verified_role_id:
            await interaction.response.send_message('No verified role set. Please contact the server administrator.', ephemeral=True)
            return
        verified_role_id = verified_role_id[0]

        # Test if user already has the role
        if interaction.guild.get_role(int(verified_role_id)) in interaction.user.roles:
            await interaction.response.send_message('You are already verified.', ephemeral=True)
            return

        await Functions.send_logging_message(interaction=interaction, kind='verify_start')
        captcha_picture, captcha_text = Functions.create_captcha()

        bot.captcha_timeout.append(interaction.user.id)
        await interaction.response.send_message(
            'Please verify yourself to gain access to this server.\n\n**Captcha:**',
            file=discord.File(captcha_picture, filename='captcha.png'),
            view=SubmitView(),
            ephemeral=True
        )

    async def send_logging_message(interaction: discord.Interaction = None, member: discord.Member = None, kind: str = '', mass_amount: int = 0):
        guild_id = interaction.guild_id if interaction else member.guild.id
        c.execute('SELECT log_channel, ban_time, account_age_min FROM servers WHERE guild_id = ?', (guild_id,))
        row = c.fetchone()
        if not row:
            return
        log_channel_id, ban_time, account_age = row
        if not log_channel_id:
            return

        log_channel = (interaction.guild if interaction else member.guild).get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(timestamp=datetime.datetime.now(datetime.UTC))
        if kind == 'verify_start':
            embed.title = 'Captcha sent'
            embed.description = f'User {interaction.user.mention} requested a new captcha.'
            embed.color = discord.Color.blurple()
        elif kind == 'verify_success':
            embed.title = 'Verification successful'
            embed.description = f'User {interaction.user.mention} successfully verified.'
            embed.color = discord.Color.green()
        elif kind == 'verify_fail':
            embed.title = 'Wrong captcha'
            embed.description = f'User {interaction.user.mention} entered a wrong captcha.'
            embed.color = discord.Color.red()
        elif kind == 'verify_kick':
            embed.title = 'Time limit reached'
            embed.color = discord.Color.red()
            embed.add_field(name='User', value=member.mention)
            embed.add_field(name='Action', value='Kick')
        elif kind == 'verify_ban':
            embed.title = 'Time limit reached'
            embed.color = discord.Color.red()
            embed.add_field(name='User', value=member.mention)
            embed.add_field(name='Action', value='Ban')
            if ban_time:
                embed.add_field(name='Duration', value=f'{Functions.format_seconds(ban_time)}')
        elif kind == 'verify_mass_started':
            embed.title = 'Mass verification started'
            embed.description = f'Mass verification started by {interaction.user.mention}.'
            embed.color = discord.Color.blurple()
        elif kind == 'verify_mass_success':
            embed.title = 'Mass verification successful'
            embed.description = f'{interaction.user.mention} successfully applied the verified role to {mass_amount} users.'
            embed.color = discord.Color.green()
        elif kind == 'unban':
            embed.title = 'Unban'
            embed.description = f'User {member.mention} was unbanned.'
            embed.color = discord.Color.green()
        elif kind == 'account_too_young':
            embed.title = 'Account too young'
            embed.description = f'User {member.mention} was kicked because their account is younger than {Functions.format_seconds(account_age)}.'
            embed.color = discord.Color.orange()
        elif kind == 'user_verify':
            embed.title = 'User verified'
            embed.description = f'User {member.mention} was verified by {interaction.user.mention}.'
            embed.color = discord.Color.green()

        try:
            await log_channel.send(embed=embed)
        except discord.errors.Forbidden:
            pass
        finally:
            program_logger.debug(f'Sent logging message in {log_channel.guild.name} ({log_channel.guild.id}) with type {kind}.')

    async def get_or_fetch(item: str, item_id: int) -> Optional[Any]:
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

        get_method = getattr(bot, get_method_name, None)
        fetch_method = getattr(bot, fetch_method_name, None)

        if get_method is None or fetch_method is None:
            raise AttributeError(f"Methods {get_method_name} or {fetch_method_name} not found on bot object.")

        item_object = get_method(item_id)
        if item_object is None:
            try:
                item_object = await fetch_method(item_id)
            except discord.NotFound:
                pass
        return item_object

    async def send_update_serverpanel(entry_id: tuple, channel: discord.TextChannel, update: bool = False, message_on_update: discord.Message = None):
        host, port = entry_id[2], entry_id[3]
        embed = discord.Embed(
            description=f"**IP:** {host}:{port}",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        try:
            server_info = await a2s.ainfo((host, port))
            embed.title = server_info.server_name
            embed.url = f'{STEAM_REDIRECT_URL}?ip={host}&port={port}'
            embed.color = discord.Color.brand_green()
            embed.add_field(name="Gamemode", value=server_info.game, inline=True)
            embed.add_field(name="Version", value=server_info.version, inline=True)
            embed.add_field(name="Ping", value=f"{server_info.ping * 1000:.1f}ms", inline=True)
            embed.add_field(name="Aktuelle Spieler", value=server_info.player_count, inline=True)
            embed.add_field(name="Maximale Spieler", value=server_info.max_players, inline=True)
            embed.add_field(name="Map", value=server_info.map_name, inline=True)
        except Exception:
            embed.title = message_on_update.embeds[0].title if update and message_on_update and message_on_update.embeds else "Unknown Server"
            embed.color = discord.Color.red()
            for field in ["Gamemode", "Version", "Ping", "Aktuelle Spieler", "Maximale Spieler", "Map"]:
                embed.add_field(name=field, value="N/A", inline=True)

        guild_image = channel.guild.icon.url if channel.guild.icon else 'https://cdn.cloudflare.steamstatic.com/steam/apps/4000/header.jpg'
        embed.set_thumbnail(url=guild_image)
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        if update:
            try:
                await message_on_update.edit(embed=embed)
                return True
            except discord.NotFound:
                return False
        else:
            message = await channel.send(embed=embed)
            return message.id

    async def GetSteamAppInfo() -> list:
        try:
            games = await steam_api.GetFreePromotions()
        except steam_errors.NotOK as e:
            program_logger.error(f'Error getting free games from Steam: {e}')
            return []

        async def fetch_game_info(game):
            game_info = await SteamAPI.get_app_details(game)
            if game_info:
                return {
                    'id': game,
                    'title': game_info[game]['data']['name'],
                    'description': game_info[game]['data']['short_description']
                }
            else:
                program_logger.debug(f'Game not found: {game}')
                return None

        tasks = [fetch_game_info(game) for game in games]
        results = await asyncio.gather(*tasks)

        data = [result for result in results if result]
        program_logger.debug(data)
        return data

    async def update_team_embed(guild):
        teams_data = Functions.load_teams()
        embeds = []

        for team in teams_data["teams"]:
            role: discord.Role = guild.get_role(team["role_id"])
            if role and role.members:
                members = '\n'.join(member.mention for member in role.members)

                embed = discord.Embed(
                    title=role.name,
                    description=members,
                    color=discord.Color.dark_orange(),
                    timestamp=datetime.datetime.now(datetime.UTC)
                )

                embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

                if role.icon:
                    embed.set_thumbnail(url=role.icon.url)

                embeds.append(embed)

        return embeds

    async def check_message(message: discord.Message):
        if await Functions.isSpamming(message):
            embed = discord.Embed(
                title="User got timeouted",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=bot.user.display_name, icon_url=message.guild.icon.url)

            if message.author.is_timed_out():
                return

            try:
                await message.author.timeout(datetime.timedelta(minutes=5), reason="Spamming")
                embed.description = f"Der Nutzer {message.author.mention} wurde für 5 Minuten getimeouted, da er zu schnell schreibt."
            except discord.Forbidden:
                embed.description = f"Der Nutzer {message.author.mention} konnte nicht getimeouted werden, da ich keine Rechte dazu habe."

            row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (message.guild.id,)).fetchone()
            if row:
                channel = await Functions.get_or_fetch('channel', row[0])
                if channel:
                    await channel.send(embed=embed)

            try:
                await message.delete()
            except discord.NotFound:
                pass

    async def isSpamming(message: discord.Message) -> bool:
        author = message.author
        if author.bot:
            return False

        user_id = author.id
        current_time = message.created_at.timestamp()

        # Cache the user's message times
        message_times = bot.message_cache.setdefault(user_id, [])

        # Remove old messages (older than 10 seconds)
        message_times[:] = [msg_time for msg_time in message_times if current_time - msg_time < 10]

        message_times.append(current_time)

        return len(message_times) >= 5

    async def isAdminOrSupport(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True

        supportRoleIdentifier = interaction.channel.category.name.upper().replace('TICKET-', 'SUPPORT_ROLE_ID_')
        c.execute(f'SELECT {supportRoleIdentifier} FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild.id,))
        support_role_id = c.fetchone()

        if not support_role_id:
            return False

        support_role = interaction.guild.get_role(int(support_role_id[0]))
        return support_role in interaction.user.roles if support_role else False


class Tasks():
    async def update_embeds_task():
        async def _function():
            c.execute("SELECT * FROM EMBEDS")
            entries = c.fetchall()
            to_delete = []
            for entry in entries:
                channel = await Functions.get_or_fetch('channel', entry[2])
                if channel is None:
                    to_delete.append(entry[0])
                    continue
                try:
                    message = await channel.fetch_message(entry[3])
                except discord.NotFound:
                    to_delete.append(entry[0])
                    continue
                c.execute("SELECT * FROM SERVER WHERE ID = ?", (entry[4],))
                server = c.fetchone()
                if server is None:
                    to_delete.append(entry[0])
                    continue
                panel = await Functions.send_update_serverpanel(server, channel, update=True, message_on_update=message)
                if not panel:
                    to_delete.append(entry[0])
                    program_logger.error(f"Fehler beim Updaten des Panels: {panel}")
            if to_delete:
                c.executemany("DELETE FROM EMBEDS WHERE ID = ?", [(id,) for id in to_delete])
                conn.commit()

        while not bot.initialized:
            await asyncio.sleep(5)
        while True:
            await _function()
            try:
                await asyncio.sleep(60*3)
            except asyncio.CancelledError:
                break

    async def CheckFreeGames():
        async def _fetch_games(platform):
            if platform == "epic":
                return epic_games_api.GetFreeGames()
            elif platform == "steam":
                return await Functions.GetSteamAppInfo()

        async def _get_game_details(game, platform):
            if platform == "epic":
                return {
                    "title": game['title'],
                    "url": game['link'],
                    "image_url": game['picture'],
                    "description": game['description'],
                    "id": game['id']
                }
            elif platform == "steam":
                return {
                    "title": game['title'],
                    "url": f'https://store.steampowered.com/app/{game["id"]}',
                    "image_url": f'https://cdn.cloudflare.steamstatic.com/steam/apps/{game["id"]}/header.jpg',
                    "description": game['description'],
                    "id": game['id']
                }

        async def _function(platform):
            try:
                c.execute("SELECT free_games_channel FROM GUILD_SETTINGS")
                data = c.fetchall()
                if not data:
                    return

                channels = [await Functions.get_or_fetch('channel', row[0]) for row in data]
                channels = [channel for channel in channels if channel]

                if not channels:
                    program_logger.warning("Kein Channel gefunden.")
                    return

                try:
                    new_games = await _fetch_games(platform)
                except Exception as e:
                    program_logger.error(f"Fehler beim Abrufen der {platform.capitalize()} Games: {e}")
                    return

                embeds = []
                for game in new_games:
                    c.execute("SELECT 1 FROM free_games WHERE TITEL_ID = ?", (game['id'],))
                    if c.fetchone() is not None:
                        continue

                    game_details = await _get_game_details(game, platform)
                    if "mysterygame" in game_details['title'].lower().replace(' ', ''):
                        continue

                    embed = discord.Embed(
                        title=game_details['title'],
                        url=game_details['url'],
                        color=discord.Color.dark_gold(),
                        timestamp=datetime.datetime.now(datetime.UTC)
                    )
                    embed.set_image(url=game_details['image_url'])
                    embed.add_field(name='Titel', value=game_details['title'], inline=False)
                    embed.add_field(name='Beschreibung', value=game_details['description'], inline=False)
                    embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
                    embeds.append(embed)
                    c.execute("INSERT INTO free_games (TITEL_ID, DATUM) VALUES (?, ?)", (game['id'], int(time.time())))

                conn.commit()
                if embeds:
                    for channel in channels:
                        await channel.send(embeds=embeds)

            except Exception as e:
                program_logger.error(f"Fehler beim Senden der {platform.capitalize()} Games: {e}")

        while not bot.initialized:
            await asyncio.sleep(5)
        while True:
            await _function("epic")
            await _function("steam")
            try:
                await asyncio.sleep(60 * 30)
            except asyncio.CancelledError:
                break

    async def CheckGameDuration():
        async def _function():
            ten_days_ago = int(time.time()) - 86400*10

            c.execute("SELECT * FROM free_games WHERE DATUM < ?", (ten_days_ago,))
            old_entries = c.fetchall()

            for entry in old_entries:
                entry_id = entry[2]
                c.execute("DELETE FROM free_games WHERE DATUM = ?", (entry_id,))
                conn.commit()

        while not bot.initialized:
            await asyncio.sleep(5)
        while True:
            await _function()
            try:
                await asyncio.sleep(60*60*24)
            except asyncio.CancelledError:
                break

    async def check_team():
        async def _function():
            c.execute('SELECT GUILD_ID, team_list_channel FROM `GUILD_SETTINGS`')
            data = c.fetchall()

            for entry in data:
                try:
                    guild = bot.get_guild(entry[0])
                    if not guild:
                        continue

                    embeds = await Functions.update_team_embed(guild)
                    if not embeds:
                        continue

                    channel = await Functions.get_or_fetch('channel', entry[1])
                    if not channel:
                        continue

                    last_message = None
                    async for message in channel.history(limit=1):
                        if message.author == bot.user and message.embeds:
                            last_message = message
                            break

                    if last_message:
                        await last_message.edit(embeds=embeds)
                    else:
                        await channel.send(embeds=embeds)
                except Exception as e:
                    program_logger.error(f"Fehler beim Senden des Team Embeds: {e}")

        while not bot.initialized:
            await asyncio.sleep(5)
        while True:
            await _function()
            try:
                await asyncio.sleep(60 * 60)
            except asyncio.CancelledError:
                break

    async def health_server():
        async def __health_check(request):
            return web.Response(text="Healthy")

        app = web.Application()
        app.router.add_get('/health', __health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 5000)
        try:
            await site.start()
        except OSError as e:
            program_logger.warning(f'Error while starting health server: {e}')

    async def process_latest_joined():
        while not shutdown:
            current_time = int(time.time())
            for guild in bot.guilds:
                try:
                    c.execute('SELECT timeout, verify_role, action, ban_time FROM servers WHERE guild_id = ?', (guild.id,))
                    server = c.fetchone()
                    if not server:
                        continue
                    timeout, verified_role_id, action, ban_time = server
                    c.execute('SELECT user_id FROM processing_joined WHERE guild_id = ? AND (join_time + ?) < ?', (guild.id, timeout, current_time))
                    rows = c.fetchall()
                    if not rows:
                        continue
                    verified_role = guild.get_role(verified_role_id)
                    if not verified_role:
                        continue
                    for user_id, in rows:
                        member = guild.get_member(user_id)
                        if not member:
                            try:
                                member = await guild.fetch_member(user_id)
                            except discord.NotFound:
                                pass
                        if not member or verified_role in member.roles:
                            c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (guild.id, user_id))
                            continue
                        if action == 'kick':
                            try:
                                await member.kick(reason='Did not successfully verify in time.')
                                await Functions.send_logging_message(member=member, kind='verify_kick')
                                program_logger.debug(f'Kicked {member} from {guild}.')
                            except discord.Forbidden:
                                program_logger.debug(f'Could not kick {member} from {guild}.')
                        elif action == 'ban':
                            try:
                                await member.ban(reason=f'Did not successfully verify in time. Banned for {Functions.format_seconds(ban_time)}' if ban_time else 'Did not successfully verify in time.')
                                if ban_time:
                                    c.execute('INSERT INTO temp_bans VALUES (?, ?, ?)', (guild.id, member.id, current_time + ban_time))
                                await Functions.send_logging_message(member=member, kind='verify_ban')
                                program_logger.debug(f'Banned {member} from {guild}.')
                            except discord.Forbidden:
                                program_logger.debug(f'Could not ban {member} from {guild}.')
                        c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (guild.id, user_id))
                except Exception as e:
                    program_logger.error(f'Error processing guild {guild.id}: {e}')
            conn.commit()
            try:
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break

    async def check_and_process_temp_bans():
        while not shutdown:
            current_time = time.time()
            c.execute('SELECT * FROM temp_bans WHERE unban_time < ?', (current_time,))
            temp_bans = c.fetchall()
            for temp_ban in temp_bans:
                guild_id, user_id, _ = temp_ban
                try:
                    guild = bot.get_guild(guild_id)
                    if guild is None:
                        c.execute('DELETE FROM temp_bans WHERE guild_id = ?', (guild_id,))
                        continue
                    member = bot.get_user(user_id)
                    if member is None:
                        try:
                            member = await bot.fetch_user(user_id)
                        except discord.NotFound:
                            c.execute('DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
                            continue
                    c.execute('SELECT log_channel FROM servers WHERE guild_id = ?', (guild_id,))
                    log_channel_id = c.fetchone()[0]
                    log_channel = guild.get_channel(log_channel_id)
                    if log_channel is None:
                        try:
                            log_channel = await guild.fetch_channel(log_channel_id)
                        except discord.HTTPException:
                            log_channel = None
                    try:
                        await guild.unban(member, reason='Temporary ban expired.')
                        embed = discord.Embed(title='Unban', description=f'User {member.mention} was unbanned.', color=discord.Color.green())
                        embed.timestamp = datetime.datetime.now(datetime.UTC)
                        program_logger.debug(f'Unbanned {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                        c.execute('DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
                        if log_channel:
                            try:
                                await log_channel.send(embed=embed)
                            except discord.Forbidden:
                                program_logger.debug(f'Could not send unban log message in {guild.name} ({guild.id}).')
                    except discord.Forbidden:
                        program_logger.debug(f'Could not unban {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                except Exception as e:
                    conn.commit()
                    program_logger.error(f'Error processing temp ban: {e}')
                    continue

            conn.commit()
            try:
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break


class Owner():
    async def log(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'log [current/folder/lines] (Replace lines with a positive number, if you only want lines.) - Get the log\n'
                                       '```')
        if not args:
            await __wrong_selection()
            return

        command = args[0]
        if command == 'current':
            log_file_path = f'{LOG_FOLDER}{BOT_NAME}.log'
            try:
                await message.channel.send(file=discord.File(log_file_path))
            except discord.HTTPException as err:
                if err.status == 413:
                    zip_path = f'{BUFFER_FOLDER}Logs.zip'
                    with ZipFile(zip_path, mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as zip_file:
                        zip_file.write(log_file_path)
                    try:
                        await message.channel.send(file=discord.File(zip_path))
                    except discord.HTTPException as err:
                        if err.status == 413:
                            await message.channel.send("The log is too big to be sent directly.\nYou have to look at the log in your server (VPS).")
                    os.remove(zip_path)
            return

        if command == 'folder':
            zip_path = f'{BUFFER_FOLDER}Logs.zip'
            if os.path.exists(zip_path):
                os.remove(zip_path)
            with ZipFile(zip_path, mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as zip_file:
                for file in os.listdir(LOG_FOLDER):
                    if not file.endswith(".zip"):
                        zip_file.write(f'{LOG_FOLDER}{file}')
            try:
                await message.channel.send(file=discord.File(zip_path))
            except discord.HTTPException as err:
                if err.status == 413:
                    await message.channel.send("The folder is too big to be sent directly.\nPlease get the current file or the last X lines.")
            os.remove(zip_path)
            return

        try:
            lines = int(command)
            if lines < 1:
                await __wrong_selection()
                return
        except ValueError:
            await __wrong_selection()
            return

        log_file_path = f'{LOG_FOLDER}{BOT_NAME}.log'
        buffer_file_path = f'{BUFFER_FOLDER}log-lines.txt'
        with open(log_file_path, 'r', encoding='utf8') as log_file:
            log_lines = log_file.readlines()[-lines:]
        with open(buffer_file_path, 'w', encoding='utf8') as buffer_file:
            buffer_file.writelines(log_lines)
        await message.channel.send(content=f'Here are the last {len(log_lines)} lines of the current logfile:', file=discord.File(buffer_file_path))
        os.remove(buffer_file_path)

    async def activity(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'activity [playing/streaming/listening/watching/competing] [title] (url) - Set the activity of the bot\n'
                                       '```')
        def isURL(zeichenkette):
            try:
                ergebnis = urlparse(zeichenkette)
                return all([ergebnis.scheme, ergebnis.netloc])
            except:
                return False

        def remove_and_save(liste):
            if liste and isURL(liste[-1]):
                return liste.pop()
            else:
                return None

        if args == []:
            await __wrong_selection()
            return
        action = args[0].lower()
        url = remove_and_save(args[1:])
        title = ' '.join(args[1:])
        program_logger.debug(title)
        program_logger.debug(url)
        with open(ACTIVITY_FILE, 'r', encoding='utf8') as f:
            data = json.load(f)
        if action == 'playing':
            data['activity_type'] = 'Playing'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'streaming':
            data['activity_type'] = 'Streaming'
            data['activity_title'] = title
            data['activity_url'] = url
        elif action == 'listening':
            data['activity_type'] = 'Listening'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'watching':
            data['activity_type'] = 'Watching'
            data['activity_title'] = title
            data['activity_url'] = ''
        elif action == 'competing':
            data['activity_type'] = 'Competing'
            data['activity_title'] = title
            data['activity_url'] = ''
        else:
            await __wrong_selection()
            return
        with open(ACTIVITY_FILE, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=2)
        await bot.change_presence(activity = bot.Presence.get_activity(), status = bot.Presence.get_status())
        await message.channel.send(f'Activity set to {action} {title}{" " + url if url else ""}.')

    async def status(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'status [online/idle/dnd/invisible] - Set the status of the bot\n'
                                       '```')

        if args == []:
            await __wrong_selection()
            return
        action = args[0].lower()
        with open(ACTIVITY_FILE, 'r', encoding='utf8') as f:
            data = json.load(f)
        if action == 'online':
            data['status'] = 'online'
        elif action == 'idle':
            data['status'] = 'idle'
        elif action == 'dnd':
            data['status'] = 'dnd'
        elif action == 'invisible':
            data['status'] = 'invisible'
        else:
            await __wrong_selection()
            return
        with open(ACTIVITY_FILE, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=2)
        await bot.change_presence(activity = bot.Presence.get_activity(), status = bot.Presence.get_status())
        await message.channel.send(f'Status set to {action}.')

    async def shutdown(message):
        global shutdown
        _message = 'Engine powering down...'
        program_logger.info(_message)
        try:
            await message.channel.send(_message)
        except:
            await owner.send(_message)
        await bot.change_presence(status=discord.Status.invisible)
        shutdown = True

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        await bot.close()



@tree.command(name = 'ping', description = 'Test, if the bot is responding.')
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.user.id))
async def self(interaction: discord.Interaction):
    before = time.monotonic()
    await interaction.response.send_message('Pong!')
    ping = (time.monotonic() - before) * 1000
    await interaction.edit_original_response(content=f'Command ausführ Zeit: `{int(ping)}ms`\nPing zum Gateway: `{int(bot.latency * 1000)}ms`')

@tree.command(name = 'setup', description = 'Setup the bot.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, welcome_channel: discord.TextChannel, leave_channel: discord.TextChannel, logging_channel: discord.TextChannel, announce_channel: discord.TextChannel, team_update: discord.TextChannel, free_games_channel: discord.TextChannel, team_list_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    guild_id = interaction.guild.id
    channels = (welcome_channel.id, leave_channel.id, logging_channel.id, announce_channel.id, team_update.id, free_games_channel.id, team_list_channel.id)

    c.execute("SELECT 1 FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (guild_id,))
    guild_exists = c.fetchone() is not None

    if not guild_exists:
        c.execute('INSERT OR REPLACE INTO GUILD_SETTINGS (GUILD_ID, welcome_channel, leave_channel, logging_channel, announce_channel, team_update_channel, free_games_channel, team_list_channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (guild_id, *channels))
        conn.commit()
        embed = discord.Embed(
            title='✅ Erfolgreich',
            description='Die Konfiguration wurde erfolgreich gespeichert.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        embed.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.edit_original_response(embed=embed)
    else:
        embed = discord.Embed(
            title='⚠️ Warnung',
            description='Es existiert bereits ein Eintrag für diesen Server. Möchtest du ihn ersetzen?',
            color=discord.Color.yellow()
        )
        embed.set_footer(text='Reagiere mit ✅ um den Eintrag zu ersetzen.')
        warning_message = await interaction.channel.send(embed=embed)
        await asyncio.sleep(2)
        await warning_message.add_reaction('✅')

        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) == '✅' and reaction.message.id == warning_message.id

        try:
            reaction, user = await interaction.client.wait_for('reaction_add', timeout=60.0, check=check)
            if reaction.emoji == '✅':
                c.execute('INSERT OR REPLACE INTO GUILD_SETTINGS (GUILD_ID, welcome_channel, leave_channel, logging_channel, announce_channel, team_update_channel, free_games_channel, team_list_channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (guild_id, *channels))
                conn.commit()
                await interaction.channel.send('✅ Eintrag erfolgreich ersetzt.')
                await warning_message.delete()
        except asyncio.TimeoutError:
            await interaction.channel.send('❌ Zeit abgelaufen.')

@tree.command(name='clear', description='Clears the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_messages=True)
@discord.app_commands.describe(amount='Amount of messages to delete.')
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    try:
        await interaction.channel.purge(limit=amount)
        clear_eb = discord.Embed(
            title='✅ Clear',
            description=f'{amount} Nachrichten wurden gelöscht.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        clear_eb.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=clear_eb)
    except Exception as e:
        error_eb = discord.Embed(
           title='❌ Fehler',
           description='Die Menge muss eine Zahl sein.' if isinstance(e, ValueError) else str(e),
           color=discord.Color.red(),
           timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        error_eb.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=error_eb)

@tree.command(name='lock', description='Locks the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_channels=True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    send_messages_permission = interaction.channel.permissions_for(interaction.guild.default_role).send_messages
    description = 'Der Chat ist bereits gesperrt.' if not send_messages_permission else 'Der Chat wurde gesperrt.'
    color = discord.Color.red() if not send_messages_permission else discord.Color.green()

    if send_messages_permission:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)

    lock_eb = discord.Embed(
        title='🔒 Lock',
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    lock_eb.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    await interaction.followup.send(embed=lock_eb)

@tree.command(name='unlock', description='Unlocks the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_channels=True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    send_messages_permission = interaction.channel.permissions_for(interaction.guild.default_role).send_messages
    description = 'Der Chat ist bereits entsperrt.' if send_messages_permission else 'Der Chat wurde entsperrt.'
    color = discord.Color.red() if send_messages_permission else discord.Color.green()

    if not send_messages_permission:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=None)

    unlock_eb = discord.Embed(
        title='🔓 Unlock',
        description=description,
        color=color,
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    unlock_eb.set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    await interaction.followup.send(embed=unlock_eb)

@tree.command(name='kick', description='Kicks a user.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(kick_members=True)
@discord.app_commands.describe(user='User to kick.',
                               reason='Reason for the kick.'
                               )
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.defer(ephemeral=True)
    user_mention = user.mention
    bot_avatar_url = bot.user.avatar.url if bot.user.avatar else ''
    timestamp = datetime.datetime.now(datetime.UTC)

    kick_eb = discord.Embed(
        title='⚔️ Kick',
        description=f'{user_mention} wurde gekickt.\nGrund: {reason}',
        color=discord.Color.green(),
        timestamp=timestamp
    ).set_footer(text=bot.user.display_name, icon_url=bot_avatar_url)

    user_notify = discord.Embed(
        title='⚔️ Kick',
        description=f'Du wurdest gekickt.\nGrund: {reason}',
        color=discord.Color.dark_orange(),
        timestamp=timestamp
    ).add_field(name="Ausführendes Teammitglied", value=interaction.user.mention)\
     .add_field(name="Grund", value=reason)\
     .add_field(name="Server", value=interaction.guild)\
     .set_footer(text=bot.user.display_name, icon_url=bot_avatar_url)

    try:
        await user.send(embed=user_notify)
    except discord.Forbidden:
        pass

    await interaction.guild.kick(user, reason=reason)
    await interaction.followup.send(embed=kick_eb)

@tree.command(name='ban_id', description='Bans a user by there id.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(ban_members=True)
@discord.app_commands.describe(user_id='User ID to ban.',
                               reason='Reason for the ban.'
                               )
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, user_id: int, reason: str):
    await interaction.response.defer(ephemeral=True)
    try:
        user = await bot.fetch_user(user_id)
    except discord.NotFound:
        await interaction.followup.send(content='User not found.', ephemeral=True)
        return

    ban_eb = discord.Embed(
        title='🔨 Ban',
        description=f'{user.mention} wurde gebannt.\nGrund: {reason}',
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    ).set_footer(text=bot.user.display_name, icon_url=bot.user.avatar.url if bot.user.avatar else '')

    await interaction.guild.ban(user, reason=reason)
    await interaction.followup.send(embed=ban_eb)

@tree.command(name = 'register_server', description = 'register a Server')
@discord.app_commands.checks.cooldown(2, 30, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(host='ip address of the server.',
                               port='server port.'
                               )
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, host: str, port: int):
    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT ID FROM SERVER WHERE GUILD = ? AND HOST = ? AND PORT = ?", (interaction.guild_id, host, port))
    server = c.fetchone()
    if server is not None:
        await interaction.followup.send(content="Error: Server already registered.", ephemeral=True)
    else:
        c.execute("INSERT INTO SERVER (GUILD, HOST, PORT) VALUES (?, ?, ?)", (interaction.guild_id, host, port))
        conn.commit()
        server_id = c.lastrowid
        await interaction.followup.send(content=f"Server registered successfully.\nYou can now use `/send_panel_server` with ID {server_id}, to send it to a channel.", ephemeral=True)

@tree.command(name = 'send_panel_server', description = 'send the panel into a channel.')
@discord.app_commands.checks.cooldown(2, 30, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(entry_id='panel id.',
                               channel='In which channel the panel should be send.'
                               )
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, entry_id: int, channel: discord.TextChannel):
    async def _panel_send():
        c.execute("SELECT * FROM SERVER WHERE ID = ?", (entry_id,))
        entry = c.fetchone()
        if entry is None:
            await interaction.followup.send(content=f"Error: Server with ID {entry_id} not found.", ephemeral=True)
            return
        if entry[1] != interaction.guild_id:
            await interaction.followup.send(content=f"Error: Server with ID {entry_id} is not registered for this guild.", ephemeral=True)
            return
        panel = await Functions.send_update_serverpanel(entry, channel)
        if not isinstance(panel, int):
            await interaction.followup.send(content=f"Error: Panel could not be sent.", ephemeral=True)
            return
        c.execute("INSERT INTO EMBEDS (GUILD, CHANNEL, MESSAGE_ID, SERVER_ID) VALUES (?, ?, ?, ?)", (interaction.guild_id, channel.id, panel, entry_id))
        conn.commit()
        await interaction.followup.send(content=f"Panel sent successfully.", ephemeral=True)

    perms = channel.permissions_for(interaction.guild.me)
    needed_permissions = ['send_messages', 'embed_links', 'read_message_history', 'view_channel']
    missing_permissions = [perm for perm in needed_permissions if not getattr(perms, perm)]
    if missing_permissions:
        await interaction.response.send_message(content=f"I need the following permissions to send the panel: {', '.join(missing_permissions)}.\nYou can also give me Admin.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM EMBEDS WHERE GUILD = ? AND CHANNEL = ? AND SERVER_ID = ?", (interaction.guild_id, channel.id, entry_id))
    message_id = c.fetchone()
    if message_id is None:
        await _panel_send()
    else:
        try:
            await channel.fetch_message(message_id[3])
        except discord.NotFound:
            c.execute("DELETE FROM EMBEDS WHERE GUILD = ? AND CHANNEL = ? AND SERVER_ID = ?", (interaction.guild_id, channel.id, entry_id))
            conn.commit()
            await _panel_send()
        else:
            await interaction.followup.send(content=f"Error: Panel already exists in channel.", ephemeral=True)

@tree.command(name = 'list_servers', description = 'list of all registered servers.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    c.execute("SELECT ID, HOST, PORT FROM SERVER WHERE GUILD = ?", (interaction.guild_id,))
    servers = c.fetchall()
    if not servers:
        await interaction.response.send_message(content="Keine Server in der Datenbank gefunden.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Registrierte Server für {interaction.guild.name}",
        color=discord.Color.blue()
    )

    for i, server in enumerate(servers[:25]):
        embed.add_field(name=f"ID: {server[0]}", value=f"IP: {server[1]}:{server[2]}", inline=False)

    if len(servers) > 25:
        embed.set_footer(text=f"Nur 25/{len(servers)} Server werden aufgeführt.")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name = 'unregister_server', description = 'remove a server.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(entry_id='id of the panel from the server which should be removed')
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, entry_id: int):
    c.execute("SELECT * FROM SERVER WHERE ID = ? AND GUILD = ?", (entry_id, interaction.guild_id))
    entry = c.fetchone()
    if entry is None:
        await interaction.response.send_message(content=f"Error: Server with ID {entry_id} not found in the database or not registered for this guild.", ephemeral=True)
    else:
        c.execute("DELETE FROM SERVER WHERE ID = ?", (entry_id,))
        c.execute("DELETE FROM EMBEDS WHERE SERVER_ID = ?", (entry_id,))
        conn.commit()
        await interaction.response.send_message(content=f"Server with ID {entry_id} successfully removed.", ephemeral=True)

@tree.command(name='create_ticketsystem', description='creates the ticketsystem.')
@discord.app_commands.checks.cooldown(1, 2, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator=True)
@discord.app_commands.describe(channel='In which channel the ticketsystem should be.',
                               archive='In which channel the transcript should be send.'
                              )
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, channel: discord.TextChannel, archive: discord.TextChannel):
    class TicketDropdown(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(label="Discord", description="Für allgemeine Hilfe im Discord."),
                discord.SelectOption(label="Report", description="Melde einen Nutzer auf dem Discord."),
                discord.SelectOption(label="Support", description="Für technische Hilfe."),
                discord.SelectOption(label="Bug", description="Falls du einen Bug gefunden hast."),
                discord.SelectOption(label="Feedback", description="Falls du Feedback an HRP hast."),
                discord.SelectOption(label="Entbannung", description="Wenn du einen Entbannungsantrag stellen möchtest."),
                discord.SelectOption(label="Putschantrag", description="Wenn du einen Putschantrag stellen möchtest."),
                discord.SelectOption(label="Sonstiges", description="Für alles andere."),
            ]
            super().__init__(placeholder="Wähle ein Ticket-Thema aus.", options=options, min_values=1, max_values=1, custom_id="support_menu")

    class TicketSystemView(discord.ui.View):
        def __init__(self):
            super().__init__()
            self.add_item(TicketDropdown())

    await interaction.response.defer(ephemeral=True)

    bot_avatar = bot.user.avatar.url if bot.user.avatar else ''
    ticketsystem_embed = discord.Embed(
        title='Ticket System',
        description='Hier kannst du ein Ticket erstellen. Wähle unten eine Kategorie aus.',
        color=discord.Color.purple()
    )
    ticketsystem_embed.set_footer(text=bot.user.display_name, icon_url=bot_avatar)

    c.execute('SELECT 1 FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild_id,))
    if c.fetchone():
        await interaction.response.send_message(content='[ERROR] Ticketsystem wurde schon erstellt.', ephemeral=True)
        return

    try:
        async def get_or_create_role(guild, name):
            role = discord.utils.get(guild.roles, name=name)
            if role is None:
                role = await guild.create_role(name=name, permissions=discord.Permissions.none())
            return role

        roles = await asyncio.gather(
            get_or_create_role(interaction.guild, "Support-Discord"),
            get_or_create_role(interaction.guild, "Support-Report"),
            get_or_create_role(interaction.guild, "Support-Support"),
            get_or_create_role(interaction.guild, "Support-Bug"),
            get_or_create_role(interaction.guild, "Support-Feedback"),
            get_or_create_role(interaction.guild, "Support-Entbannung"),
            get_or_create_role(interaction.guild, "Support-Putschantrag"),
            get_or_create_role(interaction.guild, "Support-Sonstiges")
        )

        c.execute(
            'INSERT INTO TICKET_SYSTEM (GUILD_ID, CHANNEL, ARCHIVE_CHANNEL_ID, SUPPORT_ROLE_ID_SUPPORT, SUPPORT_ROLE_ID_REPORT, SUPPORT_ROLE_ID_DISCORD, SUPPORT_ROLE_ID_BUG, SUPPORT_ROLE_ID_FEEDBACK, SUPPORT_ROLE_ID_SONSTIGES, SUPPORT_ROLE_ID_ENTBANNUNG, SUPPORT_ROLE_ID_PUTSCHANTRAG) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                interaction.guild_id,
                channel.id,
                archive.id,
                roles[2].id,  # support_role
                roles[1].id,  # report_role
                roles[0].id,  # discord_role
                roles[3].id,  # bug_role
                roles[4].id,  # feedback_role
                roles[7].id,  # sonstiges_role
                roles[5].id,  # entbannung_role
                roles[6].id   # putschantrag_role
            )
        )
        conn.commit()
        await channel.send(embed=ticketsystem_embed, view=TicketSystemView())
        await interaction.followup.send(content='Ticketsystem wurde erfolgreich erstellt.')
    except Exception as e:
        text = f"Ticketsystem konnte nicht erstellt werden. -> {e}"
        program_logger.warning(text)
        await interaction.followup.send(text)

@tree.command(name = 'remove_ticketsystem', description = 'removes the ticket channel.')
@discord.app_commands.checks.cooldown(1, 120, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM TICKET_SYSTEM WHERE GUILD_ID = ?", (interaction.guild_id,))
    guild = c.fetchone()
    if guild is None:
        await interaction.followup.send(content='[ERROR] Der Ticket Channel wurde noch nicht gesetzt.', ephemeral=True)
        return

    support_role_columns = [
        "SUPPORT_ROLE_ID_SUPPORT", "SUPPORT_ROLE_ID_REPORT", "SUPPORT_ROLE_ID_DISCORD",
        "SUPPORT_ROLE_ID_BUG", "SUPPORT_ROLE_ID_FEEDBACK", "SUPPORT_ROLE_ID_SONSTIGES",
        "SUPPORT_ROLE_ID_ENTBANNUNG", "SUPPORT_ROLE_ID_PUTSCHANTRAG"
    ]

    for column in support_role_columns:
        c.execute(f"SELECT {column} FROM TICKET_SYSTEM WHERE {column} IS NOT NULL")
        role_ids = c.fetchall()
        for role_id, in role_ids:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await role.delete(reason="TICKET_SYSTEM wird gelöscht.")
                except discord.DiscordException as e:
                    program_logger.warning(f"Rolle konnte nicht gelöscht werden. -> {e}")

    c.execute("DELETE FROM TICKET_SYSTEM WHERE GUILD_ID = ?", (interaction.guild_id,))
    conn.commit()
    await interaction.followup.send(content='Ticket Channel wurde erfolgreich entfernt.', ephemeral=True)

@tree.command(name = 'verify_send_pannel', description = 'Send panel to verification channel.')
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    class CaptchaView(discord.ui.View):
        def __init__(self, *, timeout=None):
            super().__init__(timeout=timeout)
            self.add_item(discord.ui.Button(label='🤖 Verify', style=discord.ButtonStyle.blurple, custom_id='verify'))
            self.add_item(discord.ui.Button(label='Why?', style=discord.ButtonStyle.blurple, custom_id='why'))

    c.execute('SELECT verify_channel, timeout, action, ban_time FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if not data:
        await interaction.followup.send('The verification channel is not set. Please set it with `/setup`.', ephemeral=True)
        return

    verify_channel_id, timeout, action, ban_time = data
    timeout = int(timeout / 60)

    try:
        verify_channel = await bot.fetch_channel(verify_channel_id)
    except (discord.NotFound, discord.Forbidden):
        await interaction.followup.send(f'I don\'t have permission to see the verification channel (<#{verify_channel_id}>).', ephemeral=True)
        return

    embed = discord.Embed(title=':robot: Verification required', color=0x2b63b0)
    action_text = {
        'ban': f"you'll be banned{f' for {Functions.format_seconds(ban_time)}' if ban_time else ''}, if you do not verify yourself within {timeout} minutes",
        'kick': f"you'll be kicked, if you do not verify yourself within {timeout} minutes",
        None: "",
    }[action]
    embed.description = f"To proceed to `{interaction.guild.name}`, we kindly ask you to confirm your humanity by solving a captcha. Simply click the button below to get started!"
    if action_text:
        embed.description += f"\n\nPlease note that {action_text}."

    c.execute('SELECT panel_id FROM panels WHERE guild_id = ?', (interaction.guild_id,))
    panel_id = c.fetchone()
    if panel_id:
        try:
            await verify_channel.fetch_message(panel_id[0])
            await interaction.followup.send('The verification panel already exists.\nTo update it, you have to first delete the old one.', ephemeral=True)
            return
        except (discord.NotFound, discord.Forbidden):
            pass

    try:
        panel = await verify_channel.send(embed=embed, view=CaptchaView())
    except discord.Forbidden:
        await interaction.followup.send(f'I don\'t have permission to send messages in the verification channel (<#{verify_channel_id}>).', ephemeral=True)
        return

    c.execute('INSERT OR REPLACE INTO panels VALUES (?, ?)', (interaction.guild_id, panel.id))
    conn.commit()
    await interaction.followup.send(f'The verification panel has been sent to <#{verify_channel_id}>.', ephemeral=True)

@tree.command(name = 'verify_setup', description = 'Setup the server for the bot.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.describe(verify_channel = 'Channel for the verification message.',
                               verify_role = 'Role assigned after successfull verification.',
                               log_channel = 'Channel used to send logs.',
                               timeout = 'After that timeframe the action gets executed.',
                               action = 'Action that gets executed after timeout.',
                               ban_time = 'Time a user gets banned for if action is ban. Leave empty for perma ban. (1d / 1h / 1m / 1s)',
                               account_age = 'Account age required to join the server.'
                               )
@discord.app_commands.choices(timeout = [
    discord.app_commands.Choice(name = '5 Minutes', value = 300),
    discord.app_commands.Choice(name = '10 Minutes', value = 600),
    discord.app_commands.Choice(name = '15 Minutes', value = 900),
    discord.app_commands.Choice(name = '20 Minutes', value = 1200),
    discord.app_commands.Choice(name = '25 Minutes', value = 1500),
    discord.app_commands.Choice(name = '30 Minutes', value = 1800)
    ],
                            action = [
    discord.app_commands.Choice(name = 'Kick', value = 'kick'),
    discord.app_commands.Choice(name = 'Ban', value = 'ban'),
    discord.app_commands.Choice(name = 'Nothing', value = '')
    ])
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction, verify_channel: discord.TextChannel, verify_role: discord.Role, log_channel: discord.TextChannel, timeout: int, action: str, ban_time: str = None, account_age: str = None):
    guild_me = interaction.guild.me
    if action == 'kick' and not guild_me.guild_permissions.kick_members:
        await interaction.response.send_message(f'I need the permission to {action} members.', ephemeral=True)
        return
    elif action == 'ban' and not guild_me.guild_permissions.ban_members:
        await interaction.response.send_message(f'I need the permission to {action} members.', ephemeral=True)
        return

    if action == '':
        action = None

    if not verify_channel.permissions_for(guild_me).send_messages:
        await interaction.response.send_message(f'I need the permission to send messages in {verify_channel.mention}.', ephemeral=True)
        return

    if guild_me.top_role <= verify_role:
        await interaction.response.send_message(f'My highest role needs to be above {verify_role.mention}, so I can assign it.', ephemeral=True)
        return

    bot_permissions = log_channel.permissions_for(guild_me)
    if not bot_permissions.view_channel:
        await interaction.response.send_message(f'I need the permission to see {log_channel.mention}.', ephemeral=True)
        return
    if not (bot_permissions.send_messages and bot_permissions.embed_links):
        await interaction.response.send_message(f'I need the permission to send messages and embed links in {log_channel.mention}.', ephemeral=True)
        return

    if ban_time:
        ban_time = timeparse(ban_time)
        if ban_time is None:
            await interaction.response.send_message('Invalid ban time. Please use the following format: `1d / 1h / 1m / 1s`.\nFor example: `1d2h3m4s`', ephemeral=True)
            return

    if account_age:
        if not guild_me.guild_permissions.kick_members:
            await interaction.response.send_message(f'I need the permission to kick members.', ephemeral=True)
            return
        account_age = timeparse(account_age)
        if account_age is None:
            await interaction.response.send_message('Invalid account age. Please use the following format: `1d / 1h / 1m / 1s`.\nFor example: `1d2h3m4s`', ephemeral=True)
            return

    c.execute('INSERT OR REPLACE INTO servers VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (interaction.guild.id, verify_channel.id, verify_role.id, log_channel.id, timeout, action, ban_time, account_age))
    conn.commit()
    await interaction.response.send_message(f'Setup completed.\nYou can now run `/send_panel`, to send the panel to <#{verify_channel.id}>.', ephemeral=True)

@tree.command(name = 'verify_einstellungen', description = 'Zeige die aktuellen Einstellungen.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    c.execute('SELECT verify_channel, verify_role, log_channel, timeout, action, ban_time, account_age_min FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if data:
        verify_channel, verify_role, log_channel, timeout, action, ban_time, account_age = data
        embed = discord.Embed(
            title='Current settings',
            description=(
                f'**Verify Channel:** <#{verify_channel}>\n'
                f'**Verify Role:** <@&{verify_role}>\n'
                f'**Log Channel:** <#{log_channel}>\n'
                f'**Timeout:** {Functions.format_seconds(timeout)}\n'
                f'**Action:** {action}\n'
                f'**Banned for:** {Functions.format_seconds(ban_time) if ban_time else "None"}\n'
                f'**Min account age:** {Functions.format_seconds(account_age) if account_age else "None"}'
            ),
            color=0x2b63b0
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        await interaction.response.send_message('There are no settings for this server.\nUse `/setup` to set-up this server.', ephemeral=True)

@tree.command(name = 'verify-all', description = 'Verify all non-bot users on the server.')
@discord.app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
@discord.app_commands.guild_only
async def self(interaction: discord.Interaction):
    c.execute('SELECT verify_role FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if not data:
        await interaction.response.send_message('There are no settings for this server.\nUse `/setup` to set-up this server.', ephemeral=True)
        return

    verify_role_id = data[0]
    if not verify_role_id:
        await interaction.response.send_message('The verify role does not exist.', ephemeral=True)
        return

    verify_role = interaction.guild.get_role(verify_role_id)
    if not verify_role:
        await interaction.response.send_message('The verify role does not exist.', ephemeral=True)
        return

    await interaction.response.send_message('Verifying all users on the server. This can take a while.', ephemeral=True)
    await Functions.send_logging_message(interaction=interaction, kind='verify_mass_started')

    members_to_verify = [member for member in interaction.guild.members if not member.bot and verify_role not in member.roles]
    for member in members_to_verify:
        try:
            await member.add_roles(verify_role, reason='Verify all users on the server.')
        except discord.Forbidden:
            continue

    await Functions.send_logging_message(interaction=interaction, kind='verify_mass_success', mass_amount=len(members_to_verify))
    await interaction.edit_original_response(content=f'{interaction.user.mention}\nVerified {len(members_to_verify)} users on the server.')

@tree.context_menu(name="Verify User")
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id, i.data['target_id']))
@discord.app_commands.checks.has_permissions(manage_roles=True)
@discord.app_commands.guild_only
async def verify_user(interaction: discord.Interaction, member: discord.Member):
    c.execute('SELECT verify_role FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    verify_role_id = c.fetchone()

    if not verify_role_id:
        await interaction.response.send_message('There are no settings for this server.\nUse `/setup` to set-up this server.', ephemeral=True)
        return

    verify_role = interaction.guild.get_role(verify_role_id[0])
    if not verify_role:
        await interaction.response.send_message('The verify role does not exist.', ephemeral=True)
        return

    if member.bot or verify_role in member.roles:
        await interaction.response.send_message(f'{member.mention} is already verified or is a bot.', ephemeral=True)
        return

    try:
        await member.add_roles(verify_role, reason=f'{interaction.user.name} verified user via context menu.')
        await interaction.response.send_message(f'{member.mention} got verified by {interaction.user.mention}.', ephemeral=True)
        await Functions.send_logging_message(interaction=interaction, kind='user_verify', member=member)
    except discord.Forbidden:
        await interaction.response.send_message('I do not have permission to add roles to this user.', ephemeral=True)



if __name__ == '__main__':
    if sys.version_info < (3, 11):
        program_logger.critical('Python 3.11 or higher is required.')
        sys.exit(1)
    if not TOKEN:
        error_message = 'Missing token. Please check your .env file.'
        program_logger.critical(error_message)
        sys.exit(error_message)
    else:
        try:
            SignalHandler()
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure:
            error_message = 'Invalid token. Please check your .env file.'
            program_logger.critical(error_message)
            sys.exit(error_message)
        except asyncio.CancelledError:
            if shutdown:
                pass
