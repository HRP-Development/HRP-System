# -*- coding: utf-8 -*-
#Import

# Badwords check currently disabled! Enable in check_message()

# Todo: • Abmeldungen für TB
#       • Private Sprachchannel

import time
startupTime_start = time.time()
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
from CustomModules.bad_words import BadWords
from CustomModules import context_commands
from CustomModules.ticket import TicketHTML
from CustomModules import epic_games_api
from CustomModules import stat_dock

from aiohttp import web
from rcon import source
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
FOOTER_TEXT = 'HRP | System'
os.makedirs(f'{APP_FOLDER_NAME}//Logs', exist_ok=True)
os.makedirs(f'{APP_FOLDER_NAME}//Buffer', exist_ok=True)
LOG_FOLDER = f'{APP_FOLDER_NAME}//Logs//'
BUFFER_FOLDER = f'{APP_FOLDER_NAME}//Buffer//'
ACTIVITY_FILE = f'{APP_FOLDER_NAME}//activity.json'
SQL_FILE = os.path.join(APP_FOLDER_NAME, f'{BOT_NAME}.db')
BOT_VERSION = "1.6.1"
BadWords = BadWords()

TOKEN = os.getenv('TOKEN')
OWNERID = os.getenv('OWNER_ID')
LOG_LEVEL = os.getenv('LOG_LEVEL')
STEAM_API_KEY = os.getenv('STEAM_API_KEY')
STEAM_REDIRECT_URL = os.getenv('STEAM_REDIRECT_URL')
    
#Init sentry
sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    traces_sample_rate=1.0,
    profiles_sample_rate=1.0,
    environment='Production',
    release=f'HRP-System@{BOT_VERSION}'
)

log_manager = log_handler.LogManager(LOG_FOLDER, BOT_NAME, LOG_LEVEL)
discord_logger = log_manager.get_logger('discord')
program_logger = log_manager.get_logger('Program')
program_logger.info('Starte Discord Bot...')

SteamAPI = steam_api.API(STEAM_API_KEY)

