import os
import configparser
import openai
import discord
import asyncio
import tiktoken
import json
import pathlib
import re
import traceback
from functools import wraps
from discord.ext import commands
from discord.ext.commands import Converter, BadArgument

#Read sensitive information
config = configparser.ConfigParser()
config_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
config.read(config_file_path)
openai.api_key = config.get("API_KEYS", "OPENAI_API_KEY")

# Set up OpenAI bot prompts. There are two different types of OpenAI API call: One to get a chat response for the user and one to autogenerate a progress summary to track the campaign over the long term. 
chatbot_name = {}
default_priming_prompt_base = "You are a veteran Dungeon Master. You speak with the flair of a bestselling fantasy author. You run your campaigns according to the Fifth Edition of the Dungeons and Dragons Players' Handbook, ensuring that turns and dice rolls are performed according to the rules. Here are the details of your campaign so far:"
default_summary_priming_prompt = "Your purpose is to summarise lists of Dungeons and Dragons chat inputs according to the following specific rules."

# Set token limits for DM bot (Leave ~1000 for the response and various miscalculations)
max_user_priming_prompt = 50
max_campaign_overview = 500
max_user_progress_summary = 200
max_user_chat_history = 2000
max_user_prompt = 500

# Set token limits for summary bot (Leave ~500 for the response and various miscalculations)
max_progress_summary = 2500
max_chat_history = 1000

# Set global variables
summary_priming_prompt = {}
priming_prompt_base = {}
DATA_FILE = f"data.json"
temperature = {}
campaign_overview = {}
progress_summary = {}
characters = {}
chat_history = {}
input_tokens = {}

help_message = '''
    Commands:
    !create_character [name], [race], [class], [background], [alignment], [notes] - Create a character.
    !update_character [attribute] [value] - Update your character's attribute (name, race, class, or background) with the specified value.
    !update_stats [STR] [str_value] [DEX] [dex_value] [CON] [con_value] [INT] [int_value] [WIS] [wis_value] [CHA] [cha_value] - Update your character's stats.
    !update_alignment [alignment] - Update your character's alignment.
    !update_level [level] - Update your character's level.
    !update_xp [xp] - Update your character's experience points.
    !update_ac [armor_class] - Update your character's Armor Class.
    !update_hp [hit_points] - Update your character's Hit Points.
    !update_inventory [item1], [item2], ... - Update your character's inventory.
    !update_spells [spell1], [spell2], ... - Update your character's spells.
    !update_notes [note1], [note2], ... - Update your character's notes.
    !display_character - Display your character's details.
    !update_campaign_overview [campaign_overview] - Update the campaign overview.
    !dm [message] - Chat with the bot, including your character's details.
    !update_priming_prompt [new_priming_prompt] - Update the priming prompt for the DM.
    !update_temperature [new_temperature] - Update the chatbot's response temperature. Provide a value between 0 and 1.
    !display_progress_summary - Shows the DM's automatically generated list of key events.
    
    Usage example:
    !create_character John Doe, Human, Wizard, Acolyte, chaotic evil, Hates cheese. Loves cats.
    !update_character class Cleric
    !update_stats STR 10 DEX 12 CON 14 INT 16 WIS 12 CHA 8
    !update_alignment Chaotic Good
    !update_level 5
    !update_xp 6500
    !update_ac 15
    !update_hp 20
    !update_inventory Dagger, Spellbook, Wand of Magic Missiles
    !update_spells Magic Missile, Mage Armor, Shield
    !update_notes Loves cats, Hates orcs, Is terrible at telling jokes
    !update_campaign_overview Campaign setting: Faerun. Rumors of a dark cult spreading. First location: City of Waterdeep. Party will be summoned by local authorities. Party will investigate the cult's activities and put a stop to their plans. Party will journey through a city, a forest, and a mountain. Party will combat fierce monsters, traps, and cunning enemies. Party will uncover clues that will lead to the cult's lair. Party will face the cult's leader, a powerful sorcerer named Zoltar, and his army of dark minions. Party must defeat Zoltar.
    !display_character
    !dm What should I do in the next dungeon?
    !update_priming_prompt You are DM, a Dungeons and Dragons dungeon master. You speak like a wise sage and your language is sprinkled with archaic old English. Your campaigns are in the style of a bestselling fantasy author. You adhere fastidiously to the Fifth Edition (5e) of the Dungeons and Dragons ruleset. You are running a Dungeons and Dragons campaign. Here are details to help you run the campaign:
    !update_temperature 0.6
        '''
