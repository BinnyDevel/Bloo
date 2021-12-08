import datetime
import json
import traceback

import aiohttp
import discord
from aiocache.decorators import cached
from discord.commands import slash_command
from discord.commands.commands import Option
from discord.ext import commands
from utils.autocompleters import get_ios_cfw, ios_autocomplete, jb_autocomplete
from utils.config import cfg
from utils.context import BlooContext
from utils.logger import logger
from utils.permissions.checks import (PermissionsFailure,
                                      whisper_in_general)


@cached(ttl=3600)
async def get_jailbreaks_jba():
    """Gets all apps on Jailbreaks.app

    Returns
    -------
    dict
        "Apps"
    """
    res_apps = []
    async with aiohttp.ClientSession() as session:
        async with session.get("https://jailbreaks.app/json/apps.json") as resp:
            if resp.status == 200:
                res_apps = await resp.json()
    return res_apps


@cached(ttl=1800)
async def get_signed_status():
    """Gets Jailbreaks.app's signed status"""
    signed = []
    async with aiohttp.ClientSession() as session:
        async with session.get("https://jailbreaks.app/status.php") as resp:
            if resp.status == 200:
                res = await resp.text()
                signed = json.loads(res)
    return signed


async def iterate_apps(query) -> dict:
    """Iterates through Jailbreaks.app apps, looking for a matching query

    Parameters
    ----------
    query : str
        "App to look for"

    Returns
    -------
    dict
        "List of apps that match the query"

    """
    apps = await get_jailbreaks_jba()
    for possibleApp in apps:
        if possibleApp.get('name').lower() == query.lower().replace("œ", "oe"):
            return possibleApp