LUA_COMMANDS = {
    "GetIPAddress": "print(game.GetIPAddress())",
    "GetMap": "print(game.GetMap())",
    "CurrentPlayers": "print(#player.GetAll())",
    "MaxPlayers": "print(game.MaxPlayers())",
    "GetHostName": "print(GetHostName())",
    "ActiveGamemode": "print(engine.ActiveGamemode())"
}

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
            user = self.user_id_input.value
            try:
                user = await Functions.get_or_fetch('user', int(user))
                await self.channel.set_permissions(user, read_messages=True, send_messages=True, read_message_history=True, embed_links=True, attach_files=True)
                await interaction.response.send_message(f'{user.mention} wurde zum Ticket hinzugefügt.', ephemeral=True)
            except ValueError:
                await interaction.response.send_message(content="Die ID darf ausschließlich aus Zahlen bestehen!", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f'Fehler beim Hinzufügen eines Nutzers zu einem Ticket: {e}', ephemeral=True)
                
    class _RemoveUserModal(discord.ui.Modal):
        def __init__(self, channel):
            super().__init__(title="Benutzer zum entfernen des Tickets")
            self.channel = channel
    
            self.user_id_input = discord.ui.TextInput(
                label='Benutzer-ID',
                placeholder='Benutzer-ID',
                min_length=17,
                max_length=21
            )
            self.add_item(self.user_id_input)
        
        async def on_submit(self, interaction: discord.Interaction):
            user = self.user_id_input.value
            try:
                user = await Functions.get_or_fetch('user', int(user))
                if user == interaction.user:
                    await interaction.response.send_message(f'Du kannst dich nicht selbst entfernen.', ephemeral=True)
                    return
                await self.channel.set_permissions(user, read_messages=False, send_messages=False, read_message_history=False)
                await interaction.response.send_message(f'{user.mention} wurde vom Ticket entfernt.', ephemeral=True)
            except ValueError:
                await interaction.response.send_message(content="Die ID darf ausschließlich aus Zahlen bestehen!", ephemeral=True)
                return
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
            #Check for existing Ticket
            c.execute('SELECT * FROM CREATED_TICKETS WHERE USER_ID = ? AND GUILD_ID = ? AND CATEGORY = ?', (interaction.user.id, interaction.guild.id, self.category))
            data = c.fetchone()
            if data is not None:
                channel = await Functions.get_or_fetch('channel', int(data[2]))
                if channel is not None:
                    await interaction.response.send_message(content=f"Du hast bereits ein offenes Ticket für die Kategorie {self.category}.: <#{data[2]}>\nDu kannst nur ein Ticket pro Kategorie zur selben Zeit offen haben.", ephemeral=True)
                    return
                else:
                    c.execute('DELETE FROM CREATED_TICKETS WHERE USER_ID = ? AND GUILD_ID = ? AND CATEGORY = ?', (interaction.user.id, interaction.guild.id, self.category))
                    conn.commit()
    
            title = self.title_input.value
            description = self.description_input.value
            category = discord.utils.get(interaction.guild.categories, name=f'Ticket-{self.category}')
    
            if category is None:
                category = await interaction.guild.create_category(f'Ticket-{self.category}')
    
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
                self.user: discord.PermissionOverwrite(read_messages=True, embed_links=True, attach_files=True)
            }
    
            c.execute('SELECT SUPPORT_ROLE_ID FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild.id,))
            support_role_id = c.fetchone()[0]
            if support_role_id is not None:
                support_role: discord.Role = interaction.guild.get_role(int(support_role_id))
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
            admin_embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    
            close_button = discord.ui.Button(label="✅ Schließen", style=discord.ButtonStyle.blurple, custom_id="close_ticket")
            add_button = discord.ui.Button(label="➕ Hinzufügen", style=discord.ButtonStyle.green, custom_id="add_ticket")
            remove_button = discord.ui.Button(label="➖ Entfernen", style=discord.ButtonStyle.red, custom_id="remove_ticket")
        
            admin_view = discord.ui.View()
            admin_view.add_item(close_button)
            admin_view.add_item(add_button)
            admin_view.add_item(remove_button)
            
            await ticket_channel.send(embed=admin_embed, view=admin_view)
            await ticket_channel.send(embed=ticket_embed)
            await ticket_channel.send(content=f"Hey listen <@&{support_role_id}>, es gibt ein neues Ticket.") # Wenn geändert, ändere Text in ticket.py, um vom Transcript auszunehmen.
            try:
                c.execute('INSERT INTO CREATED_TICKETS (USER_ID, CHANNEL_ID, GUILD_ID, CATEGORY) VALUES (?, ?, ?, ?)', (self.user.id, ticket_channel.id, interaction.guild.id, self.category))
                conn.commit()
                program_logger.debug(f'Ticket wurde erfolgreich erstellt ({self.user.id}, {ticket_channel.id}, {interaction.guild.id}, {self.category}).')
            except Exception as e:
                program_logger.error(f'Fehler beim einfügen in die Datenbank: {e}')
            await interaction.response.send_message(f'Dein Ticket wurde erstellt: {ticket_channel.mention}', ephemeral=True)
    
    async def on_interaction(interaction: discord.Interaction):
        if interaction.response.is_done():
            return
        if interaction.data and interaction.data.get('component_type') == 3: #3 ist Dropdown
            button_id = interaction.data.get('custom_id')
            if button_id == ("support_menu"):
                selected_value = interaction.data.get('values', [None])[0]
                program_logger.debug(f"Support Menu gewählt: {selected_value}")
                category = selected_value
                modal = DiscordEvents._TicketModal(category, interaction.user)
                await interaction.response.send_modal(modal)
                    
        elif interaction.data and interaction.data.get('component_type') == 2: #2 ist Button
            button_id = interaction.data.get('custom_id')
            if button_id == ("close_ticket"):
                isAdminOrSupport = await Functions.isAdminOrSupport(interaction)
                if not isAdminOrSupport:
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
        
                overwrite = discord.PermissionOverwrite()
                overwrite.send_messages = False 
                overwrite.add_reactions = False  
                overwrite.read_messages = False 
                await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        
                transcript = await TicketSystem.create_transcript(interaction.channel.id, data_created_tickets[1])
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
               
            elif button_id == ("add_ticket"):
                isAdminOrSupport = await Functions.isAdminOrSupport(interaction)
                if not isAdminOrSupport:
                    await interaction.response.send_message(content="Du hast nicht das Recht, diesen Button zu verwenden!", ephemeral=True)
                    return
        
                channel = interaction.channel
                modal = DiscordEvents._AddUserModal(channel)
                await interaction.response.send_modal(modal)
            elif button_id == ("remove_ticket"):
                isAdminOrSupport = await Functions.isAdminOrSupport(interaction)
                if not isAdminOrSupport:
                    await interaction.response.send_message(content="Du hast nicht das Recht, diesen Button zu verwenden!", ephemeral=True)
                    return
        
                channel = interaction.channel
                modal = DiscordEvents._RemoveUserModal(channel)
                await interaction.response.send_modal(modal)
            elif button_id == 'verify':
                if interaction.user.id in bot.captcha_timeout:
                    try:
                        await interaction.response.send_message('Bitte warte ein paar Sekunden.', ephemeral=True)
                    except discord.NotFound:
                        try:
                            await interaction.followup.send('Bitte warte ein paar Sekunden.', ephemeral=True)
                        except discord.NotFound:
                            pass
                    return
                else:
                    await Functions.verify(interaction)
                    return

    async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        options = interaction.data.get("options")
        option_values = ""
        if options:
            for option in options:
                option_values += f"{option['name']}: {option['value']}"
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await interaction.response.send_message(f'This command is on cooldown.\nTime left: `{str(datetime.timedelta(seconds=int(error.retry_after)))}`', ephemeral=True)
        else:
            try:
                try:
                    await interaction.response.send_message(f"Error! Try again.", ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(f"Error! Try again.", ephemeral=True)
                    except:
                        pass
            except discord.Forbidden:
                try:
                    await interaction.followup.send(f"{error}\n\n{option_values}", ephemeral=True)
                except discord.NotFound:
                    try:
                        await interaction.response.send_message(f"{error}\n\n{option_values}", ephemeral=True)
                    except discord.NotFound:
                        pass
                except Exception as e:
                    discord_logger.warning(f"Unexpected error while sending message: {e}")
            finally:
                try:
                    program_logger.warning(f"{error} -> {option_values} | Invoked by {interaction.user.name} ({interaction.user.id}) @ {interaction.guild.name} ({interaction.guild.id}) with Language {interaction.locale[1]}")
                except AttributeError:
                    program_logger.warning(f"{error} -> {option_values} | Invoked by {interaction.user.name} ({interaction.user.id}) with Language {interaction.locale[1]}")

    async def on_guild_join(guild: discord.Guild):
        if not bot.synced:
            return
        discord_logger.info(f'Ich wurde zu {guild} hinzugefügt. (ID: {guild.id})')

    async def on_guild_remove(guild):
        if not bot.synced:
            return
        program_logger.info(f'Ich wurde von {guild} gekickt. (ID: {guild.id})')

    async def on_guild_channel_update(before, after):
        if before.position != after.position and before.name == after.name:
            return

        embed = discord.Embed(
            title="🔧 Channel aktualisiert",
            description=f"Channel **{before.name}** wurde bearbeitet.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        if before.name != after.name:
           embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)
        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_guild_update(before, after):
        embed = discord.Embed(
            title="⚙️ Server-Einstellungen geändert",
            description=f"Der Server **{before.name}** hat Änderungen erfahren.",
            color=discord.Color.purple(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        if before.name != after.name:
            embed.add_field(name="Servername geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)
        if before.icon != after.icon:
            embed.add_field(name="Server-Icon geändert", value="Das Server-Icon wurde geändert", inline=False)
            embed.set_thumbnail(url=after.icon.url if after.icon else discord.Embed.Empty)
        if before.afk_timeout != after.afk_timeout:
            embed.add_field(name="AFK-Timeout geändert", value=f"Von **{before.afk_timeout//60} Minuten** zu **{after.afk_timeout//60} Minuten**", inline=False)
        if before.system_channel != after.system_channel:
            embed.add_field(name="System-Channel geändert", value=f"Von **{before.system_channel}** zu **{after.system_channel}**", inline=False)
        if before.premium_tier != after.premium_tier:
            embed.add_field(name="Boost-Level geändert", value=f"Von **Stufe {before.premium_tier}** zu **Stufe {after.premium_tier}**", inline=False)
        if before.premium_subscription_count != after.premium_subscription_count:
            embed.add_field(name="Anzahl der Server-Boosts geändert", value=f"Von **{before.premium_subscription_count}** zu **{after.premium_subscription_count}**", inline=False)
        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
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
        field_count = 1

        if overwrites:
            for entity, overwrite in overwrites.items():
                role_or_user = entity.name if isinstance(entity, discord.Role) else entity.display_name

                embed.add_field(name=f"Rollenüberschreibung für {role_or_user}", value="", inline=False)
                field_count += 1

                permissions = {
                    "read_messages": overwrite.read_messages,
                    "send_messages": overwrite.send_messages,
                    "manage_messages": overwrite.manage_messages,
                    "manage_channels": overwrite.manage_channels,
                    "embed_links": overwrite.embed_links,
                    "attach_files": overwrite.attach_files,
                    "add_reactions": overwrite.add_reactions,
                }

                permission_lines = []
                for perm, value in permissions.items():
                    if value:
                        permission_lines.append(f"{perm.replace('_', ' ').capitalize()}: {'✅' if value else '❌'}")

                if permission_lines:
                    embed.add_field(name="Berechtigungen:", value="\n".join(permission_lines), inline=False)
                    field_count += 1

                if field_count >= 24:
                    embed.add_field(name="Info", value="Zu viele Berechtigungen, um sie alle anzuzeigen.", inline=False)
                    break

        embed.add_field(name="Channel ID:", value=channel.id)
        field_count += 1

        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (channel.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_guild_channel_delete(channel):
        embed = discord.Embed(
            title="🗑️ Channel gelöscht",
            description=f"Channel **{channel.name}** wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (channel.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_guild_role_create(role):
        guild = role.guild
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

        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (role.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_guild_role_delete(role):
        embed = discord.Embed(
            title="➖ Rolle gelöscht",
            description=f"Rolle **{role.name}** wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (role.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_guild_role_update(before, after):
        if before.position != after.position and before.name == after.name:
            return
    
        embeds = []
    
        embed = discord.Embed(
            title="🔄 Rolle aktualisiert",
            description=f"Rolle **{before.name}** wurde aktualisiert.",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
    
        field_count = 0
        changes = []
    
        if before.name != after.name:
            embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)
            field_count += 1
    
        if before.color != after.color:
            embed.add_field(name="Farbe geändert", value=f"Von {before.color} zu {after.color}", inline=False)
            field_count += 1
    
        if before.mentionable != after.mentionable:
            embed.add_field(name="Erwähnbar geändert", value=f"Von {'Erwähnbar' if before.mentionable else 'Nicht erwähnbar'} zu {'Erwähnbar' if after.mentionable else 'Nicht erwähnbar'}", inline=False)
            field_count += 1
    
        before_permissions = before.permissions
        after_permissions = after.permissions
    
        for perm in dir(after_permissions):
            if not perm.startswith("_"):
                before_value = getattr(before_permissions, perm)
                after_value = getattr(after_permissions, perm)
    
                if before_value != after_value:
                    changes.append(f"**{perm.replace('_', ' ').capitalize()}**: {'✅' if after_value else '❌'}")
    
        if changes:
            for change in changes:
                if field_count >= 25:
                    embeds.append(embed)
                    embed = discord.Embed(
                        title="🔄 Rolle aktualisiert - Fortsetzung",
                        description=f"Änderungen für Rolle **{after.name}**",
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.now(datetime.timezone.utc)
                    )
                    field_count = 0
    
                embed.add_field(name="Berechtigungsänderung", value=change, inline=False)
                field_count += 1
    
        embeds.append(embed)
    
        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i + 10]
            embed_message = discord.Embed()
    
            for emb in batch:
                embed_message.add_field(name=emb.title, value=emb.description, inline=False)
    
            embed_message.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        
            try:
                if channel is not None:
                    await channel.send(embed=embed_message)
            except Exception as e:
                program_logger.error(f"Error while sending role update log: {e}")

    async def on_message_delete(message):
        embed = discord.Embed(
            title="🗑️ Nachricht gelöscht",
            description=f"Nachricht von {message.author.mention} wurde gelöscht.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        if message.content:
            embed.add_field(name="Inhalt", value=message.content, inline=False)
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        
        try:
            async for entry in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete):
                if entry.target.id == message.author.id and entry.extra.channel.id == message.channel.id:
                    embed.description = f"Nachricht von {message.author.mention} wurde durch {entry.user.mention} gelöscht."
                    break
        except Exception as e:
            program_logger.warning(f"Couldn't read the audit logs -> {e}")

        try:   
            row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (message.guild.id,)).fetchone()
            channel = await Functions.get_or_fetch('channel', row[0]) if row else None
            if channel is not None:
                await channel.send(embed=embed)
        except discord.Forbidden:
            program_logger.error(f"Missing permissions to read audit log in guild: {message.guild.id}")

    async def on_member_update(before, after):
        embed = discord.Embed(
            title="🔄 Mitglied aktualisiert",
            description=f"Änderungen an **{after.name}** (ID: {after.id})",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        
        changes = []

        if before.roles != after.roles:
            added_roles = [role for role in after.roles if role not in before.roles]
            removed_roles = [role for role in before.roles if role not in after.roles]
            
            if added_roles:
                changes.append(f"Hinzugefügt: {', '.join(role.name for role in added_roles)}")
            if removed_roles:
                changes.append(f"Entfernt: {', '.join(role.name for role in removed_roles)}")

        if before.nick != after.nick:
            changes.append(f"Nickname geändert: **{before.nick or 'kein Nickname'}** zu **{after.nick or 'kein Nickname'}**")

        if before.avatar != after.avatar:
            before_avatar = before.avatar.url if before.avatar else "kein Avatar"
            after_avatar = after.avatar.url if after.avatar else "kein Avatar"
            changes.append(f"Avatar geändert: [Vorher]({before_avatar}) zu [Nachher]({after_avatar})")

        if before.status != after.status:
            changes.append(f"Status geändert: **{before.status}** zu **{after.status}**")

        if before.activity != after.activity:
            before_activity = before.activity.name if before.activity else "keine"
            after_activity = after.activity.name if after.activity else "keine"
            changes.append(f"Aktivität geändert: **{before_activity}** zu **{after_activity}**")

        if changes:
            embed.add_field(name="Änderungen:", value="\n".join(changes), inline=False)
            row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.id,)).fetchone()
            channel = await Functions.get_or_fetch('channel', row[0]) if row else None
            if channel is not None:
                await channel.send(embed=embed)

    async def on_message(message):
        async def __wrong_selection():
            await message.channel.send(
                  '```'
                  'Commands:\n'
                  'hilfe - Zeigt diese Nachricht.\n'
                  'log - Gibt dir denn Log.\n'
                  'activity - Setzt die Aktivität des Bots.\n'
                  'status - Setzt denn Status des Bots.\n'
                  'shutdown - Fährt denn Bot herunter.\n'
                  '```'
            )

        if message.guild is None and message.author.id == int(OWNERID):
            args = message.content.split(' ')
            program_logger.debug(args)
            command, *args = args
            if command == 'hilfe':
                await __wrong_selection()
                return
            elif command == 'log':
                await Owner.log(message, args)
                return
            elif command == 'activity':
                await Owner.activity(message, args)
                return
            elif command == 'status':
                await Owner.status(message, args)
                return
            elif command == 'shutdown':
                await Owner.shutdown(message)
                return
            else:
                await __wrong_selection()
        
        if message.author.bot:
            return
        if message.guild is None:
            return

        await Functions.check_message(message)

    async def on_message_edit(before, after):
        if before.content == after.content or before.author.bot:
            return

        embed = discord.Embed(
            title="Nachricht wurde bearbeitet.",
            color=0x2f3136,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.set_author(name=after.author.nick if after.author.nick is not None else after.author.name, icon_url=after.author.avatar.url)
        embed.description = (f"✏️ **Nachricht von** {after.author.mention} **wurde in** {after.channel.mention} **bearbeitet**.\n[Jump to Message]({after.jump_url})")
        embed.add_field(name="Alt", value=f"```{before.content}```" or "*(N/A)*", inline=False)
        embed.add_field(name="Neu", value=f"```{after.content}```" or "*(N/A)*", inline=False)

        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

        row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (after.guild.id,)).fetchone()
        channel = await Functions.get_or_fetch('channel', row[0]) if row else None
        if channel is not None:
            await channel.send(embed=embed)

    async def on_member_join(member: discord.Member):
        def account_age_in_seconds(member: discord.Member) -> int:
            now = datetime.datetime.now(datetime.UTC)
            created = member.created_at
            age = now - created
            return age.total_seconds()
        
        if not bot.initialized or member.bot:
            return
        #Fetch account_age_min from DB and kick user if account age is less than account_age_min
        c.execute('SELECT account_age_min FROM servers WHERE guild_id = ?', (member.guild.id,))
        result = c.fetchone()
        if result is None or result[0] is None:
            return
        account_age_min = result[0]
        if account_age_in_seconds(member) < account_age_min:
            try:
                await member.kick(reason=f'Account age is less than {Functions.format_seconds(account_age_min)}.')
                await Functions.send_logging_message(member = member, kind = 'account_too_young')
                return
            except discord.Forbidden:
                return
        else:
            program_logger.debug(f'Account age is greater than {Functions.format_seconds(account_age_min)}.')

        c.execute('SELECT action FROM servers WHERE guild_id = ?', (member.guild.id,))
        result = c.fetchone()
        if result is None or result[0] is None:
            return
        c.execute('INSERT INTO processing_joined VALUES (?, ?, ?)', (member.guild.id, member.id, int(time.time(),)))
        conn.commit()

        member_anzahl = len(member.guild.members) 
        welcome_embed = discord.Embed(
            title='👋 Willkommen',
            description=f'Willkommen auf dem Server {member.guild.name}, {member.mention}!\nWir sind nun {member_anzahl} Member.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        welcome_embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        welcome_embed.set_thumbnail(url=member.avatar.url if member.avatar else '')
    
        guild = c.execute("SELECT welcome_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (member.guild.id,)).fetchone()
        if guild is not None:
            channel = await Functions.get_or_fetch('channel', guild[0])
            try:
                await channel.send(embed=welcome_embed)
            except Exception as e:
                program_logger.error(f"Error while sending welcome message: {e}")

    async def on_member_remove(member: discord.Member):
        c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (member.guild.id, member.id,))
        conn.commit()

        member_anzahl = len(member.guild.members)
        leave_embed = discord.Embed(
            title='👋 Auf Wiedersehen',
            description=f'{member.mention} hat den Server verlassen.\nWir sind nun {member_anzahl} Member.',
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        leave_embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        leave_embed.set_thumbnail(url=member.avatar.url if member.avatar else '')
    
        guild = c.execute("SELECT leave_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (member.guild.id,)).fetchone()
        if guild is not None:
            channel = await Functions.get_or_fetch('channel', guild[0])
            try:
                await channel.send(embed=leave_embed)
            except Exception as e:
                   program_logger.error(f"Error while sending leave message: {e}")

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
TicketSystem = TicketHTML(bot=bot, buffer_folder=BUFFER_FOLDER)

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
    
    async def verify(interaction: discord.Interaction):
        class CaptchaInput(discord.ui.Modal, title = 'Verification'):
            def __init__(self):
                super().__init__()
                self.verification_successful = False

            answer = discord.ui.TextInput(label = 'Bitte gebe denn Captcha Code ein:', placeholder = 'Captcha text', min_length = 6, max_length = 6, style = discord.TextStyle.short, required = True)

            async def on_submit(self, interaction: discord.Interaction):
                if self.answer.value.upper() == captcha_text:
                    try:
                        await interaction.user.add_roles(interaction.guild.get_role(int(verified_role_id)))
                        await Functions.send_logging_message(interaction = interaction, kind = 'verify_success')
                        await interaction.response.edit_message(content = 'Du hast dich erfolgreich Verifiziert.', view = None)
                        c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (interaction.guild.id, interaction.user.id,))
                        conn.commit()
                    except discord.Forbidden:
                        await interaction.response.edit_message(content = 'Ich habe keine Rechte um dich zu Verifizieren.', view = None)
                    except discord.errors.NotFound:
                        pass
                    if interaction.user.id in bot.captcha_timeout:
                        bot.captcha_timeout.remove(interaction.user.id)
                    self.verification_successful = True
                else:
                    await Functions.send_logging_message(interaction = interaction, kind = 'verify_fail')
                    await interaction.response.edit_message(content = 'Dein eingegebener Code ist ungültig.', view = None)
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
                    self.remove_item(SubmitButton())
                    await interaction.edit_original_response(content = 'Captcha timed out. Request a new one.', view = None)
                    if interaction.user.id in bot.captcha_timeout:
                        bot.captcha_timeout.remove(interaction.user.id)

        c.execute(f'SELECT verify_role FROM servers WHERE guild_id = {interaction.guild_id}')
        try:
            verified_role_id = c.fetchone()[0]
        except TypeError:
            await interaction.response.send_message('Es wurde keine Rolle zum Verifizieren gesetzt.', ephemeral = True)
            return

        if interaction.guild.get_role(int(verified_role_id)) in interaction.user.roles:
            await interaction.response.send_message('Du bist bereits Verifiziert.', ephemeral = True)
            return

        await Functions.send_logging_message(interaction = interaction, kind = 'verify_start')
        captcha = Functions.create_captcha()
        captcha_picture = discord.File(captcha[0], filename = 'captcha.png')
        captcha_text = captcha[1]

        bot.captcha_timeout.append(interaction.user.id)
        await interaction.response.send_message(f'Bitte verifiziere dich, um Zugang zu diesem Server zu erhalten.\n\n**Captcha:**', file = captcha_picture, view = SubmitView(), ephemeral = True)

    async def send_logging_message(interaction: discord.Interaction = None, member: discord.Member = None, kind: str = '', mass_amount: int = 0):
        if interaction is not None:
            c.execute('SELECT * FROM servers WHERE guild_id = ?', (interaction.guild_id,))
            row = c.fetchone()
            log_channel_id = row[3]
            if log_channel_id is None:
                return
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel is None:
                return
        elif member is not None:
            c.execute('SELECT * FROM servers WHERE guild_id = ?', (member.guild.id,))
            row = c.fetchone()
            log_channel_id = row[3]
            if log_channel_id is None:
                return
            log_channel = member.guild.get_channel(int(log_channel_id))
            if log_channel is None:
                return
        ban_time = row[6]
        if len(row) > 7:
            account_age = row[7]
        else:
            account_age = None

        try:
            if kind == 'verify_start':
                embed = discord.Embed(title = 'Captcha gesendet', description = f'User {interaction.user.mention} requested a new captcha.', color = discord.Color.blurple())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'verify_success':
                embed = discord.Embed(title = 'Verification erfolgreich', description = f'User {interaction.user.mention} successfully verified.', color = discord.Color.green())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'verify_fail':
                embed = discord.Embed(title = 'Falscher captcha', description = f'User {interaction.user.mention} entered a wrong captcha.', color = discord.Color.red())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'verify_kick':
                embed = discord.Embed(title = 'Time limit reached', color = discord.Color.red())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                embed.add_field(name = 'User', value = member.mention)
                embed.add_field(name = 'Action', value = 'Kick')
                await log_channel.send(embed = embed)
            elif kind == 'verify_ban':
                embed = discord.Embed(title = 'Time limit reached', color = discord.Color.red())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                embed.add_field(name = 'User', value = member.mention)
                embed.add_field(name = 'Action', value = 'Ban')
                if ban_time is not None:
                    embed.add_field(name = 'Duration', value = f'{Functions.format_seconds(ban_time)}')
                await log_channel.send(embed = embed)
            elif kind == 'verify_mass_started':
                embed = discord.Embed(title = 'Mass verification started', description = f'Mass verification started by {interaction.user.mention}.', color = discord.Color.blurple())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'verify_mass_success':
                embed = discord.Embed(title = 'Mass verification successful', description = f'{interaction.user.mention} successfully applied the verified role to {mass_amount} users.', color = discord.Color.green())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'unban':
                embed = discord.Embed(title = 'Unban', description = f'User {member.mention} was unbanned.', color = discord.Color.green())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'account_too_young':
                embed = discord.Embed(title = 'Account too young', description = f'User {member.mention} was kicked because their account is youger than {Functions.format_seconds(account_age)}.', color = discord.Color.orange())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
            elif kind == 'user_verify':
                embed = discord.Embed(title = 'User verified', description = f'User {member.mention} was verified by {interaction.user.mention}.', color = discord.Color.green())
                embed.timestamp = datetime.datetime.now(datetime.UTC)
                await log_channel.send(embed = embed)
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
    
    async def rcon_lua_run(command: str, host: str, port: int, passwd: str):
        try:
            response = await source.rcon(f'lua_run {command}', host=host, port=port, passwd=passwd)
            index = response.find('rcon')
            if index != -1:
                response = response[:index]
            response = response.replace('\n', '').replace(command, '').replace('>', '').replace(' ', '').replace('(', '').replace(')', '').replace('...', '')
            return response
        except Exception as e:
            program_logger.error(f'Fehler beim Ausführen von rcon: {e}')
            return e

    async def send_update_serverpanel(entry_id: tuple, channel: discord.TextChannel, update: bool = False, message_on_update: discord.Message = ''):
        host, port, passwd = entry_id[2], entry_id[3], entry_id[4]
        embed = discord.Embed(
            title = await Functions.rcon_lua_run(LUA_COMMANDS['GetHostName'], host, port, passwd),
            url = f'{STEAM_REDIRECT_URL}?ip={host}&port={port}',
            description = f"**IP:** {host}:{port}",
            color = discord.Color.brand_green(),
            timestamp = datetime.datetime.now(datetime.UTC),
        )

        guild_image = channel.guild.icon.url if channel.guild.icon else 'https://cdn.cloudflare.steamstatic.com/steam/apps/4000/header.jpg'
        embed.set_thumbnail(url=guild_image)
        #embed.add_field(name='\u200b', value='\u200b', inline=False)
        embed.add_field(name="Aktuelle Spieler", value=await Functions.rcon_lua_run(LUA_COMMANDS['CurrentPlayers'], host, port, passwd), inline=True)
        embed.add_field(name="Maximale Spieler", value=await Functions.rcon_lua_run(LUA_COMMANDS['MaxPlayers'], host, port, passwd), inline=True)
        embed.add_field(name='\u200b', value='\u200b', inline=True)
        embed.add_field(name="Map", value=await Functions.rcon_lua_run(LUA_COMMANDS['GetMap'], host, port, passwd), inline=True)
        embed.add_field(name="Gamemode", value=await Functions.rcon_lua_run(LUA_COMMANDS['ActiveGamemode'], host, port, passwd), inline=True)
        embed.add_field(name='\u200b', value='\u200b', inline=True)
        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
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

        data = []
        for game in games:
            game_info = await SteamAPI.get_app_details(game)
            if game_info is None:
                program_logger.debug(f'Game not found: {game}')
                continue
        
            structure = {
                'id': game,
                'title': game_info[game]['data']['name'],
                'description': game_info[game]['data']['short_description']
            }
            data.append(structure)
        program_logger.debug(data)
        return data
    
    async def update_team_embed(guild):
        teams_data = Functions.load_teams()
        embeds = []
        
        for team in teams_data["teams"]:
            role: discord.Role = guild.get_role(team["role_id"])
            if role and role.members:
                members = '\n'.join([f"{member.mention}" for member in role.members])
                
                embed = discord.Embed(
                    title=f"{role.name}",
                    description=members,
                    color=discord.Color.dark_orange(),
                    timestamp=datetime.datetime.now(datetime.UTC)
                )
                
                embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        
                if role.icon:
                    embed.set_thumbnail(url=role.icon.url)
        
                embeds.append(embed)
        
        return embeds
    
    async def check_message(message: discord.Message):
        """
        Überprüft eine Nachricht auf böse Wörter und löscht die Nachricht, wenn
        ein ähnliches oder exaktes Wort gefunden wird.
        """
        if await Functions.isSpamming(message):
            embed = discord.Embed()
            embed.title = "Nutzer wurde getimeouted"
            embed.color = discord.Color.red()
            embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
            embed.set_footer(text=FOOTER_TEXT, icon_url=message.guild.icon.url)
            
            if message.author.is_timed_out():
                return
            try:
                await message.author.timeout(datetime.timedelta(minutes=5), reason="Spamming")
                embed.description = f"Der Nutzer {message.author.mention} wurde für 5 Minuten getimeouted, da er zu schnell schreibt."
            except discord.Forbidden:
                embed.description = f"Der Nutzer {message.author.mention} konnte nicht getimeouted werden, da ich keine Rechte dazu habe."

            row = c.execute("SELECT logging_channel FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (message.guild.id,)).fetchone()
            channel = await Functions.get_or_fetch('channel', row[0]) if row else None
            await channel.send(embed=embed)
            try:
                await message.delete()
            except discord.NotFound:
                pass

        return
        if BadWords.isBad(message.content):
            await message.delete()
            guild = message.guild
            emb = discord.Embed(
            title='⚠️ Warnung ⚠️',
            color=discord.Color.yellow(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            )
            emb.add_field(
            name="Grund",
            value="Deine Nachricht wurde vom System gemeldet und gelöscht.",
                inline=False
            )
            emb.add_field(
                name="Gelöschte Nachricht",
                value=message.content,
                inline=False
            )
            emb.set_footer(text='HRP | System', icon_url=guild.icon.url)
            try:
                await message.author.send(embed=emb)
            except discord.Forbidden:
                pass

    async def isSpamming(message: discord.Message) -> bool:
        author = message.author
        if author.bot:
            return False
        
        user_id = author.id
        current_time = message.created_at.timestamp()

        # Cache the user's message times
        if user_id not in bot.message_cache:
            bot.message_cache[user_id] = []

        # Remove old messages (older than 10 seconds)
        bot.message_cache[user_id] = [msg_time for msg_time in bot.message_cache[user_id] if current_time - msg_time < 10]

        bot.message_cache[user_id].append(current_time)

        if len(bot.message_cache[user_id]) >= 5:
            return True

        return False

    async def isAdminOrSupport(interaction: discord.Interaction) -> bool:
        isAdmin = interaction.user.guild_permissions.administrator
        if isAdmin:
            return True
        else:
            c.execute('SELECT SUPPORT_ROLE_ID FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild.id,))
            support_role_id = c.fetchone()[0]
            if support_role_id is None:
                return False
            else:
                guild = bot.get_guild(interaction.guild.id)
                support_role: discord.Role = guild.get_role(int(support_role_id))
                if support_role in interaction.user.roles:
                    return True


class Tasks():
    async def update_embeds_task():
        async def _function():
            c.execute("SELECT * FROM EMBEDS")
            entries = c.fetchall()
            for entry in entries:
                channel = await Functions.get_or_fetch('channel', entry[2])
                if channel is None:
                    c.execute("DELETE FROM EMBEDS WHERE ID = ?", (entry[0],))
                    conn.commit()
                    continue
                try:
                    message = await channel.fetch_message(entry[3])
                except discord.NotFound:
                    c.execute("DELETE FROM EMBEDS WHERE ID = ?", (entry[0],))
                    conn.commit()
                    continue
                c.execute("SELECT * FROM SERVER WHERE ID = ?", (entry[4],))
                server = c.fetchone()
                if server is None:
                    c.execute("DELETE FROM EMBEDS WHERE ID = ?", (entry[0],))
                    conn.commit()
                    continue
                panel = await Functions.send_update_serverpanel(server, channel, update=True, message_on_update=message)
                if not panel:
                    c.execute("DELETE FROM EMBEDS WHERE ID = ?", (entry[0],))
                    conn.commit()
                    program_logger.error(f"Fehler beim Updaten des Panels: {panel}")
                    continue

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
                return await epic_games_api.GetFreeGames()
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
            recent_list = []
            try:
                c.execute("SELECT * FROM GUILD_SETTINGS")
                data = c.fetchall()
                if not data:
                    return
    
                channel = await Functions.get_or_fetch('channel', data[0][6])
                if not channel:
                    program_logger.warning("Kein Channel gefunden.")
                    return
    
                try:
                    new_games = await _fetch_games(platform)
                except Exception as e:
                    program_logger.error(f"Fehler beim Abrufen der {platform.capitalize()} Games: {e}")
                    return
    
                embeds = []
                for game in new_games:
                    c.execute("SELECT * FROM free_games WHERE TITEL_ID = ?", (game['id'],))
                    if c.fetchone() is not None:
                        continue
    
                    game_details = await _get_game_details(game, platform)
                    if "mysterygame" in game_details['title'].lower().replace(' ', ''):
                        continue
                    if game_details['title'] not in [g['title'] for g in recent_list]:
                        embed = discord.Embed(
                            title=game_details['title'],
                            url=game_details['url'],
                            color=discord.Color.dark_gold(),
                            timestamp=datetime.datetime.now(datetime.UTC)
                        )
                        embed.set_image(url=game_details['image_url'])
                        embed.add_field(name='Titel', value=game_details['title'], inline=False)
                        embed.add_field(name='Beschreibung', value=game_details['description'], inline=False)
                        embed.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
                        embeds.append(embed)
                        c.execute("INSERT INTO free_games (TITEL_ID, DATUM) VALUES (?, ?)", (game['id'], int(time.time())))
    
                conn.commit()
                if embeds:
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
                    if guild:
                        embeds = await Functions.update_team_embed(guild)
                        if not embeds:
                            return

                        c.execute("SELECT * FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (guild.id,))
                        data = c.fetchone()
                        if data is None:
                            continue

                        channel = await Functions.get_or_fetch('channel', entry[1])
                        if channel:
                            last_message: discord.Message = None
                            async for message in channel.history(limit=1):
                                last_message = message
                                break

                            if last_message and last_message.embeds and isinstance(last_message.embeds[0], discord.Embed):
                                if last_message.author != bot.user:
                                    continue
                                await last_message.edit(embeds=embeds)
                            else:
                                await channel.send(embeds=embeds)
                except Exception as e:
                    program_logger.error(f"Fehler beim Senden des Team Embeds.:  {e}")
        
        while not bot.initialized:
            await asyncio.sleep(5)
        while True:
            await _function()
            try:
                await asyncio.sleep(60*60)
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
            program_logger.debug(f'Error while starting health server: {e}')

    async def process_latest_joined():
        while not shutdown:
            for guild in bot.guilds:
                try:
                    c.execute('SELECT * FROM servers WHERE guild_id = ?', (guild.id,))
                    server = c.fetchone()
                    if server is None:
                        continue
                    timeout = server[4]
                    verified_role_id = server[2]
                    action = server[5]
                    ban_time = server[6]
                    c.execute('SELECT * FROM processing_joined WHERE guild_id = ? AND (join_time + ?) < ?', (guild.id, timeout, int(time.time())))
                    rows = c.fetchall()
                    for row in rows:
                        guild = bot.get_guild(row[0])
                        if guild is None:
                            c.execute('DELETE FROM processing_joined WHERE guild_id = ?', (row[0],))
                            continue
                        member = guild.get_member(row[1])
                        if member is None:
                            try:
                                member = await guild.fetch_member(row[1])
                                if member is None:
                                    c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (row[0], row[1]))
                                    continue
                            except discord.NotFound:
                                c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (row[0], row[1]))
                                continue
                        if action is None:
                            continue
                        verified_role = guild.get_role(verified_role_id)
                        if verified_role is None:
                            continue
                        if verified_role not in member.roles:
                            if action == 'kick':
                                try:
                                    await member.kick(reason='Did not successfully verify in time.')
                                    await Functions.send_logging_message(member = member, kind = 'verify_kick')
                                    program_logger.debug(f'Kicked {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                                except discord.Forbidden:
                                    program_logger.debug(f'Could not kick {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                            elif action == 'ban':
                                try:
                                    if ban_time is not None:
                                        await member.ban(reason=f'Did not successfully verify in time. Banned for {Functions.format_seconds(ban_time)}')
                                        c.execute('INSERT INTO temp_bans VALUES (?, ?, ?)', (guild.id, member.id, int(time.time() + ban_time)))
                                    else:
                                        await member.ban(reason=f'Did not successfully verify in time.')
                                    await Functions.send_logging_message(member = member, kind = 'verify_ban')
                                    program_logger.debug(f'Banned {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                                except discord.Forbidden:
                                    program_logger.debug(f'Could not ban {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                        else:
                            c.execute('DELETE FROM processing_joined WHERE guild_id = ? AND user_id = ?', (row[0], row[1]))
                except Exception as e:
                    conn.commit()
                    raise e
            conn.commit()
            try:
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                pass

    async def check_and_process_temp_bans():
        while not shutdown:
            c.execute('SELECT * FROM temp_bans WHERE unban_time < ?', (time.time(),))
            temp_bans = c.fetchall()
            for temp_ban in temp_bans:
                try:
                    guild = bot.get_guild(temp_ban[0])
                    if guild is None:
                        c.execute('DELETE FROM temp_bans WHERE guild_id = ?', (temp_ban[0],))
                        continue
                    member = bot.get_user(temp_ban[1])
                    if member is None:
                        try:
                            member = await bot.fetch_user(temp_ban[1])
                        except discord.NotFound:
                            c.execute('DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?', (temp_ban[0], temp_ban[1]))
                            continue
                    c.execute('SELECT log_channel FROM servers WHERE guild_id = ?', (guild.id,))
                    log_channel_id = c.fetchone()[0]
                    log_channel = guild.get_channel(int(log_channel_id))
                    if log_channel is None:
                        try:
                            log_channel = await guild.fetch_channel(int(log_channel_id))
                        except:
                            log_channel = None
                    try:
                        await guild.unban(member, reason='Temporary ban expired.')
                        embed = discord.Embed(title = 'Unban', description = f'User {member.mention} was unbanned.', color = discord.Color.green())
                        embed.timestamp = datetime.datetime.now(datetime.UTC)
                        program_logger.debug(f'Unbanned {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                        c.execute('DELETE FROM temp_bans WHERE guild_id = ? AND user_id = ?', (temp_ban[0], temp_ban[1]))
                        if log_channel is not None:
                            try:
                                await log_channel.send(embed = embed)
                            except discord.Forbidden:
                                program_logger.debug(f'Could not send unban log message in {guild.name} ({guild.id}).')
                    except discord.Forbidden:
                        program_logger.debug(f'Could not unban {member.name}#{member.discriminator} ({member.id}) from {guild.name} ({guild.id}).')
                except Exception as e:
                    conn.commit()
                    raise e

            conn.commit()
            try:
                await asyncio.sleep(15)
            except asyncio.CancelledError:
                pass

                 
class Owner():
    async def log(message, args):
        async def __wrong_selection():
            await message.channel.send('```'
                                       'log [current/folder/lines] (Replace lines with a positive number, if you only want lines.) - Get the log\n'
                                       '```')
        if args == []:
            await __wrong_selection()
            return
        if args[0] == 'current':
            try:
                await message.channel.send(file=discord.File(f'{LOG_FOLDER}{BOT_NAME}.log'))
            except discord.HTTPException as err:
                if err.status == 413:
                    with ZipFile(f'{BUFFER_FOLDER}Logs.zip', mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as f:
                        f.write(f'{LOG_FOLDER}{BOT_NAME}.log')
                    try:
                        await message.channel.send(file=discord.File(f'{BUFFER_FOLDER}Logs.zip'))
                    except discord.HTTPException as err:
                        if err.status == 413:
                            await message.channel.send("The log is too big to be sent directly.\nYou have to look at the log in your server (VPS).")
                    os.remove(f'{BUFFER_FOLDER}Logs.zip')
                    return
        elif args[0] == 'folder':
            if os.path.exists(f'{BUFFER_FOLDER}Logs.zip'):
                os.remove(f'{BUFFER_FOLDER}Logs.zip')
            with ZipFile(f'{BUFFER_FOLDER}Logs.zip', mode='w', compression=ZIP_DEFLATED, compresslevel=9, allowZip64=True) as f:
                for file in os.listdir(LOG_FOLDER):
                    if file.endswith(".zip"):
                        continue
                    f.write(f'{LOG_FOLDER}{file}')
            try:
                await message.channel.send(file=discord.File(f'{BUFFER_FOLDER}Logs.zip'))
            except discord.HTTPException as err:
                if err.status == 413:
                    await message.channel.send("The folder is too big to be sent directly.\nPlease get the current file or the last X lines.")
            os.remove(f'{BUFFER_FOLDER}Logs.zip')
            return
        else:
            try:
                if int(args[0]) < 1:
                    await __wrong_selection()
                    return
                else:
                    lines = int(args[0])
            except ValueError:
                await __wrong_selection()
                return
            with open(f'{LOG_FOLDER}{BOT_NAME}.log', 'r', encoding='utf8') as f:
                with open(f'{BUFFER_FOLDER}log-lines.txt', 'w', encoding='utf8') as f2:
                    count = 0
                    for line in (f.readlines()[-lines:]):
                        f2.write(line)
                        count += 1
            await message.channel.send(content=f'Here are the last {count} lines of the current logfile:', file=discord.File(f'{BUFFER_FOLDER}log-lines.txt'))
            if os.path.exists(f'{BUFFER_FOLDER}log-lines.txt'):
                os.remove(f'{BUFFER_FOLDER}log-lines.txt')
            return

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
        _message = 'System fährt herunter...'
        program_logger.info(_message)
        try:
            await message.channel.send(_message)
        except:
            await owner.send(_message)
        await bot.change_presence(status=discord.Status.invisible)
        shutdown = True

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        [task.cancel() for task in tasks]
        await asyncio.gather(*tasks, return_exceptions=True)

        conn.commit()
        conn.close()

        await bot.close()
        


@tree.command(name = 'ping', description = 'Test, if the bot is responding.')
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.user.id))
async def self(interaction: discord.Interaction):
    before = time.monotonic()
    await interaction.response.send_message('Pong!')
    ping = (time.monotonic() - before) * 1000
    await interaction.edit_original_response(content=f'Command ausführ Zeit: `{int(ping)}ms`\nPing zum Gateway: `{int(bot.latency * 1000)}ms`')

@tree.command(name = 'change_nickname', description = 'Change the nickname of the bot.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_nicknames = True)
@discord.app_commands.describe(nick='New nickname for me.')
async def self(interaction: discord.Interaction, nick: str):
    await interaction.guild.me.edit(nick=nick)
    await interaction.response.send_message(f'Mein neuer Nickname ist nun **{nick}**.', ephemeral=True)
    
@tree.command(name = 'setup', description = 'Setup the bot.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
async def self(interaction: discord.Interaction, welcome_channel: discord.TextChannel, leave_channel: discord.TextChannel, logging_channel: discord.TextChannel, announce_channel: discord.TextChannel, team_update: discord.TextChannel, free_games_channel: discord.TextChannel, team_list_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (interaction.guild.id,))
    guild = c.fetchone()
    if guild is None:
        c.execute('INSERT OR REPLACE INTO GUILD_SETTINGS (GUILD_ID, welcome_channel, leave_channel, logging_channel, announce_channel, team_update_channel, free_games_channel, team_list_channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (interaction.guild.id, welcome_channel.id, leave_channel.id, logging_channel.id, announce_channel.id, team_update.id, free_games_channel.id, team_list_channel.id))
        conn.commit()
        erfolgreich = discord.Embed(
            title = '✅ Erfolgreich',
            description = 'Die Konfiguration wurde erfolgreich gespeichert.',
            color = discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
            )
        erfolgreich.set_footer(text = FOOTER_TEXT, icon_url = bot.user.avatar.url if bot.user.avatar else '')
        await interaction.edit_original_response(embed=erfolgreich)
    else:
        warning = discord.Embed(
            title = '⚠️ Warnung',
            description = 'Es existiert bereits ein Eintrag für diesen Server. Möchtest du ihn ersetzen?',
            color = discord.Color.yellow()
            )
        warning.set_footer(text = 'Reagiere mit ✅ um den Eintrag zu ersetzen.')
        warning_message = await interaction.channel.send(embed = warning)
        await asyncio.sleep(2)
        await warning_message.add_reaction('✅')
        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) == '✅' and reaction.message.id == warning_message.id
        try:
            reaction, user = await interaction.client.wait_for('reaction_add', timeout=60.0, check=check)
            if reaction.emoji == '✅':
                c.execute('INSERT OR REPLACE INTO GUILD_SETTINGS (GUILD_ID, welcome_channel, leave_channel, logging_channel, announce_channel, team_update_channel, free_games_channel, team_list_channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (interaction.guild.id, welcome_channel.id, leave_channel.id, logging_channel.id, announce_channel.id, team_update.id, free_games_channel.id, team_list_channel.id))
                conn.commit()
                await interaction.channel.send('✅ Eintrag erfolgreich ersetzt.')
                await warning_message.delete()
        except asyncio.TimeoutError:
            await interaction.channel.send('❌ Zeit abgelaufen.')
            
@tree.command(name='clear', description='Clears the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_messages=True)
@discord.app_commands.describe(amount='Amount of messages to delete.')
async def self(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    try:
        amount = int(amount)
        await interaction.channel.purge(limit=amount)
        clear_eb = discord.Embed(
            title='✅ Clear',
            description=f'{amount} Nachrichten wurden gelöscht.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        clear_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=clear_eb)
    except ValueError:
        error_eb = discord.Embed(
           title='❌ Fehler',
           description='Die Menge muss eine Zahl sein.',
           color=discord.Color.red(),
           timestamp=datetime.datetime.now(datetime.UTC)
        )
        error_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=error_eb)
        
@tree.command(name='lock', description='Locks the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_channels=True)
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if interaction.channel.permissions_for(interaction.guild.default_role).send_messages == False:
        lock_eb = discord.Embed(
            title='🔒 Lock',
            description='Der Chat ist bereits gesperrt.',
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        lock_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=lock_eb)
        return
    else:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=False)
        lock_eb = discord.Embed(
            title='🔒 Lock',
            description='Der Chat wurde gesperrt.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        lock_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=lock_eb)
    
@tree.command(name='unlock', description='Unlocks the chat.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_channels=True)
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if interaction.channel.permissions_for(interaction.guild.default_role).send_messages == True:
        unlock_eb = discord.Embed(
            title='🔓 Unlock',
            description='Der Chat ist bereits entsperrt.',
            color=discord.Color.red(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        unlock_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=unlock_eb)
        return
    else:
        await interaction.channel.set_permissions(interaction.guild.default_role, send_messages=True)
        unlock_eb = discord.Embed(
            title='🔓 Unlock',
            description='Der Chat wurde entsperrt.',
            color=discord.Color.green(),
            timestamp=datetime.datetime.now(datetime.UTC)
        )
        unlock_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
        await interaction.followup.send(embed=unlock_eb)
    
@tree.command(name='kick', description='Kicks a user.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(kick_members=True)
@discord.app_commands.describe(user='User to kick.',
                               reason='Reason for the kick.'
                               )
async def self(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.guild.kick(user, reason=reason)
    user_mention = user.mention if user else f'<@!{user.id}>'
    kick_eb = discord.Embed(
        title='⚔️ Kick',
        description=f'{user_mention} wurde gekickt.\nGrund: {reason}',
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    kick_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    
    user_notify = discord.Embed(
        title='⚔️ Kick',
        description=f'Du wurdest gekickt.\nGrund: {reason}',
        color=discord.Color.dark_orange(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    user_notify.add_field(name="Ausführendes Teammitglied", value=interaction.user)
    user_notify.add_field(name="Grund", value=reason)
    user_notify.add_field(name="Server", value=interaction.guild)
    user_notify.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

    try:
        await user.send(embed=user_notify)
    except discord.Forbidden:
        pass
    await interaction.followup.send(embed=kick_eb)
    
@tree.command(name='ban', description='Bans a user.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(ban_members=True)
@discord.app_commands.describe(user='User to ban.',
                               reason='Reason for the ban.'
                               )
async def self(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.guild.ban(user, reason=reason)
    user_mention = user.mention if user else f'<@!{user.id}>'
    ban_eb = discord.Embed(
        title='🔨 Ban',
        description=f'{user_mention} wurde gebannt.\nGrund: {reason}',
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    ban_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    
    user_notify = discord.Embed(
        title='🔨 Ban',
        description=f'Du wurdest gebannt.\nGrund: {reason}',
        color=discord.Color.dark_orange(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    user_notify.add_field(name="Ausführendes Teammitglied", value=interaction.user)
    user_notify.add_field(name="Grund", value=reason)
    user_notify.add_field(name="Server", value=interaction.guild)
    user_notify.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

    try:
        await user.send(embed=user_notify)
    except discord.Forbidden:
        pass
    await interaction.followup.send(embed=ban_eb)
    
@tree.command(name='unban', description='Unbans a user.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(ban_members=True)
@discord.app_commands.describe(user='User to unban.',
                               reason='Reason for the unban.'
                               )
async def self(interaction: discord.Interaction, user: discord.User, reason: str):
    await interaction.response.defer(ephemeral=True)
    await interaction.guild.unban(user, reason=reason)
    user_mention = user.mention if user else f'<@!{user.id}>'
    unban_eb = discord.Embed(
        title='🔓 Unban',
        description=f'{user_mention} wurde entbannt.\nGrund: {reason}',
        color=discord.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    unban_eb.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')
    
    user_notify = discord.Embed(
        title='🔓 Unban',
        description=f'Du wurdest entbannt.\nGrund: {reason}',
        color=discord.Color.dark_orange(),
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    user_notify.add_field(name="Ausführendes Teammitglied", value=interaction.user)
    user_notify.add_field(name="Grund", value=reason)
    user_notify.add_field(name="Server", value=interaction.guild)
    user_notify.set_footer(text=FOOTER_TEXT, icon_url=bot.user.avatar.url if bot.user.avatar else '')

    try:
        await user.send(embed=user_notify)
    except discord.Forbidden:
        pass
    await interaction.followup.send(embed=unban_eb)
 
@tree.command(name='team_update', description='Updates the team.')
@discord.app_commands.checks.has_permissions(manage_roles=True)
@discord.app_commands.describe(user='User')
@discord.app_commands.choices(role=[
    discord.app_commands.Choice(name="Community Verwaltung", value="communityverwaltung"),
    discord.app_commands.Choice(name="Community Leitung", value="Communityleitung"),
    discord.app_commands.Choice(name="Infrastruktur Verwaltung", value="Infrastruktur_Verwaltung"),
    discord.app_commands.Choice(name="Stv. Projektleitung", value="Stv_Projektleiter"),
    ############################################################################################
    discord.app_commands.Choice(name="Jedi vs Sith - Verwaltung", value="jvs_verwaltung"),
    discord.app_commands.Choice(name="Jedi vs Sith - Stv. Teamleitung", value="jvs_stv_teamleitung"),
    discord.app_commands.Choice(name="Jedi vs Sith - S-Admin", value="jvs_s_admin"),
    discord.app_commands.Choice(name="Jedi vs Sith - Admin", value="jvs_admin"),
    discord.app_commands.Choice(name="Jedi vs Sith - Team", value="jvs_team"),
    discord.app_commands.Choice(name="Jedi vs Sith - Developer", value="jvs_dev"),
    ############################################################################################
    discord.app_commands.Choice(name="Developer", value="developer"),
    discord.app_commands.Choice(name="Grafik Designer", value="grafikdesigner"),
    ############################################################################################
    discord.app_commands.Choice(name="Discord - Verwaltung", value="discord_verwaltung"),
    discord.app_commands.Choice(name="Moderator", value="moderator"),
    discord.app_commands.Choice(name="Supporter", value="supporter"),
    discord.app_commands.Choice(name="Event - Teamleitung", value="event_leitung"),
    discord.app_commands.Choice(name="Event - Team", value="event_team"),
])
@discord.app_commands.choices(category=[
    discord.app_commands.Choice(name="Neues Teammitglied", value="new_member"),
    discord.app_commands.Choice(name="Teammitglied verlässt", value="leave"),
])
async def team_update(interaction: discord.Interaction, user: discord.Member, role: discord.app_commands.Choice[str], category: discord.app_commands.Choice[str]):
    role_mapping = {
        "Communityleitung": 1297333309650767944,
        "Infrastruktur_Verwaltung": 1297333311407919107,
        "Projektleiter": 1297333313379504180,
        "jvs_team": 1297333325710495825,
        "head_dev": 1297333322846044320,
        "developer":1297333323823321109,
        "discord_leitung":1297333315447033856,
        "discord_team": 1297333316449730651,
        "communitymanager": 1297333310737088532,
        "ttt_team": 1297333324792070184,
        "darkrp_team": 1297333326591295515,
        "support": 1297548437532971058,
    }

    role_id = role_mapping[role.value]
    discord_role = interaction.guild.get_role(role_id)

    action_text = ""
    try:
        if category.value == "new_member":
            if discord_role in user.roles:
                await user.remove_roles(discord_role)
            else:
                await user.add_roles(discord_role)
    
        elif category.value == "leave":
            if discord_role in user.roles:
                await user.remove_roles(discord_role)
    except discord.Forbidden:
        await interaction.response.send_message("Ich habe nicht die Berechtigung, diese Rolle hinzuzufügen oder zu entfernen.", ephemeral=True)
        return
    
    color = discord.Color.green() if category.value == "new_member" else discord.Color.red()
    embed = discord.Embed(
        title='**👥 Team Update**',
        description="",
        color=color,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.set_footer(text=FOOTER_TEXT, icon_url=interaction.guild.me.avatar.url)
    embed.add_field(name='Team:', value=discord_role.name, inline=False)
    embed.add_field(name='User:', value=user.mention, inline=False)
    if category.value == "new_member":
        embed.add_field(name='Willkommen:', value=f'🎉 Ist dem Team {discord_role.name} beigetreten. Wir hoffen auf eine gute Zusammenarbeit!', inline=False)
    elif category.value == "leave":
        embed.add_field(name='Danke:', value='👋 Wir danken für deine Arbeit und wünschen dir noch viel Spaß auf der HRP Community.', inline=False)
    
    
    guild_id = interaction.guild.id
    c.execute("SELECT * FROM GUILD_SETTINGS WHERE GUILD_ID = ?", (guild_id,))
    guild = c.fetchone()
    
    if guild is None:
        await interaction.response.send_message("Bitte konfiguriere den Bot zuerst.", ephemeral=True)
        return
    
    team_update_channel = await bot.fetch_channel(guild[5])
    await team_update_channel.send(embed=embed)
    await interaction.response.send_message(f"Das Team wurde aktualisiert: {action_text}", ephemeral=True)
    
@tree.command(name = 'register_server', description = 'register a Server')
@discord.app_commands.checks.cooldown(2, 30, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(host='ip address of the server.',
                               port='server port.',
                               passwd='rcon password of the server.'
                               )
async def self(interaction: discord.Interaction, host: str, port: int, passwd: str):
    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM SERVER WHERE GUILD = ? AND HOST = ? AND PORT = ? AND PASS = ?", (interaction.guild_id, host, port, passwd))
    if c.fetchone() is not None:
        await interaction.followup.send(content=f"Error: Server already registered.", ephemeral=True)
    else:
        test = await Functions.rcon_lua_run(LUA_COMMANDS['GetIPAddress'], host, port, passwd)
        if type(test) != str:
            await interaction.followup.send(content=f"Error: {test}", ephemeral=True)
            return
        else:
            c.execute("INSERT INTO SERVER (GUILD, HOST, PORT, PASS) VALUES (?, ?, ?, ?)", (interaction.guild_id, host, port, passwd))
            conn.commit()
            c.execute("SELECT ID FROM SERVER WHERE GUILD = ? AND HOST = ? AND PORT = ? AND PASS = ?", (interaction.guild_id, host, port, passwd))
            ID = c.fetchone()[0]
            await interaction.followup.send(content=f"Server registered successfully.\nYou can now use `/send_panel` with ID {ID}, to send it to a channel.", ephemeral=True)

@tree.command(name = 'send_panel_server', description = 'send the panel into a channel.')
@discord.app_commands.checks.cooldown(2, 30, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(entry_id='panel id.',
                               channel='In which channel the panel should be send.'
                               )
async def self(interaction: discord.Interaction, entry_id: int, channel: discord.TextChannel):
    async def _pannel_send():
        c.execute("SELECT * FROM SERVER WHERE ID = ?", (entry_id,))
        entry = c.fetchone()
        if entry is None:
            await interaction.followup.send(content=f"Error: Server with ID {entry_id} not found.", ephemeral=True)
            return
        if entry[1] != interaction.guild_id:
            await interaction.followup.send(content=f"Error: Server with ID {entry_id} is not registered for this guild.", ephemeral=True)
            return
        panel = await Functions.send_update_serverpanel(entry, channel)
        if type(panel) is not int:
            await interaction.followup.send(content=f"Error: Panel could not be sent.", ephemeral=True)
            return
        c.execute("INSERT INTO EMBEDS (GUILD, CHANNEL, MESSAGE_ID, SERVER_ID) VALUES (?, ?, ?, ?)", (interaction.guild_id, channel.id, panel, entry_id))
        conn.commit()
        await interaction.followup.send(content=f"Panel sent successfully.", ephemeral=True)

    perms = channel.permissions_for(interaction.guild.me)
    needed_permissions = ['send_messages', 'embed_links', 'read_message_history', 'view_channel']
    missing_permissions = [perm for perm in needed_permissions if not getattr(perms, perm)]
    if not interaction.guild.me.guild_permissions.administrator or missing_permissions:
        await interaction.response.send_message(content=f"I need the following permissions to send the panel: {", ".join(missing_permissions)}.\nYou can also give me Admin.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM EMBEDS WHERE GUILD = ? AND CHANNEL = ? AND SERVER_ID = ?", (interaction.guild_id, channel.id, entry_id))
    message_id = c.fetchone()
    if message_id is None:
        await _pannel_send()
    else:
        channel = await Functions.get_or_fetch('channel', channel.id)
        try:
            message = await channel.fetch_message(message_id[3])
        except discord.NotFound:
            message = None
            c.execute("DELETE FROM EMBEDS WHERE GUILD = ? AND CHANNEL = ? AND SERVER_ID = ?", (interaction.guild_id, channel.id, entry_id))
            conn.commit()
        if message is not None:
            await interaction.followup.send(content=f"Error: Panel already exists in channel.", ephemeral=True)
            return
        else:
            await _pannel_send()

@tree.command(name = 'list_servers', description = 'list of all registered servers.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(administrator = True)
async def self(interaction: discord.Interaction):
    c.execute("SELECT * FROM SERVER WHERE GUILD = ?", (interaction.guild_id,))
    servers = c.fetchall()
    if servers == []:
        await interaction.response.send_message(content=f"Keine Server in der Datenbank gefunden.", ephemeral=True)
        return
    embed = discord.Embed(
        title = f"Regestrierte Server für {interaction.guild.name}",
        color = discord.Color.blue()
    )
    i = 0
    for server in servers:
        embed.add_field(name=f"ID: {server[0]}", value=f"IP: {server[2]}:{server[3]}", inline=False)
        i += 1
        if i == 25:
            if len(servers) > 25:
                embed.set_footer(text=f"Nur 25/{len(servers)} Server werden aufgeführt.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name = 'unregister_server', description = 'remove a server.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
@discord.app_commands.describe(entry_id='id of the panel from the server which should be removed')
async def self(interaction: discord.Interaction, entry_id: int):
    c.execute("SELECT * FROM SERVER WHERE ID = ?", (entry_id,))
    entry = c.fetchone()
    if entry is None:
        await interaction.response.send_message(content=f"Error: Server mit der ID {entry_id} konnte in der Datenbank nicht gefunden werden.", ephemeral=True)
    else:
        if entry[1] != interaction.guild_id:
            await interaction.response.send_message(content=f"Error: Server mit der ID {entry_id} ist nicht für diesen Discord regestriert.", ephemeral=True)
        else:
            c.execute("DELETE FROM SERVER WHERE ID = ?", (entry_id,))
            c.execute("DELETE FROM EMBEDS WHERE SERVER_ID = ?", (entry_id,))
            conn.commit()
            await interaction.response.send_message(content=f"Server mit der ID {entry_id} erfolgreich entfernt.", ephemeral=True)
                     
@tree.command(name='create_ticketsystem', description='creates the ticketsystem.')
@discord.app_commands.checks.cooldown(1, 2, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator=True)
@discord.app_commands.describe(channel='In which channel the ticketsystem should be.',
                               archive='In which channel the transcript should be send.',
                               support='Group that has accesd to ticket controls.')
async def self(interaction: discord.Interaction, channel: discord.TextChannel, archive: discord.TextChannel, support: discord.Role):
    class TicketDropdown(discord.ui.Select):
            def __init__(self):
                options = [
                discord.SelectOption(label="Discord", description="Für allgemeine Hilfe im Discord."),
                discord.SelectOption(label="Report", description="Melde einen Nutzer auf dem Discord."),
                discord.SelectOption(label="Support", description="Für technische Hilfe."),
                discord.SelectOption(label="Bug", description="Falls du einen Bug gefunden hast."),
                discord.SelectOption(label="Feedback", description="Falls du Feedback an HRP hast."),
                discord.SelectOption(label="Entbannung", description="Wenn du einen Entbannungsantrag stellen möchtest."),
                discord.SelectOption(label="Sonstiges", description="Für alles andere."),
                ]
                super().__init__(placeholder="Wähle ein Ticket-Thema aus.", options=options, min_values=1, max_values=1, custom_id="support_menu")

    class TicketSystemView(discord.ui.View):
            def __init__(self):
                super().__init__()
                self.add_item(TicketDropdown())

    bot_avatar = bot.user.avatar.url if bot.user.avatar else ''
    ticketsystem_embed = discord.Embed(
    title='Ticket System',
    description='Hier kannst du ein Ticket erstellen. Wähle unten eine Kategorie aus.',
    color=discord.Color.purple()
    )
    ticketsystem_embed.set_footer(text=FOOTER_TEXT, icon_url=bot_avatar)

    c.execute('SELECT * FROM TICKET_SYSTEM WHERE GUILD_ID = ?', (interaction.guild_id,))
    ticketsystem = c.fetchone()
    if ticketsystem:
        await interaction.response.send_message(content=f'[ERROR] Ticketsystem wurde schon erstellt.', ephemeral=True)
    else:
        try:
            c.execute('INSERT INTO TICKET_SYSTEM (GUILD_ID, CHANNEL, ARCHIVE_CHANNEL_ID, SUPPORT_ROLE_ID) VALUES (?, ?, ?, ?)', (interaction.guild_id, channel.id, archive.id, support.id))
            conn.commit()
            await channel.send(embed=ticketsystem_embed, view=TicketSystemView())
            await interaction.response.send_message(content=f'Ticketsystem wurde erfolgreich erstellt.', ephemeral=True)
        except Exception as e:
            text = f"Ticketsystem konnte nicht erstellt werden. -> {e}"
            program_logger.warning(text)
            await interaction.response.send_message(text)
            
@tree.command(name = 'remove_ticket_channel', description = 'removes the ticket channel.')
@discord.app_commands.checks.cooldown(1, 120, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(administrator = True)
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    c.execute("SELECT * FROM TICKET_SYSTEM WHERE GUILD_ID = ?", (interaction.guild_id,))
    guild = c.fetchone()
    if guild is None:
        await interaction.followup.send(content=f'[ERROR] Der Ticket Channel wurde noch nicht gesetzt.', ephemeral=True)
    else:
        c.execute("DELETE FROM TICKET_SYSTEM WHERE GUILD_ID = ?", (interaction.guild_id,))
        conn.commit()
        await interaction.followup.send(content=f'Ticket Channel wurde erfolgreich entfernt.', ephemeral=True)

@tree.command(name = 'verify_send_pannel', description = 'Send pannel to varification channel.')
@discord.app_commands.checks.has_permissions(manage_guild = True)
async def self(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral= True)
    class CaptchaView(discord.ui.View):
        def __init__(self, *, timeout=None):
            super().__init__(timeout=timeout)

            self.add_item(discord.ui.Button(label='🤖 Verifizieren', style=discord.ButtonStyle.blurple, custom_id='verify'))


    c.execute('SELECT * FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if data:
        verify_channel_id = data[1]
        timeout = int(data[4] / 60)
        action = data[5]
        ban_time = data[6]
    else:
        verify_channel_id = None
    if not verify_channel_id:
        await interaction.followup.send('Der Verifizierungskanal ist nicht vorhanden. Bitte setze ihn mit `/setup`.', ephemeral = True)
        return
    try:
        verify_channel = await bot.fetch_channel(verify_channel_id)
    except discord.NotFound:
        verify_channel = None
    except discord.Forbidden:
        await interaction.followup.send(f'Ich habe keine Berechtigung, den Verifizierungskanal zu sehen. (<#{verify_channel_id}>).', ephemeral = True)
        return
    if not verify_channel:
        await interaction.followup.send('Der Verifizierungskanal ist nicht vorhanden. Bitte setze ihn mit `/verify_setup`.', ephemeral = True)
        return


    embed = discord.Embed(title = ':robot: Verifiziere dich',
                          color = discord.Color.brand_green()
                          
                      )
    embed.set_footer(text = FOOTER_TEXT, icon_url = bot.user.avatar.url if bot.user.avatar else '')
    action_text = {
        'ban': f"Bitte beachte, dass du {f' für {Functions.format_seconds(ban_time)}' if ban_time else ''} gebannt wirst, wenn du dich nicht innerhalb von {timeout} Minuten verifizierst.",
        'kick': f"Bitte beachte, dass du gekickt wirst, wenn du dich nicht innerhalb von {timeout} Minuten verifizierst.",
        None: "",
    }[action]

    embed.description = f"Um mit {interaction.guild.name} fortzufahren, bitten wir dich, zu bestätigen, dass du kein Bot bist, indem du ein Captcha löst. Dies dient dazu, die Sicherheit aller zu gewährleisten."
    if action_text:
        embed.description += f"\n\n{action_text}"

    c.execute('SELECT * FROM panels WHERE guild_id = ?', (interaction.guild_id,))
    data = c.fetchone()
    if data:
        panel_id = data[1]
        try:
            panel_id = await verify_channel.fetch_message(panel_id)
        except discord.NotFound:
            panel_id = None
        except discord.Forbidden:
            await interaction.followup.send(f'I don\'t have permission to see the verification channels (<#{verify_channel_id}>) history.\nI need the "Read Message History" permission.', ephemeral = True)
            return
        if not panel_id:
            try:
                panel = await verify_channel.send(embed = embed, view = CaptchaView())
            except discord.Forbidden:
                await interaction.followup.send(f'I don\'t have permission to send messages in the verification channel (<#{verify_channel_id}>).', ephemeral = True)
                return
        else:
            await interaction.followup.send('The verification panel already exists.\nTo update it, you have to first delete the old one.', ephemeral = True)
            return
    else:
        try:
            panel = await verify_channel.send(embed = embed, view = CaptchaView())
        except discord.Forbidden:
            await interaction.followup.send(f'I don\'t have permission to send messages in the verification channel (<#{verify_channel_id}>).', ephemeral = True)
            return

    c.execute('INSERT OR REPLACE INTO panels VALUES (?, ?)', (interaction.guild_id, panel.id))
    conn.commit()
    await interaction.followup.send(f'The verification panel has been sent to <#{verify_channel_id}>.', ephemeral = True)

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
async def self(interaction: discord.Interaction, verify_channel: discord.TextChannel, verify_role: discord.Role, log_channel: discord.TextChannel, timeout: int, action: str, ban_time: str = None, account_age: str = None):
    if action == 'kick':
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message(f'Ich brauche die Erlaubnis für {action} Mitglieder.', ephemeral=True)
            return
    elif action == 'ban':
        if not interaction.guild.me.guild_permissions.ban_members:
            await interaction.response.send_message(f'Ich brauche die Erlaubnis für {action} Mitglieder.', ephemeral=True)
            return
    if action == '':
        action = None
    if not verify_channel.permissions_for(interaction.guild.me).send_messages:
        await interaction.response.send_message(f'Ich benötige die Berechtigung zum Senden von Nachrichten in {verify_channel.mention}.', ephemeral=True)
        return
    if not interaction.guild.me.top_role > verify_role:
        await interaction.response.send_message(f'Meine höchste Rolle muss über {verify_role.mention} liegen, damit ich sie zuweisen kann.', ephemeral=True)
        return
    bot_permissions = log_channel.permissions_for(interaction.guild.me)
    if not bot_permissions.view_channel:
        await interaction.response.send_message(f'Ich brauche die Erlaubnis zu sehen {log_channel.mention}.', ephemeral=True)
        return
    if not (bot_permissions.send_messages and bot_permissions.embed_links):
        await interaction.response.send_message(f'Ich benötige die Erlaubnis, Nachrichten zu versenden und Links einzubetten in {log_channel.mention}.', ephemeral=True)
        return
    if ban_time is not None:
        ban_time = timeparse(ban_time)
        if ban_time is None:
            await interaction.response.send_message('Invalide Ban Zeiten. Bitte nutze folgendes Format: `1d / 1h / 1m / 1s`.\nZum Beispiel: `1d2h3m4s`', ephemeral=True)
            return
    if account_age is not None:
        if not interaction.guild.me.guild_permissions.kick_members:
            await interaction.response.send_message(f'Ich brauche Rechte um Member zu kicken.', ephemeral=True)
            return
        account_age = timeparse(account_age)
        if account_age is None:
            await interaction.response.send_message('Ungültiges Alter des Kontos. Bitte verwenden Sie das folgende Format: `1d / 1h / 1m / 1s`.\nZum Beispiel: `1d2h3m4s`', ephemeral=True)
            return
    c.execute('INSERT OR REPLACE INTO servers VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (interaction.guild.id, verify_channel.id, verify_role.id, log_channel.id, timeout, action, ban_time, account_age,))
    conn.commit()
    await interaction.response.send_message(f'Setup completed.\nYou can now run `/verify_send_pannel`, to send the panel to <#{verify_channel.id}>.', ephemeral=True)

@tree.command(name = 'verify_einstellungen', description = 'Zeige die aktuellen Einstellungen.')
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
async def self(interaction: discord.Interaction):
    c.execute('SELECT * FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if data:
        verify_channel = data[1]
        verify_role = data[2]
        log_channel = data[3]
        timeout = data[4]
        action = data[5]
        ban_time = data[6]
        account_age = data[7]
        embed = discord.Embed(title = 'Aktuelle Einstellungen',
                              description = f'**Verify Channel:** <#{verify_channel}>\n**Verify Role:** <@&{verify_role}>\n**Log Channel:** <#{log_channel}>\n**Timeout:** {Functions.format_seconds(timeout)}\n**Action:** {action}\n**Banned for:** {(Functions.format_seconds(ban_time) if ban_time is not None else None)}\n**Min account age:** {(Functions.format_seconds(account_age) if account_age is not None else None)}',
                              color = 0x2b63b0)
        await interaction.response.send_message(embed = embed, ephemeral=True)
    else:
        await interaction.response.send_message('Es gibt keine Einstellungen für diesen Server.\nBenutze: `/setup`, um diesen Server einzurichten.', ephemeral=True)

@tree.command(name = 'verify-all', description = 'Verify all non-bot users on the server.')
@discord.app_commands.checks.cooldown(1, 3600, key=lambda i: (i.guild_id))
@discord.app_commands.checks.has_permissions(manage_guild = True)
async def self(interaction: discord.Interaction):
    c.execute('SELECT * FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if data:
        i = 0
        verify_role_id = data[2]
        if verify_role_id:
            await interaction.response.send_message('Verifying all users on the server. This can take a while.', ephemeral=True)
            await Functions.send_logging_message(interaction = interaction, kind = 'verify_mass_started')
            verify_role = interaction.guild.get_role(verify_role_id)
            if verify_role is None:
                await interaction.response.send_message('The verify role does not exist.', ephemeral=True)
                return
            for member in interaction.guild.members:
                if not member.bot:
                    if verify_role not in member.roles:
                        try:
                            await member.add_roles(verify_role, reason = 'Verify all users on the server.')
                            i += 1
                        except discord.Forbidden:
                            continue
            await Functions.send_logging_message(interaction = interaction, kind = 'verify_mass_success', mass_amount = i)
            await interaction.edit_original_response(content = f'{interaction.user.mention}\nVerified {i} users on the server.')
        else:
            await interaction.response.send_message('There are no settings for this server.\nUse `/setup` to set-up this server.', ephemeral=True)
    else:
        await interaction.response.send_message('There are no settings for this server.\nUse `/setup` to set-up this server.', ephemeral=True)
        
@tree.context_menu(name="Verify User")
@discord.app_commands.checks.cooldown(1, 60, key=lambda i: (i.user.id, i.data['target_id']))
@discord.app_commands.checks.has_permissions(manage_roles=True)
async def verify_user(interaction: discord.Interaction, member: discord.Member):
    c.execute('SELECT * FROM servers WHERE guild_id = ?', (interaction.guild.id,))
    data = c.fetchone()
    if data:
        verify_role_id = data[2]
        if verify_role_id:
            verify_role = interaction.guild.get_role(verify_role_id)
            if verify_role is None:
                await interaction.response.send_message('Die Rolle verify existiert nicht.', ephemeral=True)
                return
            if not member.bot and verify_role not in member.roles:
                try:
                    await member.add_roles(verify_role, reason=f' {interaction.user.name} verified user via context menu.')
                    await interaction.response.send_message(f'{member.mention} got verified by {interaction.user.mention}.', ephemeral=True)
                    await Functions.send_logging_message(interaction=interaction, kind='user_verify', member=member)
                except discord.Forbidden:
                    await interaction.response.send_message('Ich habe dazu keine Rechte.', ephemeral=True)
            else:
                await interaction.response.send_message(f'{member.mention} ist bereits Verifiziert oder ist ein Bot.', ephemeral=True)
        else:
            await interaction.response.send_message('Es gibt keine Einstellungen für denn Server.\nNutze `/verify_setup` um denn Server aufzusetzen.', ephemeral=True)
    else:
        await interaction.response.send_message('Es gibt keine Einstellungen für denn Server.\nNutze `/verify_setup` um denn Server aufzusetzen.', ephemeral=True)

@tree.command(name='get_userid', description='Print the ID of a given user.')
@discord.app_commands.checks.cooldown(1, 10, key=lambda i: (i.user.id))
@discord.app_commands.describe(user='User to get the ID from.')
async def self(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(content=f'The ID of {user.mention} is: `{user.id}`.', ephemeral=True)


# @tree.command(name='debug_close')
# @discord.app_commands.checks.has_permissions(administrator = True)
# async def self(interaction:discord.Interaction):
#     await interaction.response.send_message("Channel wird gelöscht...",ephemeral=True)
#     channel = interaction.channel
#     c.execute('SELECT * FROM CREATED_TICKETS WHERE CHANNEL_ID = ?', (channel.id,))
#     data_created_tickets = c.fetchone()
#     transcript = await TicketSystem.create_transcript(interaction.channel.id, data_created_tickets[1])
#     user: discord.User = await Functions.get_or_fetch('user', data_created_tickets[1])
#     with open(transcript, 'rb') as f:
#         try:
#              await user.send(file=discord.File(f))
#         except Exception as e:
#             if not e.code == 50007:
#                program_logger.error(f'Fehler beim senden der Nachricht an {user}\n Fehler: {e}')

#     os.remove(transcript)


if __name__ == '__main__':
    if sys.version_info < (3, 11):
        program_logger.critical('Es wird Python 3.11+ benötigt.')
        sys.exit(1)
    if not TOKEN:
        program_logger.critical('Token nicht vorhanden. Bitte Checke deine .env Datei.')
        sys.exit()
    else:
        SignalHandler()
        try:
            bot.run(TOKEN, log_handler=None)
        except discord.errors.LoginFailure:
            program_logger.critical('Ungültiges Token. Bitte überprüfen Sie Ihre .env-Datei')
            sys.exit()
        except asyncio.CancelledError:
            if shutdown:
                pass