# Set up the Discord bot
intents = discord.Intents.default()
intents.message_content = True
intents.typing = False
intents.presences = False
bot = commands.Bot(command_prefix="!", intents=intents, case_insensitive=True)

# Set up the tiktoken tokenizer for counting tokens
encoding = tiktoken.get_encoding("cl100k_base")

def num_tokens_from_string(string: str, encoding_name: str) -> int:

    # Returns the number of tokens in a text string.
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

def truncate_chat_history(chat_history_list, max_tokens):

    # Count the tokens in the chat history and truncate if necessary.
    truncated_chat_history = list(chat_history_list)
    chat_history_str = ' '.join(f"{entry['role']}: {entry['content']}" for entry in truncated_chat_history)
    chat_history_tokens = num_tokens_from_string(chat_history_str, "cl100k_base")
    while chat_history_tokens > max_tokens:
        truncated_chat_history.pop(0)
        chat_history_str = ' '.join(f"{entry['role']}: {entry['content']}" for entry in truncated_chat_history)
        chat_history_tokens = num_tokens_from_string(chat_history_str, "cl100k_base")
    return truncated_chat_history

def truncate_progress_summary(progress_summary_list, max_tokens):

    # Count the tokens in the progress_summary and truncate if necessary.
    truncated_progress_summary = list(progress_summary_list)
    progress_summary_str = ' '.join(progress_summary_list)
    progress_summary_tokens = num_tokens_from_string(progress_summary_str, "cl100k_base")
    while progress_summary_tokens > max_tokens:
        truncated_progress_summary.pop(0)
        progress_summary_str = ' '.join(truncated_progress_summary)
        progress_summary_tokens = num_tokens_from_string(progress_summary_str, "cl100k_base")
    return truncated_progress_summary

async def generate_progress_summary(chat_history_dict, progress_summary_dict, channel_id, is_progress_summary=False):

    #Provide a summary of any progress made by the party.
    truncated_chat_history = truncate_chat_history(chat_history_dict[channel_id], max_chat_history)
    truncated_progress_summary = truncate_progress_summary(progress_summary_dict[channel_id], max_progress_summary)
    truncated_chat_history_str = '\n'.join(f"{entry['content']}" for entry in truncated_chat_history)
    truncated_progress_summary_str = '\n'.join(truncated_progress_summary)
    progress_summary_prompt = (
        f"Have any key events occurred in this chat history that are NOT already noted in 'Campaign progress:'? "
        f"A key event may include: Meeting a new NPC, an important interaction with an NPC, combat, the final outcome of combat, "
        f"the party moving into new terrain, and the party making an important decision. "
        f"If yes, add those events to the progress summary by returning the new key events in the format "
        f"'Completed: [key event 1], [key event 2] ...' "
        f"Keep your summaries as concise as possible. "
        f"If no, return the text 'No new events.'"
    )
    progress_summary = await generate_response(progress_summary_prompt, channel_id, True)
    return progress_summary

#class StatConverter(Converter):
#    #Pretty sure this isn't used anymore.Delete if no errors.
#
#    async def convert(self, ctx, argument):
#        try:
#            value = int(argument)
#            if 1 <= value <= 20:
#                return value
#            else:
#                raise ValueError()
#        except ValueError:
#            raise BadArgument(f"Invalid stat value '{argument}', it must be an integer between 1 and 20.")

class Character:
    
    #The all-important character class. This is how all the information about characters is stored.
    def __init__(self, name, race, character_class, background, alignment, notes=None):
        self.name = name
        self.race = race
        self.character_class = character_class
        self.background = background
        self.alignment = alignment
        self.stats = {}
        self.armor_class = 10
        self.hit_points = 0
        self.inventory = []
        self.spells = []
        self.level = 1
        self.xp = 0
        self.notes = notes or "No notes yet."

    def display_character(self):
        stats_formatted = ', '.join(f"{key}: {value}" for key, value in self.stats.items())

        character_info = (
            f"Name: {self.name}\n"
            f"Race: {self.race}\n"
            f"Class: {self.character_class}\n"
            f"Background: {self.background}\n"
            f"Alignment: {self.alignment}\n\n" 
            f"Level: {self.level}\n"
            f"XP: {self.xp}\n\n"
            f"Armor Class: {self.armor_class}\n"
            f"Hit Points: {self.hit_points}\n\n"
            f"Stats: {stats_formatted}\n\n"
            f"Inventory: {', '.join(self.inventory)}\n\n"
            f"Spells: {', '.join(self.spells)}\n"
            f"Notes: {self.notes}\n"
        )
        return character_info

