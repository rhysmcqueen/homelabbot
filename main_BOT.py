import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands,tasks
import subprocess
from dotenv import load_dotenv 
import os
import json
import paramiko
from wakeonlan import send_magic_packet
from nextcord import Embed , ButtonStyle
from nextcord.ui import View, Button

import asyncio
import discord_interactions
import requests
import time




PIHOLE_API_URL = "https://pihole-1.local.mcqueenlab.net/admin/api.php"
PIHOLE_API_KEY = os.getenv("PIHOLE_API_KEY")

# Variables
GUILD_ID = os.getenv("GUILD_ID")  # Replace with your guild ID
load_dotenv()

HOSTS_FILE = "/home/serveradmin/homelabbot/hosts.json"
ROLES_LIST = ["Hypervisor", "VM", "Ubuntu", "Truenas", "Storage","Router","Networking"]

intents = nextcord.Intents.default()
intents.message_content = True  # This is the new intent required for message content
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)


# Load hosts from the JSON file
def load_hosts_from_file():
    with open(HOSTS_FILE, "r") as file:
        return json.load(file)

# Save hosts to the JSON file
def save_hosts_to_file(hosts):
    with open(HOSTS_FILE, "w") as file:
        json.dump(hosts, file, indent=4)

class PaginationView(View):
    def __init__(self, pages):
        super().__init__()
        self.pages = pages
        self.current_page = 0
        self.add_item(Button(style=ButtonStyle.primary, label="<<", custom_id="previous"))
        self.add_item(Button(style=ButtonStyle.primary, label=">>", custom_id="next"))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

    async def on_click(self, interaction: nextcord.Interaction):
        if interaction.data["custom_id"] == "next":
            self.current_page = (self.current_page + 1) % len(self.pages)
        elif interaction.data["custom_id"] == "previous":
            self.current_page = (self.current_page - 1) % len(self.pages)
        
        embed = self.pages[self.current_page]
        await interaction.response.edit_message(embed=embed)

def send_web_request(url):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            return "Request sent successfully."
        else:
            return f"Failed to send request. Status code: {response.status_code}"
    except Exception as e:
        return f"An error occurred: {str(e)}"


class Counter(nextcord.ui.View):
    # Define the actual button
    # When pressed, this increments the number displayed until it hits 5.
    # When it hits 5, the counter button is disabled and it turns green.
    # note: The name of the function does not matter to the library
    @nextcord.ui.button(label="0", style=nextcord.ButtonStyle.red)
    async def count(self, button: nextcord.ui.Button, interaction: nextcord.Interaction):
        number = int(button.label) if button.label else 0
        if number >= 4:
            button.style = nextcord.ButtonStyle.green
            button.disabled = True
        button.label = str(number + 1)

        # Make sure to update the message with our updated selves
       
        await interaction.response.edit_message(view=self)

hosts = load_hosts_from_file()

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')



