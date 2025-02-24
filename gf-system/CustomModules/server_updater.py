import aiohttp
import asyncio
import discord
import paramiko
import logging



# Setup
def setup(client:discord.Client, tree: discord.app_commands.CommandTree, server_ip:str, api_token: str, sshKey_pw: str, logger: logging.Logger = None):
    global _bot, _logger, _api_token, _server_ip, _sshKey_pw
    _bot, _api_token, _server_ip, _sshKey_pw = client, api_token, server_ip, sshKey_pw

    if tree is None:
        raise ValueError("Command tree cannot be None.")
    if _bot is None:
        raise ValueError("Discord client cannot be None.")

    if logger is None:
        logger = logging.getLogger("null")
        logger.addHandler(logging.NullHandler)
    _logger = logger.getChild("ServerUpdater")

    tree.add_command(_gameserver_update)

    _logger.info("Module has been set up.")



_allowed_jvs = [970119359840284743,      # Serpensin
                587018112134807567,      # Gravefist
                434713695084609537,      # Bright
                ]
_allowed_darkrp = [970119359840284743,   # Serpensin
                587018112134807567,      # Gravefist
                434713695084609537,      # Bright
                690500302331183154,      # Raymond
                ]
_allowed_scprp = [970119359840284743,    # Serpensin
                587018112134807567,      # Gravefist
                434713695084609537,      # Bright
                1149314526244786276,     # Schluxx
                ]
_server_list = {
    "jvs": "6c7dbfba",
    "darkrp": "01063651",
    "scprp": "8854ea1e",
}



# Main functions
async def _send_command_to_gameserver(server_id: int, command: str) -> bool:
    """
    Sends a command to the specified game server.

    Args:
        server_id (int): The ID of the server to which the command will be sent.
        command (str): The command to be executed on the server.

    Returns:
        bool: True if the command was successfully sent, False otherwise.
    """
    url = f"https://panel.hrp-community.net/api/client/servers/{server_id}/command"
    headers = {
        "Authorization": f"Bearer {_api_token}",
        "Content-Type": "application/json"
    }
    data = {
        "command": command
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 204:
                    return True
                else:
                    _logger.error(
                        f"Failed to send command '{command}' to server {server_id}. Status: {response.status}, Response: {await response.text()}")
                    return False
        except aiohttp.ClientError as e:
            _logger.error(f"HTTP request failed: {e}")
            return False

async def _send_power_action_to_gameserver(server_id: int, command: str) -> bool:
    """
    Sends a power action command to the specified game server.

    Args:
        server_id (int): The ID of the server to which the power action will be sent.
        command (str): The power action command to be executed on the server (e.g., "restart", "start", "stop").

    Returns:
        bool: True if the power action command was successfully sent, False otherwise.
    """
    url = f"https://panel.hrp-community.net/api/client/servers/{server_id}/power"
    headers = {
        "Authorization": f"Bearer {_api_token}",
        "Content-Type": "application/json"
    }
    data = {
        "signal": command
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 204:
                    return True
                else:
                    _logger.error(f"Failed to send power action '{command}' to server {server_id}. Status: {response.status}, Response: {await response.text()}")
                    return False
        except aiohttp.ClientError as e:
            _logger.error(f"HTTP request failed: {e}")
            return False

async def _send_ssh_command(command: str) -> bool:
    """
    Sends an SSH command to the server.

    Args:
        command (str): The command to be executed on the server.

    Returns:
        bool: True if the command was successfully executed, False otherwise.
    """
    key = paramiko.Ed25519Key.from_private_key_file("key.pem", password=_sshKey_pw)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(_server_ip, 22, "root", pkey=key)
        stdin, stdout, stderr = client.exec_command(command)
        error_output = stderr.read().decode('utf-8').strip()
        client.close()
        if error_output:
            _logger.error(f"SSH command error output: {error_output}")
            return False
        return True
    except Exception as e:
        _logger.error(f"Failed to connect to {_server_ip} via SSH. Error: {e}")
        return False






# Discord AppCommands (/)
@discord.app_commands.command(name="gameserver_update", description="Updates the game server with the latest version of the server files from GitHub.")
@discord.app_commands.checks.cooldown(1, 600, key=lambda i: (i.user.id))
@discord.app_commands.describe(server = "The server to update.")
@discord.app_commands.choices(
    server=[discord.app_commands.Choice(name=k, value=k) for k in _server_list]
)
@discord.app_commands.guild_only
async def _gameserver_update(interaction: discord.Interaction, server: str):
    await interaction.response.defer(ephemeral=True)

    allowed_users = {"jvs": _allowed_jvs, "darkrp": _allowed_darkrp, "scprp": _allowed_scprp}.get(server)
    if allowed_users is None:
        await interaction.followup.send("❌ Invalid server.")
        return

    if interaction.user.id not in allowed_users:
        await interaction.followup.send("❌ You are not allowed to use this command.")
        return

    await interaction.followup.send("🔄 Updating server... [1/3]")
    
    if not await _send_ssh_command(f"./{server}_apps-update.py"):
        await interaction.edit_original_response(content="❌ Failed to connect to the server.")
        return

    if not await _send_command_to_gameserver(_server_list[server], "announce_restart 2"):
        await interaction.edit_original_response(content="❌ Failed to send restart announcement.")
        return
    
    await interaction.edit_original_response(content="✅ Restart announcement sent. Automatic restart in 2 minutes. [2/3]")
    await asyncio.sleep(60 * 2)

    if not await _send_power_action_to_gameserver(_server_list[server], "restart"):
        await interaction.edit_original_response(content="❌ Failed to restart the server.")
        return

    await interaction.edit_original_response(content="✅ Server restarted successfully! [3/3]")



