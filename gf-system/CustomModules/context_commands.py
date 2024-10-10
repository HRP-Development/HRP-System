import discord

@discord.app_commands.context_menu(name="User Info")
@discord.app_commands.checks.cooldown(1, 30, key=lambda i: (i.guild_id, i.data['target_id']))
async def user_info(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f"User Info: {member.name}", color=discord.Color.dark_orange())
    embed.set_thumbnail(url=member.avatar.url if member.avatar else member.default_avatar.url)
    embed.add_field(name="Nutzername", value=f"{member.name}#{member.discriminator}", inline=True)
    embed.add_field(name="User ID", value=member.id, inline=True)
    embed.add_field(name="Bot", value=member.bot, inline=True)
    embed.add_field(name="Top Role", value=member.top_role.mention, inline=True)
    embed.add_field(name="Gejoint am", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)
    embed.add_field(name="Account erstellt am", value=member.created_at.strftime("%Y-%m-%d %H:%M:%S"), inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

def setup(tree):
    tree.add_command(user_info)