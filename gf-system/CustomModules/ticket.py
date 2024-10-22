from datetime import datetime
import re

class TicketHTML:
    def __init__(self, bot, buffer_folder):
        self.bot = bot
        self.buffer_folder = buffer_folder

    async def create_ticket(self, channel_id, creator):
        messages = []
        creatorname = await self.bot.fetch_user(creator)
        creator = creatorname.name
        channel = self.bot.get_channel(channel_id)
        ticket_id = channel_id
        ticket_name = channel.name
        creator_name = creator
        ticket_status = "Geschlossen"
        closing_date = datetime.now().strftime("%d.%m.%Y | %H:%M:%S")

        async for message in channel.history(limit=None):
            avatar_url = getattr(message.author.avatar, 'url', None)
            if avatar_url is None:
                avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
            
            if re.match(r"^Hey listen <@&\d+>, es gibt ein neues Ticket\.$", message.content):
                continue

            # Process normal messages
            if message.content:
                messages.append(f"""
                <div class="message">
                    <img src='{avatar_url}' alt='avatar' class="avatar">
                    <div class="message-content">
                        <div class='message-header'>
                            <span class="author-name">{message.author.name}</span>
                            <span class="timestamp">{message.created_at.strftime('%d.%m.%Y - %H:%M')}</span>
                        </div>
                        <p>{message.content}</p>
                    </div>
                </div>
                """)
            
            # Process embedded messages
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
                            <span class="timestamp">{message.created_at.strftime('%d.%m.%Y - %H:%M')}</span>
                        </div>
                        <div class="embed">
                            <strong>{embed_title}</strong>
                            <p>{embed_description}</p>
                        </div>
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
        <title>Ticket #{ticket_id}</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
        
                body {{
                    font-family: 'Roboto', sans-serif;
                    background-color: #36393f;
                    color: #dcddde;
                    margin: 0;
                    padding: 0;
                }}

                .header {{
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    background-color: #202225;
                    padding: 10px 20px;
                    z-index: 1000;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    color: #fff;
                }}

                .header-left {{
                    display: flex;
                    align-items: center;
                }}

                .header img {{
                    width: 50px;
                    height: 50px;
                    margin-right: 10px;
                }}

                .header-text {{
                    font-size: 24px;
                    font-weight: 700;
                }}

                .ticket-id {{
                    font-size: 18px;
                    font-weight: 700;
                    margin-right: 50px;
                }}

                .content {{
                    margin-top: 80px;
                    padding: 20px;
                }}

                .ticket-header {{
                    background-color: #2f3136;
                    padding: 15px;
                    border-radius: 5px;
                    margin-bottom: 20px;
                    color: #b9bbbe;
                }}

                .ticket-info {{
                    margin-bottom: 20px;
                }}

                .message {{
                    display: flex;
                    align-items: flex-start;
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

                .message-header {{
                    display: flex;
                    justify-content: space-between;
                    font-size: 14px;
                    margin-bottom: 5px;
                }}

                .author-name {{
                    font-weight: bold;
                    color: #fff;
                }}

                .timestamp {{
                    color: #72767d;
                }}

                .embed {{
                    background-color: #2f3136;
                    padding: 10px;
                    border-radius: 5px;
                    margin-top: 5px;
                    color: #7289da;
                }}

                .footer {{
                    position: fixed;
                    bottom: 0;
                    left: 0;
                    width: 100%;
                    background-color: #202225;
                    padding: 10px 20px;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    z-index: 1000;
                    color: #fff;
                }}

                .footer a {{
                    color: #b9bbbe;
                    text-decoration: none;
                    margin: 0 40px;
                }}

                .footer a:hover {{
                    color: #07a66d;
                }}

            </style>
        </head>

        <body>
        <div class="header">
            <div class="header-left">

                <img src="https://i.imgur.com/Tv7PpZm.png" alt="Logo">
                <span class="header-text">HRP | Community </span>

            </div>

            <div class="ticket-id">Ticket #{ticket_id}</div>

        </div>

        <div class="content">
            <div class="ticket-header">

                <h1>Ticket #{ticket_id}</h1>
                <p>Beendet am: {closing_date}</p>

            </div>

            <div class="ticket-info">

                <h2>Ticket Informationen</h2>
                <p><strong>Ticket Name:</strong> {ticket_name}</p>
                <p><strong>Erstellt von:</strong> {creator_name}</p>
                <p><strong>Status:</strong> {ticket_status}</p>

            </div>

            <div class="ticket-messages">
                <h2>Nachrichtenverlauf</h2>
                {messages}
            </div>
        </div>

        <div class="footer">

            <a href="https://url.bloodygang.com/hrpcommunity" target="_blank">
                <i class="fas fa-home"></i> Website
            </a>

            <a href="https://url.bloodygang.com/hrpcommunity" target="_blank">
                <i class="fab fa-discord"></i> Discord
            </a>

            <a href="https://url.bloodygang.com/hrpcommunity" target="_blank">
                <i class="fab fa-steam"></i> Steam
            </a>
        </div>

        </body>
        </html>
        """
        ticket_path = f"{self.buffer_folder}ticket-{channel_id}.html"
        with open(f"{ticket_path}", "w", encoding='utf-8') as file:
            file.write(html)
        return f"{ticket_path}"