async def send_split_message(ctx, message):
    
    #Splits messages when they're too long for Discord.
    try:
        message_parts = [message[i:i + 2000] for i in range(0, len(message), 2000)]
        for part in message_parts:
            await ctx.send(part)
    except Exception as e:
        print(f"Error in send_split_message: {e}")
        traceback.print_exc()

async def generate_response(prompt, channel_id, is_progress_summary=False):
    
    #This and chat() are where most of the action happens. This is the function that calls the OpenAI API.
    try:
        global chatbot_name, priming_prompt_base, summary_priming_prompt, campaign_overview, progress_summary, characters, chat_history, input_tokens, temperature

        #All this [channel_id] stuff is so the chatbot can run different campaigns on different Discord channels.
        if channel_id not in chatbot_name:
            chatbot_name[channel_id] = "DM"
        if channel_id not in summary_priming_prompt:
            summary_priming_prompt[channel_id] = default_summary_priming_prompt
        if channel_id not in priming_prompt_base:
            priming_prompt_base[channel_id] = default_priming_prompt_base
        if channel_id not in campaign_overview:
            campaign_overview[channel_id] = "No campaign overview yet."
        if channel_id not in progress_summary:
            progress_summary[channel_id] = []
        if channel_id not in characters:
            characters[channel_id] = {}
        if channel_id not in chat_history:
            chat_history[channel_id] = []
        if channel_id not in input_tokens:
            input_tokens[channel_id] = 0
        if channel_id not in temperature:
            temperature[channel_id] = 0.8  
        loop = asyncio.get_event_loop()

        all_character_info = "No characters made yet." if not characters[channel_id] else "\n".join(
            f"{username}: {char.display_character()}"
            for _, (char, username) in characters[channel_id].items()
        )

        def call_openai_api():
            
            #Call the OpenAI API to get a response! Lots of conditional business here as the messages are different depending on whether it's calling for a response to the user or to produce a progress summary.
            current_max_progress_summary = max_progress_summary if is_progress_summary else max_user_progress_summary
            truncated_progress_summary = truncate_progress_summary(progress_summary[channel_id], current_max_progress_summary)

            current_max_chat_history = max_chat_history if is_progress_summary else max_user_chat_history
            truncated_chat_history = truncate_chat_history(chat_history[channel_id], current_max_chat_history)

            current_temperature = 0.5 if is_progress_summary else temperature[channel_id]

            truncated_chat_history_str = '\n'.join(f"{entry['content']}" for entry in truncated_chat_history)
            truncated_progress_summary_str = '\n'.join(truncated_progress_summary)
            if is_progress_summary:
                system_message = f"{summary_priming_prompt[channel_id]}\n\nParty details:\n{all_character_info}\n\nCampaign progress:\n\n{truncated_progress_summary}"
            else:
                system_message = f"{priming_prompt_base[channel_id]}\n\nParty details:\n{all_character_info}\n\nCampaign overview: Here is an outline of the campaign the players are undertaking. These events may not have occured yet and it is important you do not spoil the campaign by accidentally revealing the events to the players early. Reference the 'Campaign progress:' and 'Chat history:' sections to determine the events that have already occurred and the current state of play.\n\n{campaign_overview[channel_id]}\n\nCampaign progress: Here is the most recent progress the party has made in the campaign.\n\n{truncated_progress_summary}"
            messages = [
                {"role": "system", "content": system_message},
                {"role": "assistant", "content": "Chat history: Here is the most recent chat history to help you determine the state of play.\n\n"},
                *truncated_chat_history,
                {"role": "user", "content": prompt}
            ]
            
            messages_string = ' '.join(f"{entry['role']}: {entry['content']}" for entry in messages)
            input_tokens[channel_id] = num_tokens_from_string(messages_string, "cl100k_base")

            response_max_tokens = 4096 - input_tokens[channel_id] - 200  # -200 for safety.

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=response_max_tokens,
                n=1,
                stop=None,
                temperature=current_temperature,
            )
            print(f"Message sent to OpenAI: {messages}")
            print(f"Total input tokens: {input_tokens[channel_id]}")
            response = response['choices'][0]['message']['content'].strip()
            while response.startswith(f"{chatbot_name[channel_id]}: "):
                response = response[len(chatbot_name[channel_id]) + 2:]  # Remove the chatbot_name and the ": " (2 characters)
            return response

    except Exception as e:
        print(f"Error in generate_response: {e}")
        traceback.print_exc()
        return "I'm sorry, I encountered an error. Please try again."
    response_text = await asyncio.to_thread(call_openai_api)
    return response_text