#---new_host Command---#
@bot.slash_command(description="Add a new host to the database", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")  # Check if the user has the "McQueenLab.net Admin" role
async def new_host(
    interaction: nextcord.Interaction,
    host_name: str = SlashOption(
        name="host_name",
        description="Enter the host name",
        required=True
    ),
    ip_address: str = SlashOption(
        name="ip_address",
        description="Enter the IP address",
        required=True
    ),
    mac_address: str = SlashOption(
        name="mac_address",
        description="Enter the MAC address",
        required=True
    ),
    roles: str = SlashOption(
        name="roles",
        description="Enter the roles",
        required=True,
        autocomplete=True
    )
):
    await interaction.response.defer()

    # Add the new host to the hosts dictionary
    roles_list = roles.split(", ")
    hosts[host_name] = {"ip": ip_address, "mac": mac_address, "role": roles_list}

    # Save the updated hosts to the JSON file
    save_hosts_to_file(hosts)

    # Send a confirmation message
    await interaction.followup.send(f"New host added:\nHost Name: {host_name}\nIP Address: {ip_address}\nMAC Address: {mac_address}\nRoles: {', '.join(roles_list)}")
@new_host.on_autocomplete("roles")
async def autocomplete_roles(interaction: Interaction, roles: str):
    if not roles:
        await interaction.response.send_autocomplete(ROLES_LIST)
    else:
        last_role = roles.split(", ")[-1]
        matched_roles = [role for role in ROLES_LIST if role.lower().startswith(last_role.lower())]
        await interaction.response.send_autocomplete(matched_roles)

#---Hello Command--#

@bot.slash_command(description="Hello!", guild_ids=[GUILD_ID])
async def hello(interaction: nextcord.Interaction):
    await interaction.send("Hello!")

#---Ping Command--#
async def async_ping(host):
    process = await asyncio.create_subprocess_exec(
        'ping', '-c', '4', host,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    return stdout.decode(), stderr.decode()


@bot.slash_command(description="Ping a host provided", guild_ids=[GUILD_ID])
async def ping(interaction: nextcord.Interaction, host: str = SlashOption(name="host", description="Select a host")):
    await interaction.response.defer()

    await interaction.followup.send("Pinging the host...")

    stdout, stderr = await async_ping(host)

    if stderr:
        print(stderr)

    await interaction.followup.send(stdout)
    
#---Ping Autocompltion--#
@ping.on_autocomplete("host")
async def ping_autocomplete(interaction: Interaction, host: str):
    if not host:
        # Send the full autocomplete list
        await interaction.response.send_autocomplete(list(hosts.keys()))
    else:
        matched_hosts = [hostname for hostname in hosts.keys() if hostname.lower().startswith(host.lower())]
        await interaction.response.send_autocomplete(matched_hosts)


#---WAKE ON LAN COMMAND---
@bot.slash_command(description="Send a Wake-on-LAN magic packet to wake up a device", guild_ids=[GUILD_ID])
async def wakeup(
    interaction: nextcord.Interaction,
    machine_name: str = SlashOption(
        name="machine_name",
        description="Enter the machine name",
        required=True
    )
):
    await interaction.response.defer()

    if machine_name in hosts:
        mac_address = hosts[machine_name]["mac"]
        try:
            send_magic_packet(mac_address)
            await interaction.followup.send(f"Wake-on-LAN magic packet sent to {machine_name} ({mac_address})")
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")
    else:
        await interaction.followup.send("Invalid machine name.")
#---Wake On Lan Autocompltion--#
@wakeup.on_autocomplete("machine_name")
async def wakeup_autocomplete(interaction: Interaction, machine_name: str):
    if not machine_name:
        await interaction.response.send_autocomplete(list(hosts.keys()))
    else:
        matched_hosts = [hostname for hostname in hosts.keys() if hostname.lower().startswith(machine_name.lower())]
        await interaction.response.send_autocomplete(matched_hosts)
#---show_host command---#
@bot.slash_command(description="Show the hosts database", guild_ids=[GUILD_ID])
async def show_host(interaction: nextcord.Interaction):
    hosts_embeds = []

    for host, data in hosts.items():
        embed = Embed(title=host, color=nextcord.Color.blue())
        embed.add_field(name="IP Address", value=f"[{data.get('ip', 'N/A')}]({'http://' + data.get('ip', '')})", inline=True)
        embed.add_field(name="Roles", value=', '.join(data.get('role', [])), inline=True)
        embed.add_field(name="FQDN", value=f"[{data.get('FQDN', 'N/A')}]({'http://' + data.get('FQDN', '')})", inline=True)
        hosts_embeds.append(embed)

    view = PaginationView(hosts_embeds)

    # Send the first embed as a message
    message = await interaction.response.send_message(embed=hosts_embeds[0], view=view)
    view.message = message

    # If you still want to send the host database formatted string as a follow-up
    # you can use the following code
    hosts_list = "\n".join([f"**Host Name:** {host}\n"
                            f"**IP Address:** [{data.get('ip', 'N/A')}]({'http://' + data.get('ip', '')})\n"
                            f"**Roles:** {', '.join(data.get('role', []))}\n"
                            f"**FQDN:** [{data.get('FQDN', 'N/A')}]({'http://' + data.get('FQDN', '')})\n"
                            for host, data in hosts.items()])

    await interaction.followup.send(f"Hosts Database:\n{hosts_list}")

#---Counter Command---#

@bot.slash_command(description="Counter", guild_ids=[GUILD_ID])
async def counter(interaction):
    """Starts a counter for pressing."""
    await interaction.send("Press!", view=Counter())


#---Timer--#
@bot.slash_command(description="Set a timer in minutes")
async def set_timer(interaction: nextcord.Interaction, minutes: int):
    try:
        if minutes <= 0:
            await interaction.response.send_message("Please enter a positive number of minutes!")
            return
        elif minutes > 60:  # Limit the timer to 60 minutes for this example
            await interaction.response.send_message("The maximum timer length is 60 minutes. Please set a shorter timer.")
            return
        
        await interaction.response.send_message(f"Timer set for {minutes} minutes!")
        await asyncio.sleep(minutes * 60)  # Sleep for the given number of minutes
        await interaction.followup.send(f"Hey {interaction.user.mention}, your {minutes} minute timer is up!")
    except Exception as e:
        await interaction.response.send_message(f"Error: {e}")





#---Settings--#
@bot.command()
async def setting(ctx, key, value):
    # Step 1: Permission check
    # Example: Only allow a user with a specific ID to change settings
    if ctx.message.author.id != 478640098691514389:
        await ctx.send("You don't have permission to modify settings.")
        return
    
    # Step 2: Modify the .env file
    # Caution: This overwrites the value for the given key in the .env file
    with open(".env", "r") as f:
        env_lines = f.readlines()

    with open(".env", "w") as f:
        for line in env_lines:
            if line.startswith(key + "="):
                f.write(f"{key}={value}\n")
            else:
                f.write(line)
    
    await ctx.send(f"Set {key} to {value} in .env file.")

#@bot.slash_command(description="Add a local DNS record to Pi-hole", guild_ids=[GUILD_ID])
#@commands.has_role("McQueenLab.net Admin")
#async def add_local_dns(
#    interaction: nextcord.Interaction,
#    record_type: str = SlashOption(name="record_type", description="Enter the record type (A or CNAME)", required=True, choices=["A", "CNAME"]),
#    domain: str = SlashOption(name="domain", description="Enter the domain", required=True),
#    value: str = SlashOption(name="value", description="Enter IP Address for ARecord or target domain for CNAME", required=True)
#):
#    await interaction.response.defer()
#    result = add_dns_record_to_pihole(record_type, domain, value)
#    await interaction.followup.send(result)


# def add_dns_record_to_pihole(record_type, domain, value):
#     # Formulate the necessary data for API request
#     data = {
#         "token": PIHOLE_API_KEY,
#         # Add other necessary fields based on Pi-hole's API documentation
#     }

#     # Depending on the record_type, adjust the data and endpoint.
#     # This is just a basic structure. Refer to the Pi-hole API documentation for exact fields and values.
#     if record_type == "A":
#         endpoint = "/add_a_record"
#         data["domain"] = domain
#         data["ip"] = value
#     elif record_type == "CNAME":
#         endpoint = "/add_cname_record"
#         data["domain"] = domain
#         data["target"] = value
#     print(PIHOLE_API_URL)
#     print(endpoint)
#     print(data)
#     response = requests.post(PIHOLE_API_URL + endpoint, data=data)

#     if response.status_code == 200:
#         return "Record added successfully."
#     else:
#         return f"Failed to add the record. Response: {response.text}"

@bot.slash_command(description="Send Power On or Power Off commands", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")
async def power_command(
    interaction: nextcord.Interaction,
    action: str = nextcord.SlashOption(
        name="action",
        description="Specify the action (Power On, Power Off or Reboot)",
        required=True,
        choices=["Power On", "Power Off", "Reboot"]
    )
):
    await interaction.response.defer()

    # Define the URLs for Power On and Power Off
    power_on_url = "http://192.168.1.245/cm?cmnd=Power%20On"
    power_off_url = "http://192.168.1.245/cm?cmnd=Power%20Off"

    # Check the chosen action and send the corresponding web request
    if action == "Power On":
        response = send_web_request(power_on_url)
    elif action == "Power Off":
        response = send_web_request(power_off_url)
    elif action =="Reboot":
        response = send_web_request(power_off_url)
        asyncio.sleep(10)
        send_web_request(power_on_url)

    else:
        response = "Invalid action specified."

    await interaction.followup.send(response)

@bot.event
async def on_slash_command_error(ctx, error):
    await ctx.send(f"An error occurred: {str(error)}")


#Start the BOT

bot.run(os.getenv("BOT_TOKEN"))