class iOSCFW(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @whisper_in_general()
    @slash_command(guild_ids=[cfg.guild_id], description="Get info about a jailbreak.")
    async def jailbreak(self, ctx: BlooContext, name: Option(str, description="Name of the jailbreak", autocomplete=jb_autocomplete, required=True)) -> None:
        """Fetches info of jailbreak

        Example usage
        -------------
        /jailbreak name:<name>

        Parameters
        ----------
        name : str
            "Name of jailbreak"
        """
        response = await get_ios_cfw()

        matching_jbs = [jb for jb in response.get(
            "jailbreak") if jb.get("name").lower() == name.lower()]
        if not matching_jbs:
            raise commands.BadArgument("No jailbreak found with that name.")

        jb = matching_jbs[0]
        info = jb.get('info')

        color = info.get("color")
        if color is not None:
            color = int(color.replace("#", ""), 16)

        embed = discord.Embed(title=jb.get(
            'name'), color=color or discord.Color.random())
        view = discord.ui.View()

        if info is not None:
            embed.set_thumbnail(url=f"https://ios.cfw.guide{info.get('icon')}")

            embed.add_field(
                name="Version", value=info.get("latestVer"), inline=True)

            if info.get("firmwares"):
                soc = f"Works with {info.get('soc')}" if info.get(
                    'soc') else ""

                firmwares = info.get("firmwares")
                if len(firmwares) > 2:
                    firmwares = ", ".join(firmwares)
                else:
                    firmwares = "-".join(info.get("firmwares"))

                embed.add_field(name="Compatible with",
                                value=f'iOS {firmwares}\n{f"**{soc}**" if soc else ""}', inline=True)
            else:
                embed.add_field(name="Compatible with",
                                value="Unavailable", inline=True)

            embed.add_field(
                name="Type", value=info.get("type"), inline=False)

            if info.get("website") is not None:
                view.add_item(discord.ui.Button(label='Website', url=info.get(
                    "website").get("url"), style=discord.ButtonStyle.url))

            if info.get('guide'):
                for guide in info.get('guide'):
                    view.add_item(discord.ui.Button(
                        label=f'{guide.get("name")} Guide', url=f"https://ios.cfw.guide{guide.get('url')}", style=discord.ButtonStyle.url))
            if info.get('notes') is not None:
                embed.add_field(
                    name="Notes", value=info.get('notes'), inline=False)

            embed.set_footer(text="Powered by https://ios.cfw.guide")
        else:
            embed.description = "No info available."

        jba = await iterate_apps(jb.get("name"))
        signed = await get_signed_status()
        if jba is None or signed.get('status') != 'Signed':
            view.add_item(discord.ui.Button(label='Install with Jailbreaks.app',
                          url=f"https://api.jailbreaks.app/", style=discord.ButtonStyle.url, disabled=True))
        else:
            view.add_item(discord.ui.Button(label='Install with Jailbreaks.app',
                          url=f"https://api.jailbreaks.app/install/{jba.get('name').replace(' ', '')}", style=discord.ButtonStyle.url))

        await ctx.respond_or_edit(embed=embed, ephemeral=ctx.whisper, view=view)

    @whisper_in_general()
    @slash_command(guild_ids=[cfg.guild_id], description="Get info about an iOS version.")
    async def firmware(self, ctx: BlooContext, version: Option(str, description="Version of the firmware", autocomplete=ios_autocomplete, required=True)) -> None:
        """Fetches info of an iOS version

        Example usage
        -------------
        /firmware version:<version>

        Parameters
        ----------
        version : str
            "Version of iOS"
        """
        response = await get_ios_cfw()
        ios = response.get("ios")
        ios = [ios for ios in ios if f"{ios.get('version')} ({ios.get('build')})" == version]

        if not ios:
            raise commands.BadArgument("No firmware found with that version.")

        matching_ios = ios[0]
        embed = discord.Embed(title=f"iOS {matching_ios.get('version')}", color=discord.Color.random())
        embed.add_field(name="Build number", value=matching_ios.get("build"), inline=True)

        release = matching_ios.get("released")
        if release is not None:
            try:
                release_date = datetime.datetime.strptime(release, "%Y-%m-%d")
                embed.add_field(name="Release date", value=f"{discord.utils.format_dt(release_date, 'D')} ({discord.utils.format_dt(release_date, 'R')})", inline=True)
            except ValueError:
                embed.add_field(name="Release date", value=release, inline=True)

        devices_supported = {
            "iPhone": 0,
            "iPod": 0,
            "iPad": 0,
            "AppleTV": 0,
            "Watch": 0,
        }
        
        for device in matching_ios.get("devices"):
            for device_type in devices_supported:
                if device_type in device:
                    devices_supported[device_type] += 1

        supported_devices_str = ""
        total_count = 0
        for device, count in devices_supported.items():
            total_count += count
            if count:
                if device == "AppleTV":
                    device = "Apple TV"
                elif device == "Watch":
                    device = "Apple Watch"
                supported_devices_str += f"{device}: {count}\n"

        supported_devices_str += f"({total_count} total)"

        embed.add_field(name="Supported devices", value=supported_devices_str or "None found", inline=False)

        await ctx.respond_or_edit(embed=embed, ephemeral=ctx.whisper)

    @firmware.error
    @jailbreak.error
    async def info_error(self, ctx: BlooContext, error):
        if isinstance(error, discord.ApplicationCommandInvokeError):
            error = error.original

        if (isinstance(error, commands.MissingRequiredArgument)
            or isinstance(error, PermissionsFailure)
            or isinstance(error, commands.BadArgument)
            or isinstance(error, commands.BadUnionArgument)
            or isinstance(error, commands.MissingPermissions)
            or isinstance(error, commands.BotMissingPermissions)
            or isinstance(error, commands.MaxConcurrencyReached)
                or isinstance(error, commands.NoPrivateMessage)):
            await ctx.send_error(error)
        else:
            await ctx.send_error("A fatal error occured. Tell <@109705860275539968> about this.")
            logger.error(traceback.format_exc())


def setup(bot):
    bot.add_cog(iOSCFW(bot))
