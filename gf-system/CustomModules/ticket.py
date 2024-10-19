from datetime import datetime

class TicketHTML:
    def __init__(self):
        print("TicketHTML initialized")

    async def create_ticket(bot, channel_id, creator):
                messages = []
                creatorname = await bot.fetch_user(creator)
                creator = creatorname.name
                channel = bot.get_channel(channel_id)
                ticket_id = channel_id
                ticket_name = channel.name
                creator_name = creator
                ticket_status = "Geschlossen"
                closing_date = datetime.now().strftime("%d.%m.%Y | %H:%M:%S")

                async for message in channel.history(limit=None):
                    avatar_url = getattr(message.author.avatar, 'url', None)
                    if message.author.bot:
                         continue
                    if message.attachments:
                        continue
                    if avatar_url is None:
                        avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
                    if message.author.avatar is None:
                        messages.append(f"""
                        <div class="message">
                        <div class='message-header'>                
                            <img src='{avatar_url}'>
                            {message.author.name}
                            {message.created_at.strftime('%d.%m.%Y - %H:%M')}
                        </div>
                            <p class="message-content">{message.content}</p>
                        </div>
                        """) 
                    else:
                        messages.append(f"""
                        <div class="message">
                        <div class='message-header'>                
                            <img src='{message.author.avatar.url}'>
                            {message.author.name}
                            {message.created_at.strftime('%d.%m.%Y - %H:%M')}
                        </div>
                            <p class="message-content">{message.content}</p>
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
                                margin: 20px;
                                padding: 40px;
                                line-height: 1.6;
                                background-color: #313338;
                                color: #fff;
                                outline: 4px solid #9900ff;
                                outline-offset: 6px;
                            }}

                            .header {{
                                position: fixed;
                                top: 0;
                                left: 0;
                                width: 100%;
                                background-color: #212121;
                                padding: 10px 20px;
                                z-index: 1000;
                                display: flex;
                                justify-content: space-between;
                                align-items: center;
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
                            }}

                            .ticket-header {{
                                background-color: #444;
                                padding: 10px;
                                border-radius: 5px;
                                margin-bottom: 20px;
                            }}

                            .ticket-info {{
                                margin-bottom: 20px;
                            }}

                            .message {{
                                margin-bottom: 15px;
                            }}
                            
                            .message-header {{
                                display: flex;
                                align-items: center;
                                font-weight: bold;
                                margin-bottom: 5px;
                            }}
                            

                            .message-header img {{
                                width: 50px;
                                height: 50px;
                                border-radius: 50%;
                                margin-right: 10px;
                            }}

                            .message-content {{
                                background-color: #1b1b1b;
                                padding: 10px;
                                border-radius: 5px;
                                color: #FFFFFF; 
                            }}

                            .footer {{
                                position: fixed;
                                bottom: 0;
                                left: 0;
                                width: 100%;
                                background-color: #212121;
                                padding: 10px 20px;
                                display: flex;
                                justify-content: center;
                                align-items: center;
                                z-index: 1000;
                            }}

                            .footer a {{
                                color: #fff;
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

                        <a href="https://gaming-networks.net" target="_blank">
                            <i class="fas fa-home"></i> Website
                        </a>

                        <a href="https://discord.gg/gamingnetworks" target="_blank">
                            <i class="fab fa-discord"></i> Discord
                        </a>

                        <a href="" target="_blank">
                            <i class="fab fa-steam"></i> Steam
                        </a>
                    </div>

                </body>
                </html>
                """
                APP_FOLDER_NAME = 'HRP-Sys'
                BUFFER_FOLDER = f'{APP_FOLDER_NAME}/Buffer/'
                ticket_path = f"{BUFFER_FOLDER}ticket-{channel_id}.html"
                with open(f"{ticket_path}", "w", encoding='utf-8') as file:
                    file.write(html)
                return f"{ticket_path}"
        

