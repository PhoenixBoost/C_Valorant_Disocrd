import discord
import requests
import os
import time
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from ratelimit import limits, sleep_and_retry
import logging
from My_Server import server_on

# ตั้งค่า logging
logging.basicConfig(level=logging.INFO)

# โหลดตัวแปรสภาพแวดล้อมจากไฟล์ .env
load_dotenv()

# กำหนดค่าตัวแปรจากการตั้งค่าในโค้ดโดยตรง
VALORANT_API_KEY = 'HDEV-e61177df-cdeb-4f6f-b0ee-994655183179'  # ใส่ค่า API Key ที่คุณต้องการ
REGION = 'ap'  # กำหนดค่า region ที่ต้องการ เช่น 'ap', 'na', 'eu' เป็นต้น

# สร้างอ็อบเจ็กต์บอท
intents = discord.Intents.default()
intents.message_content = True  # เปิดใช้งานการรับข้อความ
bot = commands.Bot(command_prefix='!', intents=intents)

# กำหนดอัตราการร้องขอ
ONE_MINUTE = 60
MAX_CALLS_PER_MINUTE = 30

# ฟังก์ชันสำหรับดึงข้อมูลสถิติของผู้เล่น
@sleep_and_retry
@limits(calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
def get_player_stats(region, name, tag):
    url = f"https://api.henrikdev.xyz/valorant/v1/account/{name}/{tag}"
    headers = {
        'Authorization': VALORANT_API_KEY
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for 4xx/5xx errors
    except requests.exceptions.HTTPError as errh:
        logging.error(f"HTTP Error: {errh}")
        return None
    except requests.exceptions.RequestException as err:
        logging.error(f"Request Error: {err}")
        return None
    
    if response.status_code == 429:
        retry_after = int(response.headers.get('Retry-After', 60))
        logging.info(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
        time.sleep(retry_after)
        return get_player_stats(region, name, tag)
    
    if response.status_code == 200:
        data = response.json().get('data')
        if data:
            return {
                'puuid': data.get('puuid'),
                'region': data.get('region'),
                'account_level': data.get('account_level'),
                'name': data.get('name'),
                'tag': data.get('tag'),
                'card': data.get('card'),
                'last_update': data.get('last_update'),
                'last_update_raw': data.get('last_update_raw')
            }
    else:
        logging.error(f"Error {response.status_code}: {response.text}")
    return None

# ฟังก์ชันสำหรับดึงข้อมูล MMR ของผู้เล่น
@sleep_and_retry
@limits(calls=MAX_CALLS_PER_MINUTE, period=ONE_MINUTE)
def get_player_mmr(region, name, tag):
    url = f"https://api.henrikdev.xyz/valorant/v2/mmr/{region}/{name}/{tag}"
    headers = {
        'Authorization': VALORANT_API_KEY
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.HTTPError as errh:
        logging.error(f"HTTP Error: {errh}")
        return None
    except requests.exceptions.RequestException as err:
        logging.error(f"Request Error: {err}")
        return None
    
    if response.status_code == 200:
        data = response.json().get('data')
        if data:
            return {
                'current_tier': data.get('current_data', {}).get('currenttierpatched'),
                'elo': data.get('current_data', {}).get('elo'),
                'highest_rank': data.get('highest_rank', {}).get('patched_tier'),
            }
    else:
        logging.error(f"Error {response.status_code}: {response.text}")
    return None

# คำสั่ง slash command สำหรับดึงสถิติของผู้เล่น
@bot.tree.command(name='valo', description='ดึงข้อมูลสถิติของผู้เล่น VALORANT')
async def valo(interaction: discord.Interaction, name: str, tag: str):
    # ตรวจสอบบทบาทของผู้ใช้ในคำสั่ง
    allowed_role_id = 1306502186783473707  # ID ของบทบาทที่อนุญาตให้ใช้คำสั่ง
    user_roles = [role.id for role in interaction.user.roles]  # ดึง ID ของบทบาทผู้ใช้
    
    # ตรวจสอบว่าผู้ใช้มีบทบาทที่อนุญาตให้ใช้คำสั่งหรือไม่
    if allowed_role_id not in user_roles:
        await interaction.response.send_message("คุณไม่มีสิทธิ์ใช้คำสั่งนี้. 🚫", ephemeral=True)
        return
    
    # ใช้ defer() เพื่อบอก Discord ว่าบอทกำลังประมวลผลคำสั่ง
    await interaction.response.defer(ephemeral=True)

    # เรียกใช้ฟังก์ชัน get_player_stats และ get_player_mmr โดยไม่บล็อกการทำงานของบอท
    stats = await bot.loop.run_in_executor(None, get_player_stats, REGION, name, tag)
    mmr = await bot.loop.run_in_executor(None, get_player_mmr, REGION, name, tag)

    if stats and mmr:
        embed = discord.Embed(
            title=f"🎮 {stats['name']}#{stats['tag']} 🏆",  # เพิ่มอิโมจิในชื่อ
            description=f"**Account Level:** {stats['account_level']} 💯\n**Region:** {stats['region']} 🌍\n**Last Update:** {stats['last_update']} ⏱️",
            color=discord.Color.blue()  # สามารถเปลี่ยนสีเป็นตามความชอบ
        )
        
        embed.set_thumbnail(url=stats['card']['small'])  # ใช้ Small Card เป็นไอคอน
        embed.set_footer(text="ข้อมูลจาก Valorant API 🔥")  # เพิ่มข้อความข้างล่าง Embed พร้อมอิโมจิ

        # เพิ่มฟิลด์สำหรับข้อมูลต่างๆ
        embed.add_field(name="PUUID 🔑", value=stats['puuid'], inline=False)
        embed.add_field(name="Current Tier 🥇", value=mmr['current_tier'], inline=True)
        embed.add_field(name="ELO 💎", value=mmr['elo'], inline=True)
        embed.add_field(name="Highest Rank 🔝", value=mmr['highest_rank'], inline=False)

        # เพิ่ม Icon และภาพให้สวยงาม
        embed.set_author(name=f"ข้อมูลสถิติของ {stats['name']}#{stats['tag']} 🎯", icon_url="https://upload.wikimedia.org/wikipedia/commons/e/e2/Valorant_Logo.svg")

        # เพิ่มภาพในส่วนของ Embed
        embed.set_image(url="https://upload.wikimedia.org/wikipedia/commons/e/e2/Valorant_Logo.svg")  # แทนที่ URL นี้ด้วยลิงค์ภาพของคุณ

        # สร้างปุ่มลิงค์เพื่อไปยัง Tracker.gg
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="เช็คข้อมูลเพิ่มติม 🔍", style=discord.ButtonStyle.link, url=f"https://vtl.lol/id/{stats['puuid']}"))

        # ส่ง embed ไปยังช่องแชทที่คำสั่งถูกใช้
        await interaction.followup.send(embed=embed, view=view)  # ส่งเป็น embed ที่สวยงามให้ทุกคนเห็น
    else:
        await interaction.followup.send(f"ไม่พบข้อมูลสำหรับ {name}#{tag}. โปรดลองใหม่ในภายหลัง. ❌")

# เหตุการณ์เมื่อบอทพร้อมใช้งาน
@bot.event
async def on_ready():
    print(f'เข้าสู่ระบบสำเร็จเป็น {bot.user}')
    print('------')
    # ซิงค์คำสั่งกับ Discord
    await bot.tree.sync()

# เริ่มต้นบอทด้วย token ที่กำหนด
server_on()
bot.run(os.getenv('TOKEN'))
