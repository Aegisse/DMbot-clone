# DungeonMasterGPT

This is a Discord bot that allows users to interact with a virtual Dungeon Master (DM) for Dungeons & Dragons (D&D) 5th Edition campaigns. The bot currently utilizes the OpenAI GPT-3.5-Turbo API for generating responses and managing the campaign.

## Installation and Dependencies
Install Python 3.6 or higher: https://www.python.org/downloads/

Install the following Python packages using pip:
```
pip install openai
pip install discord.py
pip install configparser
pip install asyncio
pip install tiktoken
```
## Basic Usage

Create a Discord bot and add it to your server.

Clone this repository and navigate to its directory.

Create a config.ini file in the root folder with the following content:
```
[API_KEYS]
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
DISCORD_TOKEN=YOUR_DISCORD_TOKEN
```
Replace YOUR_OPENAI_API_KEY with your actual OpenAI API key and YOUR_DISCORD_TOKEN with the token you created when setting up your Discord bot.

Run the DungeonMasterGPT.py script in the root folder:

```
python DungeonMasterGPT.py
```
The bot will now be online and available to use on your Discord server.

# Commands

Chat to the bot using
```
!dm [message]
```
### Character Management

DungeonMasterGPT supports the following commands:
```
!create_character [name], [race], [class], [background], [alignment], [notes]
!update_character [attribute] [value]
!update_stats [STR] [str_value] [DEX] [dex_value] [CON] [con_value] [INT] [int_value] [WIS] [wis_value] [CHA] [cha_value]
!update_alignment [alignment]
!update_level [level]
!update_xp [xp]
!update_ac [armor_class]
!update_hp [hit_points]
!update_inventory [item1], [item2], ...
!update_spells [spell1], [spell2], ...
!update_notes [note1], [note2], ...
!display_character

### Campaign Management

!update_campaign_overview [campaign_overview]
!display_progress_summary

### Bot management

!update_priming_prompt [new_priming_prompt]
!update_temperature [new_temperature]
```
## Notes

* Once you and your party have made characters, your details will be passed to the bot with every message, so it will remember who you are. It can sometimes require a couple of reminders that you are X character to begin with.
* Add a campaign_overview for the Dungeon Master bot to follow using !update_campaign_overview. You can ask it to make up one itself, or add your own. A bit of a spoiler I know, but a good overview makes for a good campaign so I haven't completely automated this step.
* A progress summary is automatically updated in the background to track the plot.
* Update your own character stats and roll your own dice as you go. I don't trust the bot's maths yet. It can however provide reliable details on which die to roll and any bonuses to add to your rolls.

Have fun! I can't wait to hear about your adventures. Please feel free to help refine this code and add features.
