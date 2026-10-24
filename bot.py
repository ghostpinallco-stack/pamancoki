import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import io
import datetime

# ================= KONFIGURASI =================
# Token diambil dari Environment Variables di Railway
TOKEN = os.getenv("DISCORD_TOKEN") 
# ===============================================

class RobloxStoreBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), help_command=None)
        # Path disesuaikan buat Railway Volume biar data ga ilang pas restart
        self.db_file = "/app/data/accounts.json"
        self.config_file = "/app/data/config.json"

    async def setup_hook(self):
        # Bikin folder data otomatis kalau belum ada
        os.makedirs("/app/data", exist_ok=True)

        # Bikin file database kalau belum ada
        if not os.path.exists(self.db_file):
            with open(self.db_file, "w") as f:
                json.dump([], f)
                
        # Bikin file config kalau belum ada
        if not os.path.exists(self.config_file):
            with open(self.config_file, "w") as f:
                json.dump({
                    "allowed_role_id": None, 
                    "panel_channel_id": None, 
                    "role_locked": False,
                    "gif_available": "https://media.tenor.com/On7KVXhzml4AAAAj/loading-gif.gif", 
                    "gif_empty": "https://media.tenor.com/On7KVXhzml4AAAAj/loading-gif.gif", 
                    "buy_link": "https://discord.com" 
                }, f, indent=4)

        # Sync slash commands ke Discord
        await self.tree.sync()
        print("✅ Slash commands disync!")

    async def on_ready(self):
        print(f"✅ Login sebagai {self.user.name} ({self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Roblox Store | /stock"))
        self.update_panel_loop.start()

    @tasks.loop(seconds=30)
    async def update_panel_loop(self):
        await self.update_panel()

    async def update_panel(self):
        """Update embed panel stok di channel yang ditentukan"""
        with open(self.config_file, "r") as f:
            config = json.load(f)
            
        channel_id = config.get("panel_channel_id")
        if not channel_id:
            return

        channel = self.get_channel(int(channel_id))
        if not channel:
            return

        # Hitung stok
        with open(self.db_file, "r") as f:
            accounts = json.load(f)
            stock = len([a for a in accounts if a["status"] == "available"])

        # Ambil URL GIF & Link Beli dari config
        gif_url = config.get("gif_available") if stock > 0 else config.get("gif_empty")
        buy_link = config.get("buy_link", "https://discord.com")
        
        # Desain Panel (Mirip contoh Zzz Solve)
        embed = discord.Embed(
            title="🛒 **ROBLOX STORE — STOCK PANEL**",
            description="*Cek ketersediaan akun secara realtime di bawah ini!*",
            color=0x5865F2 
        )
        
        if gif_url:
            embed.set_image(url=gif_url)
            
        embed.add_field(
            name="📦 **Stok Tersedia**", 
            value=f"```fix\n{stock} Akun\n```", 
            inline=True
        )
        embed.add_field(
            name="🔒 **Status**", 
            value=f"```fix\n{'✅ TERSEDIA' if stock > 0 else '❌ HABIS'}\n```", 
            inline=True
        )
        
        embed.set_footer(text="Powered by Roblox Store", icon_url=self.user.display_avatar.url)
        embed.timestamp = datetime.datetime.now()

        # Bikin Tombol
        view = discord.ui.View()
        btn = discord.ui.Button(
            label="Beli Akun / Hubungi Admin", 
            emoji="🛒", 
            style=discord.ButtonStyle.link, 
            url=buy_link 
        )
        view.add_item(btn)

        # Cari & Edit Panel Lama biar ga spam chat
        async for msg in channel.history(limit=20):
            if msg.author.id == self.user.id and msg.embeds and "STOCK PANEL" in msg.embeds[0].title:
                await msg.edit(embed=embed, view=view)
                return
        await channel.send(embed=embed, view=view)

bot = RobloxStoreBot()

# ================= HELPER CEK ROLE =================
def is_allowed(member: discord.Member):
    with open(bot.config_file, "r") as f:
        config = json.load(f)
    allowed_role_id = config.get("allowed_role_id")
    if not allowed_role_id:
        return False
    return discord.utils.get(member.roles, id=int(allowed_role_id)) is not None

# ================= COMMANDS =================

@bot.tree.command(name="setup", description="Set role penjual (HANYA BISA DILAKUKAN SEKALI)")
@app_commands.describe(role="Role yang diizinkan mengakses command penjual")
async def setup_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("🚫 Hanya Administrator server yang bisa melakukan setup awal.", ephemeral=True)

    with open(bot.config_file, "r") as f:
        config = json.load(f)

    if config["role_locked"]:
        return await interaction.response.send_message("🔒 Role sudah di-set sebelumnya dan **tidak bisa diubah lagi**.", ephemeral=True)

    config["allowed_role_id"] = role.id
    config["role_locked"] = True
    
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    embed = discord.Embed(
        title="✅ Setup Berhasil",
        description=f"Role penjual dikunci ke: {role.mention}\n\n⚠️ **Role terkunci permanen.**",
        color=0x2ecc71
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="setchannel", description="Set channel untuk info stok panel")
async def set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)
        
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    config["panel_channel_id"] = channel.id
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message(f"✅ Panel stok di-set ke {channel.mention}.", ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="setpanel", description="Set GIF animasi dan link tombol untuk panel")
@app_commands.describe(gif_tersedia="Link .gif stok ada", gif_habis="Link .gif stok habis", link_beli="Link WA/Web pas tombol diklik")
async def set_panel(interaction: discord.Interaction, gif_tersedia: str, gif_habis: str, link_beli: str):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)
        
    with open(bot.config_file, "r") as f:
        config = json.load(f)
        
    config["gif_available"] = gif_tersedia
    config["gif_empty"] = gif_habis
    config["buy_link"] = link_beli
    
    with open(bot.config_file, "w") as f:
        json.dump(config, f, indent=4)

    await interaction.response.send_message("✅ Pengaturan GIF & Link Tombol berhasil disimpan! Panel telah diupdate.", ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="inputakun", description="Tambah akun Roblox (format: user:pass:cookie)")
