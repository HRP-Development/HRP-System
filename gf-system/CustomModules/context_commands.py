import discord



# Define the context menu command
@discord.app_commands.context_menu(name="User Info")
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.guild_id, i.data['target_id']))
async def user_info(interaction: discord.Interaction, member: discord.Member):
    # Create an embed with user information
    embed = discord.Embed(title=f"User Info: {member.name}", color=discord.Color.blue())
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="Username", value=f"{member.name}#{member.discriminator}", inline=True)
    embed.add_field(name="User ID", value=member.id, inline=True)
    embed.add_field(name="Bot", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="Joined Server", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="Created Account", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

    # Send the embed as a response to the interaction
    await interaction.response.send_message(embed=embed, ephemeral=True)
    

# Add the command to the bot's tree
def setup(tree):
    tree.add_command(user_info)