#Stuff to save and load games.

async def periodic_save():
    while True:
        await asyncio.sleep(60 * 5)  # Save every 5 minutes
        for channel_id in campaign_overview.keys():
            save_data(channel_id)
        
def get_data_file(channel_id):
    current_path = pathlib.Path(__file__).parent
    save_data_directory = current_path / "save_data"
    save_data_directory.mkdir(parents=True, exist_ok=True)
    return save_data_directory / f"data_{channel_id}.json"

def save_data(channel_id):
    data_file = get_data_file(channel_id)
    data = {
        "campaign_overview": campaign_overview[channel_id],
        "progress_summary": progress_summary[channel_id],
        "characters": {
            user_id: {
                "username": username,
                "character": char.__dict__
            }
            for user_id, (char, username) in characters[channel_id].items()
        },
        "chat_history": chat_history[channel_id],
        "priming_prompt_base": priming_prompt_base[channel_id],
        "summary_priming_prompt": summary_priming_prompt[channel_id],
    }
    with open(data_file, "w") as f:
        json.dump(data, f)

def load_data(channel_id):
    global campaign_overview, progress_summary, characters, chat_history, priming_prompt_base, summary_priming_prompt
    data_file = get_data_file(channel_id)
    
    if not os.path.exists(data_file):
        if channel_id not in campaign_overview:
            campaign_overview[channel_id] = ""
            progress_summary[channel_id] = []
            characters[channel_id] = {}
            chat_history[channel_id] = []
            summary_priming_prompt[channel_id] = default_summary_priming_prompt
            priming_prompt_base[channel_id] = default_priming_prompt_base
        return
    else:
        with open(data_file, "r") as f:
            data = json.load(f)

        campaign_overview[channel_id] = data["campaign_overview"]
        progress_summary[channel_id] = data["progress_summary"]
        characters[channel_id] = {
            int(user_id): (
                Character(
                    data["characters"][user_id]["character"]["name"],
                    data["characters"][user_id]["character"]["race"],
                    data["characters"][user_id]["character"]["character_class"],
                    data["characters"][user_id]["character"]["background"],
                    data["characters"][user_id]["character"]["alignment"],
                ),
                data["characters"][user_id]["username"],
            )
            for user_id in data["characters"]
        }
        for user_id in characters[channel_id]:
            characters[channel_id][user_id][0].__dict__.update(data["characters"][str(user_id)]["character"])
        chat_history[channel_id] = data.get("chat_history", [])
    
    priming_prompt_base[channel_id] = data.get("priming_prompt_base", default_priming_prompt_base)
    summary_priming_prompt[channel_id] = data.get("summary_priming_prompt", default_summary_priming_prompt)
    if summary_priming_prompt[channel_id] == "":
        summary_priming_prompt[channel_id] = default_summary_priming_prompt
    if priming_prompt_base[channel_id] == "":
        priming_prompt_base[channel_id] = default_priming_prompt_base
        
def clear_save(channel_id):
    global campaign_overview, progress_summary, characters, chat_history

    # Reset the data structures for the specific channel
    campaign_overview[channel_id] = ""
    progress_summary[channel_id] = []
    characters[channel_id] = {}
    chat_history[channel_id] = {}
    summary_priming_prompt[channel_id] = default_summary_priming_prompt
    priming_prompt_base[channel_id] = default_priming_prompt_base

    # Save the updated data to the file
    save_data(channel_id)

#User commands, in no particular order.
        
@bot.command()
async def update_ac(ctx, armor_class: int):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters or user_id not in characters[channel_id]:
            await ctx.send("No character found. Please create a character first.")
            return
        
        character, _ = characters[channel_id][user_id]
        
        character.armor_class = armor_class
        await ctx.send(f"Armor Class updated for {ctx.author.name}:\n{character.display_character()}")
    except Exception as e:
        print(f"Error in update_ac: {e}")
        await ctx.send("An error occurred while updating your armor class. Please try again.")