@app_commands.describe(akun="Format: username:password:cookies")
async def input_akun(interaction: discord.Interaction, akun: str):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)

    lines = akun.strip().split("\n")
    sukses = 0
    gagal = 0

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    for line in lines:
        parts = line.strip().split(":")
        if len(parts) < 3:
            gagal += 1
            continue

        username = parts[0].strip()
        password = parts[1].strip()
        cookies = ":".join(parts[2:]).strip()

        accounts.append({
            "id": len(accounts) + 1,
            "username": username,
            "password": password,
            "cookies": cookies,
            "status": "available",
            "buyer": None,
            "reason": None,
            "gifted_at": None
        })
        sukses += 1

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    stock = len([a for a in accounts if a["status"] == "available"])
    
    embed = discord.Embed(title="📥 Input Akun Selesai", color=0x2ecc71)
    embed.add_field(name="✅ Berhasil", value=f"{sukses}", inline=True)
    embed.add_field(name="❌ Gagal", value=f"{gagal}", inline=True)
    embed.add_field(name="📦 Total Stok", value=f"{stock} akun", inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="giftakun", description="Kirim akun ke pembeli via DM setelah TF")
@app_commands.describe(user="Pembeli", jumlah="Jumlah akun", reason="Order ID / Alasan")
async def gift_akun(interaction: discord.Interaction, user: discord.User, jumlah: int, reason: str):
    if not is_allowed(interaction.user):
        return await interaction.response.send_message("🚫 Kamu tidak punya role penjual yang sah.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    with open(bot.db_file, "r") as f:
        accounts = json.load(f)

    available_accs = [a for a in accounts if a["status"] == "available"]
    
    if len(available_accs) < jumlah:
        return await interaction.followup.send(f"❌ Stok tidak cukup. Tersedia: **{len(available_accs)}**, diminta: **{jumlah}**", ephemeral=True)

    to_gift = available_accs[:jumlah]
    
    file_content = f"=== ROBLOX ACCOUNT DELIVERY ===\nBuyer  : {user.name} ({user.id})\nReason : {reason}\nJumlah : {jumlah}\nTanggal: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    for i, acc in enumerate(to_gift):
        file_content += f"#{i+1}\nUsername : {acc['username']}\nPassword : {acc['password']}\nCookies  : {acc['cookies']}\n\n"
    file_content += "=== JANGAN BAGIKAN DATA INI ===\n"
    
    file_buffer = io.BytesIO(file_content.encode('utf-8'))
    file_discord = discord.File(fp=file_buffer, filename=f"roblox_accounts_{int(datetime.datetime.now().timestamp())}.txt")

    dm_embed = discord.Embed(
        title="🎁 Pesanan Akun Roblox Kamu",
        description=f"Terima kasih sudah membeli!\n\n📦 **Jumlah**: {jumlah} akun\n🧾 **Reason**: {reason}\n\nFile akun terlampir di bawah. **Segera ganti password & jangan bagikan data ini ke siapa pun.**",
        color=0x2ecc71
    )
    
    try:
        await user.send(embed=dm_embed, file=file_discord)
    except discord.Forbidden:
        return await interaction.followup.send(f"❌ Gagal kirim DM ke {user.mention}. Kemungkinan DM tertutup. Akun **tidak di-gift** (stok utuh).", ephemeral=True)

    for acc in accounts:
        if acc["id"] in [a["id"] for a in to_gift]:
            acc["status"] = "gifted"
            acc["buyer"] = str(user.id)
            acc["reason"] = reason
            acc["gifted_at"] = str(datetime.datetime.now())

    with open(bot.db_file, "w") as f:
        json.dump(accounts, f, indent=4)

    sisa_stok = len([a for a in accounts if a["status"] == "available"])
    res_embed = discord.Embed(title="✅ Gift Berhasil", color=0x2ecc71)
    res_embed.add_field(name="Penerima", value=user.mention, inline=True)
    res_embed.add_field(name="Jumlah", value=str(jumlah), inline=True)
    res_embed.add_field(name="Sisa Stok", value=str(sisa_stok), inline=True)
    
    await interaction.followup.send(embed=res_embed, ephemeral=True)
    await bot.update_panel()

@bot.tree.command(name="stock", description="Cek stok akun (Bisa diakses publik)")
async def cek_stock(interaction: discord.Interaction):
    with open(bot.db_file, "r") as f:
        accounts = json.load(f)
    stok = len([a for a in accounts if a["status"] == "available"])
    await interaction.response.send_message(f"📦 Stok saat ini: **{stok}** akun. Silakan cek channel panel untuk info detail.", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ERROR: DISCORD_TOKEN tidak ditemukan! Set di Environment Variables.")
    else:
        bot.run(TOKEN)