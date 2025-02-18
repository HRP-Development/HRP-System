import aiohttp
import discord
import os
import py7zr
import pytz
import re
import shutil
import zlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class TicketHTML:
    def __init__(self, bot, buffer_folder):
        self.bot = bot
        self.buffer_folder = buffer_folder

    def calculate_file_crc32(self, file_path):
        crc32_hash = 0
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                crc32_hash = zlib.crc32(byte_block, crc32_hash)
        return format(crc32_hash & 0xFFFFFFFF, '08x')

    async def replace_mentions(self, message_content, guild):
        code_block_pattern = re.compile(r"```(?:.|\n)*?```|`[^`]*`")
    
        segments = []
        last_pos = 0
    
        for match in code_block_pattern.finditer(message_content):
            segments.append(("text", message_content[last_pos:match.start()]))
            segments.append(("code", match.group(0)))
            last_pos = match.end()
    
        segments.append(("text", message_content[last_pos:]))
    
        def mention_replacer(match):
            mention = match.group(0)
            
            if mention.startswith('<@&'):
                role_id = mention[3:-1]
                role = discord.utils.get(guild.roles, id=int(role_id))
                if role:
                    return f"[Rolle erwähnt: {role.name}]"
            
            elif mention.startswith('<@'):
                user_id = mention[2:-1].lstrip('!')
                user = guild.get_member(int(user_id))
                if user:
                    return f"[{"Bot" if user.bot else "User"} erwähnt: {user.display_name}]"
            
            elif mention.startswith('<#'):
                channel_id = mention[2:-1]
                channel = discord.utils.get(guild.channels, id=int(channel_id))
                if channel:
                    return f"[Channel erwähnt: {channel.name}]"
            
            return mention
    
        mention_pattern = re.compile(r"<@!?[0-9]+>|<@&[0-9]+>|<#\d+>")
    
        for i, (seg_type, content) in enumerate(segments):
            if seg_type == "text":
                segments[i] = ("text", mention_pattern.sub(mention_replacer, content))
    
        final_message = ''.join(content for _, content in segments)
        return final_message

    async def embed_emojis_in_text(self, message_content, media_folder, channel_id):
        emoji_pattern = r"<a?:\w+:\d+>"
        emojis_found = re.findall(emoji_pattern, message_content)
        downloaded_emoji_hashes = {}
        
        for emoji in emojis_found:
            uuid_name = uuid4()
            emoji_id = emoji.split(':')[-1][:-1]
            is_animated = emoji.startswith('<a')
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if is_animated else 'png'}"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(emoji_url) as resp:
                        if resp.status == 200:
                            emoji_file_path = os.path.join(media_folder, f'{uuid_name}.png')
                            with open(emoji_file_path, 'wb') as f:
                                f.write(await resp.read())

                            emoji_hash = self.calculate_file_crc32(emoji_file_path)
        
                            if emoji_hash in downloaded_emoji_hashes:
                                os.remove(emoji_file_path)
                                emoji_file_path = downloaded_emoji_hashes[emoji_hash]
                            else:
                                downloaded_emoji_hashes[emoji_hash] = emoji_file_path

                            message_content = message_content.replace(
                                emoji,
                                f"<img src='{os.path.join(f"ticket-{channel_id}", Path(emoji_file_path).name)}' alt='emoji' style='width: 20px; height: 20px;'>"
                            )
                except aiohttp.ClientError as e:
                    print(f"Error downloading emoji {emoji}: {e}")
                    continue
    
        return message_content

    async def create_transcript(self, channel_id: int, creator_id: int):
        messages = []
        downloaded_files_hashes = {}
        downloaded_emoji_hashes = {}
        op: discord.Member = await self.bot.fetch_user(creator_id)
        channel: discord.TextChannel = self.bot.get_channel(channel_id)
        if not channel:
            channel = self.bot.fetch_channel(channel_id)
        ticket_status = "Geschlossen"
        closing_date = datetime.now().strftime("%d.%m.%Y | %H:%M:%S")
        berlin_tz = pytz.timezone('Europe/Berlin')
        
        media_folder = os.path.join(self.buffer_folder, f"ticket-{channel_id}")
        os.makedirs(media_folder, exist_ok=True)

        async for message in channel.history(limit=None):
            avatar_url = getattr(message.author.avatar, 'url', None)
            if avatar_url is None:
                avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"

            if re.match(r"^Hey listen <@&\d+>, es gibt ein neues Ticket\.$", message.content):
                continue

            reactions_html = ""
            if message.reactions:
                reactions_html = "<div class='reactions' style='display: flex; flex-wrap: wrap; gap: 10px;'>"
                for reaction in message.reactions:
                    reaction_color = "#FFD700" if reaction.burst_count >0 else "rgba(52, 56, 58, 0.1)"
                    uuid_name = uuid4()
                    emoji_file_path = os.path.join(media_folder, f'{uuid_name}.png')
            
                    emoji_url = None
                    if isinstance(reaction.emoji, discord.PartialEmoji):
                        emoji_url = reaction.emoji.url
            
                        if emoji_url:
                            async with aiohttp.ClientSession() as session:
                                try:
                                    async with session.get(emoji_url) as resp:
                                        if resp.status == 200:
                                            with open(emoji_file_path, 'wb') as f:
                                                f.write(await resp.read())
                                except aiohttp.ClientError:
                                    continue

                            emoji_hash = self.calculate_file_crc32(emoji_file_path)
        
                            if emoji_hash in downloaded_emoji_hashes:
                                os.remove(emoji_file_path)
                                emoji_file_path = downloaded_emoji_hashes[emoji_hash]
                            else:
                                downloaded_emoji_hashes[emoji_hash] = emoji_file_path
            
                    users = []
                    async for user in reaction.users():
                        users.append(user.name)
                    users_list = ", ".join(users)
                    
                    reactions_html += f"""
                        <span class='reaction' style='border: 2px solid {reaction_color};'>
                            {'<img src=\'' + os.path.join(f"ticket-{channel_id}", Path(emoji_file_path).name) + '\' alt=\'' + reaction.emoji.name + '\' style=\'width: 20px; height: 20px;\'>' if isinstance(reaction.emoji, discord.PartialEmoji) else reaction.emoji}
                            {users_list} ({reaction.count})
                        </span>
                    """
                reactions_html += "</div>"

            if message.content or message.attachments:
                attachment_html = ""
                for attachment in message.attachments:
                    uuid_name = uuid4()
                    file_extension = attachment.filename.split('.')[-1].lower()
                    media_file_path = os.path.join(media_folder, f'{uuid_name}.{file_extension}')
                    
                    if attachment.size <= 8 * 1024 * 1024:
                        await attachment.save(media_file_path)

                        file_hash = self.calculate_file_crc32(media_file_path)
        
                        if file_hash in downloaded_files_hashes:
                            os.remove(media_file_path)
                            media_file_path = downloaded_files_hashes[file_hash]
                        else:
                            downloaded_files_hashes[file_hash] = media_file_path
            
                        if file_extension in ['png', 'jpg', 'jpeg', 'gif']:
                            attachment_width = attachment.width
                            img_html = f"<img src='{os.path.join(f"ticket-{channel_id}", Path(media_file_path).name)}' alt='{attachment.filename}' "
            
                            if attachment_width > 400:
                                img_html += "class='attachment-image'"
                            img_html += ">"
                            attachment_html += img_html
            
                        elif file_extension in ['mp4', 'webm']:
                            attachment_html += f"""
                            <video controls class="attachment-video">
                                <source src='{os.path.join(f"ticket-{channel_id}", Path(media_file_path).name)}' type='video/{file_extension}'>
                                Your browser does not support the video tag.
                            </video>
                            """
                        else:
                            attachment_html += f"<p>Datei: <a href='{os.path.join(f"ticket-{channel_id}", Path(media_file_path).name)}' download>{attachment.filename}</a></p>"
            
                    else:
                        attachment_html += f"<p>[TICKET TRANSCRIPT] Die Datei <strong>{attachment.filename}</strong> ist zu groß (maximal 8 MB) und konnte nicht heruntergeladen werden.</p>"
            
                messages.append(f"""
                <div class="message">
                    <img src='{avatar_url}' alt='avatar' class="avatar">
                    <div class="message-content">
                        <div class='message-header'>
                            <span class="author-name">{message.author.name}</span>
                            <span class="timestamp">{message.created_at.astimezone(berlin_tz).strftime('%d.%m.%Y - %H:%M')}</span>
                        </div>
                        <p>{await self.replace_mentions(await self.embed_emojis_in_text(message.content, media_folder, channel.id), channel.guild)}</p>
                        {attachment_html}
                        {reactions_html}
                    </div>
                </div>
                """)

            for embed in message.embeds:
                embed_title = embed.title if embed.title else "No Title"
                embed_description = embed.description if embed.description else "No Description"
                if embed_title == "Admincommands":
                    continue
                messages.append(f"""
                <div class="message">
                    <img src='{avatar_url}' alt='avatar' class="avatar">
                    <div class="message-content">
                        <div class='message-header'>
                            <span class="author-name">{message.author.name}</span>
                            <span class="timestamp">{message.created_at.astimezone(berlin_tz).strftime('%d.%m.%Y - %H:%M')}</span>
                        </div>
                        <div class="embed">
                            <strong>{embed_title}</strong>
                            <p>{embed_description}</p>
                        </div>
                        {reactions_html}
                    </div>
                </div>
                """)

        messages.reverse()
        messages = "".join(messages)

        html = f"""
        <!DOCTYPE html>
        <html lang="de">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Ticket #{channel_id}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
            <style>
                /* Globales Styling */
                body {{
                    font-family: 'Roboto', sans-serif;
                    background-color: #36393f;
                    color: #dcddde;
                    margin: 0;
                    padding: 0;
                }}
                .header, .footer {{
                    background-color: #202225;
                    padding: 10px 20px;
                    color: white;
                }}
                .header {{
                    position: fixed;
                    top: 0;
                    width: 100%;
                    z-index: 1000;
                }}
				.footer {{
					position: fixed;
					bottom: 0;
					width: 100%;
					display: flex;
					justify-content: center;
					background-color: #333; /* Dunkles Grau für bessere Lesbarkeit */
					padding: 10px 0; /* Platz nach oben und unten für den Footer */
				}}
				
				.footer a {{
					color: inherit; /* Setzt die Textfarbe auf die Standardfarbe des Browsers */
					text-decoration: none;
					margin: 0 15px; /* Fügt Abstand zwischen den Links hinzu */
				}}
				
				.footer i {{
					font-size: 20px;
					margin-right: 5px; /* Fügt einen kleinen Abstand zwischen Icon und Text hinzu */
				}}
				
				.footer a .fa-home {{
					color: #fff; /* Weiß für das Haus-Icon */
				}}
				
				.footer a .fa-discord {{
					color: #7289da; /* Original Discord-Farbe */
				}}
				
				.footer a .fa-steam {{
					color: #00adee; /* Original Steam-Farbe */
				}}
                .content {{
                    margin-top: 80px;
                    margin-bottom: 80px;
                    padding: 20px;
                }}
                .message {{
                    display: flex;
                    margin-bottom: 20px;
                }}
                .avatar {{
                    width: 40px;
                    height: 40px;
                    border-radius: 50%;
                    margin-right: 15px;
                }}
                .message-content {{
                    background-color: #40444b;
                    padding: 10px;
                    border-radius: 5px;
                    width: 100%;
                }}
                .attachment-image {{
                    max-width: 400px;
                    border-radius: 5px;
                    margin-top: 10px;
                }}
                .attachment-video {{
                    max-width: 100%;
                    max-height: 400px;
                    margin-top: 10px;
                    border-radius: 5px;
                }}
                .reactions {{
                    margin-top: 5px;
                    display: flex;
                    gap: 10px;
                }}
                .reaction {{
                    background-color: #7289da;
                    padding: 2px 6px;
                    border-radius: 3px;
                    color: white;
                }}
            </style>
        </head>

        <body>
        <div class="header">
            <div>
                <img src="{channel.guild.icon}" alt="Logo" style="width: 50px; height: 50px;">
                <span>{channel.guild.name} | Ticket #{channel_id}</span>
            </div>
        </div>

        <div class="content">
            <div class="ticket-info">
                <h2>Ticket #{channel_id}</h2>
                <p><strong>Erstellt von:</strong> {op.name}</p>
                <p><strong>Status:</strong> {ticket_status}</p>
                <p><strong>Beendet am:</strong> {closing_date}</p>
            </div>
            <div class="ticket-messages">
                <h2>Nachrichtenverlauf</h2>
                {messages}
            </div>
        </div>

        <div class="footer">
            <a href="https://shop.hrp-community.net" target="_blank">
                <i class="fas fa-home"></i> Website
            </a>
            <a href="https://url.serpensin.com/hrpcommunity" target="_blank">
                <i class="fab fa-discord"></i> Discord
            </a>
            <a href="https://steamcommunity.com/groups/hazeroleplay" target="_blank">
                <i class="fab fa-steam"></i> Steam
            </a>
        </div>
        </body>
        </html>
        """

        html_file_path = os.path.join(self.buffer_folder, f"ticket-{channel_id}.html")
        with open(html_file_path, "w", encoding='utf-8') as file:
            file.write(html)
        
        archive_name = f"{channel.guild.name}-ticket-{channel_id}.7z"
        zip_path = os.path.join(self.buffer_folder, archive_name)
        
        with py7zr.SevenZipFile(zip_path, 'w') as archive:
            archive.write(html_file_path, os.path.basename(html_file_path))
            for root, _, files in os.walk(media_folder):
                for file in files:
                    archive.write(os.path.join(root, file), os.path.join(os.path.basename(root), file))
        
        try:
            if os.path.getsize(zip_path) > 25 * 1024 * 1024:
                os.remove(zip_path)
                return html_file_path
            else:
                os.remove(html_file_path)
                return zip_path
        finally:
            shutil.rmtree(media_folder)
        
