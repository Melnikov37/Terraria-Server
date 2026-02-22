import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    SESSION_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 3600
    MAX_CONTENT_LENGTH = 256 * 1024 * 1024  # 256 MB

    TERRARIA_DIR   = os.environ.get('TERRARIA_DIR', '/opt/terraria')
    REST_URL       = os.environ.get('REST_URL', 'http://127.0.0.1:7878')
    REST_TOKEN     = os.environ.get('REST_TOKEN', '')
    ADMIN_TOKEN    = os.environ.get('ADMIN_TOKEN', '')
    SERVER_TYPE    = os.environ.get('SERVER_TYPE', 'tshock')
    SCREEN_SESSION = os.environ.get('SCREEN_SESSION', 'terraria')
    MODS_DIR       = os.environ.get(
        'MODS_DIR',
        '/opt/terraria/.local/share/Terraria/tModLoader/Mods'
    )
    STEAMCMD_BIN   = os.environ.get('STEAMCMD_BIN', '/opt/steamcmd/steamcmd.sh')
    TERRARIA_APP_ID = '1281930'

    MOD_UPDATE_INTERVAL_HOURS  = int(os.environ.get('MOD_UPDATE_INTERVAL_HOURS', '0'))
    BACKUP_KEEP_COUNT          = int(os.environ.get('BACKUP_KEEP_COUNT', '24'))
    AUTO_BACKUP_INTERVAL_HOURS = int(os.environ.get('AUTO_BACKUP_INTERVAL_HOURS', '1'))

    @property
    def CONFIG_FILE(self):
        return os.path.join(self.TERRARIA_DIR, 'serverconfig.txt')

    @property
    def TSHOCK_CONFIG(self):
        return os.path.join(self.TERRARIA_DIR, 'tshock', 'config.json')

    @property
    def WORLDS_DIR(self):
        return os.path.join(self.TERRARIA_DIR, 'worlds')

    @property
    def BACKUPS_DIR(self):
        return os.path.join(self.TERRARIA_DIR, 'backups')

    @property
    def ADMINS_FILE(self):
        return os.path.join(self.TERRARIA_DIR, '.admins.json')

    @property
    def DISCORD_CONFIG_FILE(self):
        return os.path.join(self.TERRARIA_DIR, '.discord.json')

    SERVICE_NAME = 'terraria'
    ROLE_LEVELS  = {'viewer': 0, 'admin': 1, 'superadmin': 2}
    MAX_CONSOLE_LINES = 500

    KNOWN_WORKSHOP_IDS = {
        'CalamityMod':          '2824688072',
        'CalamityModMusic':     '2824688266',
        'ThoriumMod':           '2756794847',
        'BossChecklist':        '2756794864',
        'RecipeBrowser':        '2756794983',
        'MagicStorage':         '2563309347',
        'Census':               '2687356363',
        'AlchemistNPCLite':     '2382561813',
        'ImprovedTorches':      '2790887285',
        'HERO_Mod':             '2564599814',
        'WingSlot':             '2563309386',
        'CheatSheet':           '2563309402',
        'AutoTrash':            '2563372007',
        'Fargo_Mutant_Mod':     '2563309826',
        'FargowiltasSouls':     '2564815791',
        'StarlightRiver':       '2609329524',
        'Infernum':             '3142790752',
        'Terraria_Overhaul':    '1417245098',
        'MusicBox':             '2563309347',
        'HEROsMod':             '2564599814',
        'FancyLighting':        '2907538845',
        'SpiritMod':            '2563309339',
        'Redemption':           '2610690817',
        'GRealm':               '2563309387',
        'AssortedCrazyThings':  '2563309359',
        'Wikithis':             '2563309402',
        'AmuletOfManyMinions':  '2398614480',
    }
