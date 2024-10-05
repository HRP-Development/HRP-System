import discord
import os
import sqlite3

class z_logger:
    def __init__(self, channel):
        self.log_channel = channel
        
    async def log_role_change(self, member, before, after):
        embed = discord.Embed(title="Role Change", color=0x00ff00)
        embed.add_field(name="User", value=member.mention, inline=False)
        embed.add_field(name="Before", value=before.mention, inline=False)
        embed.add_field(name="After", value=after.mention, inline=False)
        await self.log_channel.send(embed=embed)
        
    async def log_channel_create(self, channel):
        embed = discord.Embed(
            title="📁 Neuer Channel erstellt",
            description=f"Channel **{channel.name}** wurde erstellt.",
            color=discord.Color.green()
        )
        await self.log_channel.send(embed=embed)

    async def log_channel_delete(self, channel):
        embed = discord.Embed(
            title="🗑️ Channel gelöscht",
            description=f"Channel **{channel.name}** wurde gelöscht.",
            color=discord.Color.red()
        )
        await self.log_channel.send(embed=embed)

    async def log_channel_update(self, before, after):
        embed = discord.Embed(
            title="🔧 Channel aktualisiert",
            description=f"Channel **{before.name}** wurde bearbeitet.",
            color=discord.Color.orange()
        )
        if before.name != after.name:
            embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)
        await self.log_channel.send(embed=embed)

    async def log_role_create(self, role):
        embed = discord.Embed(
            title="➕ Neue Rolle erstellt",
            description=f"Rolle **{role.name}** wurde erstellt.",
            color=discord.Color.green()
        )
        await self.log_channel.send(embed=embed)

    async def log_role_delete(self, role):
        embed = discord.Embed(
            title="➖ Rolle gelöscht",
            description=f"Rolle **{role.name}** wurde gelöscht.",
            color=discord.Color.red()
        )
        await self.log_channel.send(embed=embed)

    async def log_role_update(self, before, after):
        embed = discord.Embed(
            title="🔄 Rolle aktualisiert",
            description=f"Rolle **{before.name}** wurde geändert.",
            color=discord.Color.orange()
        )
        if before.name != after.name:
            embed.add_field(name="Name geändert", value=f"Von **{before.name}** zu **{after.name}**", inline=False)
        await self.log_channel.send(embed=embed)
        
    async def log_message_edit(self, before, after):
        if before.content != after.content:
            embed = discord.Embed(
                title="✏️ Nachricht bearbeitet",
                description=f"Nachricht von {before.author.mention} wurde bearbeitet.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Vorher", value=before.content, inline=False)
            embed.add_field(name="Nachher", value=after.content, inline=False)
            await self.log_channel.send(embed=embed)
        
    async def log_guild_update(self, before, after):
       embed = discord.Embed(
           title="⚙️ Server-Einstellungen geändert",
           description=f"Der Server **{before.name}** hat Änderungen erfahren.",
           color=discord.Color.purple()
       )

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

       await self.log_channel.send(embed=embed)
        

