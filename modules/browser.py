from pyuseragents import random as random_ua
from aiohttp import ClientSession

from modules.utils import logger


class Browser:
    async def create_session(self):
        self.session = ClientSession()
        self.session.headers['user-agent'] = random_ua()


    async def get_airdrop_amount(self, address: str):
        url = f'https://www.zksyncpepe.com/resources/amounts/{address.lower()}.json'
        r = await self.session.get(url)

        try:
            r_json = await r.json()
            tokens_amount = r_json[0]
        except: tokens_amount = 0

        if tokens_amount > 0: logger.success(f'{address}: {tokens_amount} ZkPEPE AIRDROP')
        else: logger.info(f'{address}: {tokens_amount} ZkPEPE AIRDROP')
        return tokens_amount


    async def get_proofs(self, address: str):
        url = f'https://www.zksyncpepe.com/resources/proofs/{address.lower()}.json'
        r = await self.session.get(url)

        try: return await r.json()
        except: raise Exception(f'Couldnt get proofs: {await r.text()}\nReport it to @kAramelniy')

