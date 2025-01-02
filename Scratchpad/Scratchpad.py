#SSH VERSION /ssh hostname username command (Fails when a command like ping cant stop on its own)
#--SSH--#
import threading

@bot.slash_command(description="Execute SSH command", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")
async def ssh(
    interaction: nextcord.Interaction,
    hostname: str = SlashOption(name="hostname", description="Enter the hostname", required=True),
    username: str = SlashOption(name="username", description="Enter the username", required=True),
    command: str = SlashOption(name="command", description="Enter the command", required=True)
):
    await interaction.response.defer()

    # Sanitize inputs
    if ";" in command or "&" in command:
        await interaction.followup.send("Invalid characters in command!")
        return

    # Define a function to run the SSH command
    def ssh_thread(event: threading.Event):
        try:
            private_key_path = os.path.expanduser("~/.ssh/id_rsa")
            mykey = paramiko.RSAKey(filename=private_key_path)
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname, username=username, pkey=mykey)

            stdin, stdout, stderr = client.exec_command(command, timeout=30)
            output = stdout.read().decode()
            error = stderr.read().decode()

            client.close()

            # Set the event to signal that the command has finished
            event.set()

            return output, error

        except Exception as e:
            event.set()
            return None, str(e)

    # Use threading to run the SSH command
    event = threading.Event()
    thread = threading.Thread(target=ssh_thread, args=(event,))
    thread.start()

    # Wait for the thread to finish or for the timeout
    event.wait(timeout=30)

    # Get the results
    output, error = thread.join()

    if output:
        await interaction.followup.send(f"Output:\n```{output}```")
    if error:
        await interaction.followup.send(f"Error:\n```{error}```")


#---SSH host autcompletion---#
@ssh.on_autocomplete("hostname")
async def ssh_autocomplete(interaction: Interaction, hostname: str):
    if not hostname:
        # Send the full autocomplete list
        await interaction.response.send_autocomplete(list(hosts.keys()))
    else:
        matched_hosts = [host for host in hosts.keys() if host.lower().startswith(hostname.lower())]
        await interaction.response.send_autocomplete(matched_hosts)

#---OTHER WORKING SSH COMMANDS---#
# Assuming necessary imports and setup

active_ssh_sessions = {}  # Store active sessions

@bot.slash_command(description="Execute SSH command", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")
async def ssh(
    interaction: nextcord.Interaction,
    hostname: str = SlashOption(name="hostname", description="Enter the hostname", required=True),
    username: str = SlashOption(name="username", description="Enter the username", required=True),
    command: str = SlashOption(name="command", description="Enter the command", required=True)
):
    await interaction.response.defer()
    await execute_ssh_command(interaction, hostname, username, command)

async def execute_ssh_command(interaction, hostname, username, command):
    # Your previous SSH code here ...

    output_msg = "Output:\n```{output}```\nReply to this message with your next command." if output else "Command executed successfully, but there's no output. Reply to this message with your next command."
    sent_message = await interaction.followup.send(output_msg)
    try:
        reply = await bot.wait_for('message', timeout=300, check=lambda m: m.reference and m.reference.message_id == sent_message.id and m.author == interaction.user)
        await execute_ssh_command(interaction, hostname, username, reply.content)
    except asyncio.TimeoutError:
        await interaction.followup.send("SSH session ended due to inactivity.")

@bot.slash_command(description="Execute command in active SSH session", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")
async def ssh_command(
    interaction: nextcord.Interaction,
    command: str = SlashOption(name="command", description="Enter the command", required=True)
):
    await interaction.response.defer()

    # Check if session exists
    client = active_ssh_sessions.get(interaction.user.id)
    if not client:
        await interaction.followup.send("No active SSH session found. Start one with `/ssh_start`.")
        return

    # Execute command in the existing session
    try:
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode()
        error = stderr.read().decode()

        if output:
         await interaction.followup.send(f"Output:\n```{output}```")
        elif error:
          await interaction.followup.send(f"Error:\n```{error}```")
        else:
            await interaction.followup.send("Command executed successfully, but there's no output.")

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

@bot.slash_command(description="Terminate SSH session", guild_ids=[GUILD_ID])
@commands.has_role("McQueenLab.net Admin")
async def ssh_terminate(interaction: nextcord.Interaction):
    client = active_ssh_sessions.get(interaction.user.id)
    if client:
        client.close()
        del active_ssh_sessions[interaction.user.id]
        await interaction.response.send_message("SSH session terminated.")
    else:
        await interaction.response.send_message("No active SSH session found.")


###chat-GPT###
import openai
#
#---Ask GPT Command---#
@bot.slash_command(description="Ask GPT a question", guild_ids=[GUILD_ID])
async def ask_gpt(interaction: nextcord.Interaction, question: str = SlashOption(name="question", description="Question for GPT")):
    await interaction.response.defer()
    print(question)
    try:
        response = openai.Completion.create(
            engine="davinci",  # This is one of the main engines for GPT-3.5
            prompt=question,
            max_tokens=150  # Limit to 150 tokens for the response
        )
        await interaction.followup.send(response.choices[0].text.strip())
    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")