@bot.command()
async def update_hp(ctx, hit_points: int):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters or user_id not in characters[channel_id]:
            await ctx.send("No character found. Please create a character first.")
            return

        character, _ = characters[channel_id][user_id]
        character.hit_points = hit_points
        await ctx.send(f"Hit Points updated for {ctx.author.name}:\n{character.display_character()}")
    except Exception as e:
        print(f"Error in update_hp: {e}")
        await ctx.send("An error occurred while updating your hit points. Please try again.")
    
@bot.command()
async def create_character(ctx, *, args):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        username = ctx.author.name
        split_args = [arg.strip() for arg in args.split(',')]  # Split input by commas

        if len(split_args) < 5:
            await ctx.send("Not enough arguments provided. Please follow the format: [name], [race], [class], [background], [alignment], [notes]")
            return

        name, race, character_class, background, alignment = split_args[:5]  # Unpack the first five elements of split_args

        # Assign an empty string to notes if it's not present
        notes = split_args[5] if len(split_args) > 5 else ""

        if channel_id not in characters:
            characters[channel_id] = {}

        characters[channel_id][user_id] = (Character(name, race, character_class, background, alignment, notes), username)
        await ctx.send(f"Character created for {ctx.author.name}:\n{characters[channel_id][user_id][0].display_character()}")
    except Exception as e:
        print(f"Error in create_character: {e}")
        await ctx.send("An error occurred while creating your character. Please try again.")

@bot.command()
async def update_character(ctx, attribute: str, *, value: str):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters or user_id not in characters[channel_id]:
            await ctx.send("No character found. Please create a character first.")
            return

        character, _ = characters[channel_id][user_id]

        attribute_mapping = {
            "name": "name",
            "race": "race",
            "class": "character_class",
            "background": "background"
        }

        attribute_key = attribute_mapping.get(attribute.lower())

        if attribute_key:
            setattr(character, attribute_key, value)
            await ctx.send(f"{attribute.capitalize()} updated for {ctx.author.name}:\n{character.display_character()}")
        else:
            await ctx.send("Invalid attribute. Please use name, race, class, or background.")
    except Exception as e:
        print(f"Error in update_character: {e}")
        await ctx.send("An error occurred while updating your character. Please try again.")

@bot.command()
async def update_stats(ctx, *, stats_str: str = None):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters:
            characters[channel_id] = {}

        if user_id not in characters[channel_id]:
            await ctx.send("You don't have a character yet. Create one using the `!create_character` command.")
            return

        character, _ = characters[channel_id][user_id]

        if stats_str is not None:
            # Split the stats string and create a dictionary of stat names and values
            stats_list = stats_str.split()
            stats_dict = {stats_list[i]: int(stats_list[i + 1]) for i in range(0, len(stats_list), 2)}

            for stat, value in stats_dict.items():
                character.stats[stat.lower()] = value

        await ctx.send(f"{ctx.author.name}, your character's stats have been updated:\n{character.display_character()}")
    except Exception as e:
        print(f"Error in update_stats: {e}")
        await ctx.send("An error occurred while updating your stats. Please try again.")

@bot.command()
async def update_level(ctx, level: int):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        character, _ = characters[channel_id].get(user_id)

        if character:
            character.level = level
            await ctx.send(f"Level updated for {ctx.author.name}:\nLevel {character.level}")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        print(f"Error in update_level: {e}")
        await ctx.send("An error occurred while updating your level. Please try again.")

@bot.command()
async def update_xp(ctx, xp: int):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        character, _ = characters[channel_id].get(user_id)

        if character:
            character.xp = xp
            await ctx.send(f"XP updated for {ctx.author.name}:\n{character.xp} XP")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        print(f"Error in update_xp: {e}")
        traceback.print_exc()
        await ctx.send("An error occurred while updating your XP. Please try again.")


@bot.command()
async def update_inventory(ctx, *, args):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters:
            characters[channel_id] = {}

        character, _ = characters[channel_id].get(user_id)

        if character:
            items = [item.strip() for item in args.split(',')]
            character.inventory = items
            await ctx.send(f"Inventory updated for {ctx.author.name}:\n{', '.join(character.inventory)}")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        print(f"Error in update_inventory: {e}")
        traceback.print_exc()
        await ctx.send("An error occurred while updating your inventory. Please try again.")

