from inspect import getsourcefile
from aiohttp import ClientSession
from random import randint
from loguru import logger
from time import sleep
from tqdm import tqdm
import asyncio
import sys
import ctypes
import os

import settings


logger.remove()
logger.add(sys.stderr, format="<white>{time:HH:mm:ss}</white> | <level>{message}</level>")
windll = ctypes.windll if os.name == 'nt' else None # for Mac users


class WindowName:
    def __init__(self, accs_amount: int, threads: int):
        try: self.path = os.path.abspath(getsourcefile(lambda: 0)).split("\\")[-2]
        except: self.path = os.path.abspath(getsourcefile(lambda: 0)).split("/")[-2]

        self.accs_amount = accs_amount
        self.threads = threads
        self.accs_done = 0
        self.modules_amount = 0
        self.modules_done = 0

        self.update_name()

    def update_name(self):
        if os.name == 'nt':
            windll.kernel32.SetConsoleTitleW(f'ZkPepe Claim [{self.accs_done}/{self.accs_amount}] | {self.path} | {self.threads} THREADS')

    def update_accs(self):
        self.accs_done += 1
        self.modules_amount = 0
        self.modules_done = 0
        self.update_name()
        return self.accs_done



class TgReport:
    def __init__(self):
        self.logs = ''


    def update_logs(self, text: str):
        self.logs += f'{text}\n'


    async def send_log(self, wallet, window_name, acc_num):
        notification_text = f'[{acc_num}/{window_name.accs_amount}] <i>{wallet.address}</i>\n\n' \
                            f'{self.logs}\n'
        url = f'https://api.telegram.org/bot{settings.TG_BOT_TOKEN}/sendMessage'

        if settings.TG_BOT_TOKEN:
            for tg_id in settings.TG_USER_ID:
                params = {
                    'parse_mode': 'HTML',
                    'chat_id': tg_id,
                    'text': notification_text,
                }
                async with ClientSession() as session:
                    try: await session.post(url, params=params)
                    except Exception as err: logger.error(f'[-] TG | Send Telegram message error to {tg_id}: {err}')


def sleeping(*timing):
    if type(timing[0]) == list: timing = timing[0]
    if len(timing) == 2: x = randint(timing[0], timing[1])
    else: x = timing[0]
    for _ in tqdm(range(x), desc='sleep ', bar_format='{desc}: {n_fmt}/{total_fmt}'):
        sleep(1)


async def async_sleeping(*timing):
    if type(timing[0]) == list: timing = timing[0]
    if len(timing) == 2: x = randint(timing[0], timing[1])
    else: x = timing[0]
    if x == 0: return True
    for _ in tqdm(range(x), desc='sleep ', bar_format='{desc}: {n_fmt}/{total_fmt}'):
        await asyncio.sleep(1)