@bot.command()
async def update_spells(ctx, *, args):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters:
            characters[channel_id] = {}

        character, _ = characters[channel_id].get(user_id)

        if character:
            character.spells = [arg.strip() for arg in args.split(',')]
            await ctx.send(f"Spells updated for {ctx.author.name}:\n{', '.join(character.spells)}")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        print(f"Error in update_spells: {e}")
        traceback.print_exc()
        await ctx.send("An error occurred while updating your spells. Please try again.")

@bot.command()
async def update_notes(ctx, *, args):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters:
            characters[channel_id] = {}

        character, _ = characters[channel_id].get(user_id)

        if character:
            if len(args) <= 200:
                character.notes = args.strip()
                await ctx.send(f"Notes updated for {ctx.author.name}:\n{character.notes}")
            else:
                await ctx.send("Error: Notes must be no longer than 200 characters.")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"Error: {str(e)}")

@bot.command()
async def display_character(ctx):
    try:
        user_id = ctx.author.id
        channel_id = ctx.channel.id

        if channel_id not in characters:
            characters[channel_id] = {}

        character, _ = characters[channel_id].get(user_id)

        if character:
            await send_split_message(ctx, f"Character details for {ctx.author.name}:\n{character.display_character()}")
        else:
            await ctx.send("No character found. Please create a character first.")
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"Error: {str(e)}")

@bot.command()
async def update_campaign_overview(ctx, *, overview: str):
    try:
        global campaign_overview
        channel_id = ctx.channel.id

        # Check if the overview is under the max_campaign_overview limit
        overview_length = num_tokens_from_string(overview, "cl100k_base")
        if overview_length > max_campaign_overview:
            await ctx.send("Please try again with a shorter campaign overview.")
            return

        campaign_overview[channel_id] = overview
        await ctx.send(f"Campaign overview updated:\n{campaign_overview[channel_id]}")
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"Error: {str(e)}")

@bot.command(name="update_alignment")
async def update_alignment(ctx, *, alignment: str):
    global characters
    user_id = ctx.author.id
    channel_id = ctx.channel.id

    if channel_id in characters and user_id in characters[channel_id]:
        characters[channel_id][user_id].alignment = alignment
        await ctx.send(f"Character alignment updated to {alignment}.")
    else:
        await ctx.send("You don't have a character yet. Use !create_character to create one.")

@bot.command(name="display_progress_summary")
async def display_progress_summary(ctx):
    channel_id = ctx.channel.id
    
    # Load data for the channel if it hasn't been loaded yet
    if channel_id not in campaign_overview:
        load_data(channel_id)
        if channel_id not in campaign_overview:
            campaign_overview[channel_id] = ""
            progress_summary[channel_id] = []
            characters[channel_id] = {}
            chat_history[channel_id] = []
            priming_prompt_base[channel_id] = ""

    current_progress_summary = progress_summary.get(channel_id, [])
    if current_progress_summary:
        summary_text = "Progress Summary:\n\n" + "\n".join(current_progress_summary)
        await send_split_message(ctx, summary_text)
    else:
        await ctx.send("No progress summary found for this channel.")

#System commands

@bot.event
async def on_ready():
    print(f"{bot.user.name} is ready!")
    bot.loop.create_task(periodic_save())

@bot.command(name="update_chatbot_name")
async def update_chatbot_name_command(ctx, *args):
    new_name = " ".join(args)
    channel_id = ctx.channel.id
    chatbot_name[channel_id] = new_name
    await ctx.send(f"Chatbot name updated to: {new_name}")

@bot.command()
async def update_priming_prompt(ctx, *, new_prompt: str):
    try:
        channel_id = ctx.channel.id

        if channel_id not in chatbot_name:
            chatbot_name[channel_id] = "DM"

        formatted_prompt = new_prompt.format(chatbot_name=chatbot_name[channel_id])

        # Check if the new_prompt is under the max_user_prompt limit
        prompt_length = num_tokens_from_string(new_prompt, "cl100k_base")
        if prompt_length > max_user_prompt:
            await ctx.send("Please try again with a shorter priming prompt.")
            return

        priming_prompt_base[channel_id] = formatted_prompt
        await ctx.send(f"Priming prompt updated:\n{priming_prompt_base[channel_id]}")
    except Exception as e:
        print(f"Error in update_priming_prompt: {e}")
        await ctx.send("An error occurred while updating the priming prompt. Please try again.")


@bot.command()
async def display_priming_prompt(ctx):
    try:
        channel_id = ctx.channel.id

        if channel_id not in priming_prompt:
            priming_prompt_base[channel_id] = default_priming_prompt_base

        await ctx.send(f"Current priming prompt:\n{priming_prompt_base[channel_id]}")
    except Exception as e:
        print(f"Error in display_priming_prompt: {e}")
        await ctx.send("An error occurred while displaying the priming prompt. Please try again.")

@bot.command(name="update_temperature")
async def update_temperature(ctx, new_temperature: float):
    global temperature
    channel_id = ctx.channel.id
    if channel_id not in temperature:
        temperature[channel_id] = 0.8
    if 0 <= new_temperature <= 1:
        temperature[channel_id] = new_temperature
        await ctx.send(f"The chatbot temperature has been updated to {temperature[channel_id]:.2f}.")
    else:
        await ctx.send("Invalid temperature value. Please provide a value between 0 and 1.")

@bot.command()
async def clear_chat_history(ctx):
    try:
        global chat_history
        channel_id = ctx.channel.id
        if channel_id not in chat_history:
            chat_history[channel_id] = []
        chat_history[channel_id] = []
        await ctx.send("Chat history has been cleared.")
    except Exception as e:
        traceback.print_exc()
        print(f"Error in clear_chat_history: {e}")
        await ctx.send("An error occurred while clearing the chat history. Please try again.")

@bot.command(name="dm")
async def chat(ctx, *, message):
    global chatbot_name, chat_history
    channel_id = ctx.channel.id
    if channel_id not in chatbot_name:
        chatbot_name[channel_id] = "DM"

    # Load data for the channel if it hasn't been loaded yet
    if channel_id not in campaign_overview:
        load_data(channel_id)
        if channel_id not in campaign_overview:
            campaign_overview[channel_id] = ""
            progress_summary[channel_id] = []
            characters[channel_id] = {}
            chat_history[channel_id] = []
            summary_priming_prompt[channel_id] = default_summary_priming_prompt
            priming_prompt_base[channel_id] = default_priming_prompt_base

    # Add this check to ensure chat_history has a key for the channel_id
    if channel_id not in chat_history:
        chat_history[channel_id] = [{"role": "system", "content": "DM: Welcome to Dungeons and Dragons!"}]

    try:
        user_id = ctx.author.id
        username = ctx.author.name
        character = characters.get(user_id)

        # Check if the message is under 500 tokens
        message_length = num_tokens_from_string(message, "cl100k_base")
        if message_length > max_user_prompt:
            await ctx.send("Please try again with a shorter message.")
            return

        # Update chat history
        chat_history[channel_id].append({"role": "user", "content": f"{username}: {message}"})

        prompt = f"You are the Dungeon Master. Respond to this player: '{message}'"
        response = await generate_response(prompt, channel_id)
        # Update chat history with the model's response
        chat_history[channel_id].append({"role": "assistant", "content": f"{chatbot_name[channel_id]}: {response}"})
        await send_split_message(ctx, response)

        # Generate progress summary update
        progress_summary_update = await generate_progress_summary(chat_history, progress_summary, channel_id, is_progress_summary=True)
        # If the progress summary update contains "Completed:", update the progress_summary
        print(f"Progress summary update: {progress_summary_update}")
        if progress_summary_update.startswith("Completed:"):
            new_events = progress_summary_update[len("Completed:"):].strip().split(", ")
            progress_summary[channel_id].extend(new_events)
            save_data(channel_id)

    except Exception as e:
        print(f"Error in chat: {e}")
        traceback.print_exc()
        await ctx.send("An error occurred while processing your message. Please try again.")

@bot.command(name="clear_save")
async def clear_save_command(ctx):
    channel_id = ctx.channel.id
    clear_save(channel_id)
    await ctx.send("Saved data for this channel has been cleared.")

@bot.command(name="save_game")
async def save_game_command(ctx):
    channel_id = ctx.channel.id
    save_data(channel_id)
    await ctx.send("Game data saved successfully.")

# Remove the default help command
bot.remove_command('help')

# Custom help command
@bot.command()
async def help(ctx):
    try:
        await send_split_message(ctx, help_message)
    except Exception as e:
        traceback.print_exc()
        await ctx.send(f"Error: {str(e)}")


bot.run(config.get("API_KEYS", "DISCORD_TOKEN"))
