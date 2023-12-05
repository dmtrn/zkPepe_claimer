from web3.eth import AsyncEth
from random import uniform, randint
from typing import Union, Optional
from time import sleep
from web3 import Web3
import asyncio

from modules.utils import logger, async_sleeping
import modules.config as config
import settings


class Wallet:
    def __init__(self, privatekey: str, recipient: str, tg_report, browser):
        self.chain = 'zksync'
        self.web3 = self.get_async_web3(chain_name=self.chain)

        self.privatekey = privatekey
        self.recipient = self.web3.to_checksum_address(recipient) if recipient else None
        self.account = self.web3.eth.account.from_key(privatekey)
        self.address = self.account.address
        self.tg_report = tg_report
        self.browser = browser

        self.airdrop_contract = self.web3.eth.contract(address=self.web3.to_checksum_address('0x95702a335e3349d197036Acb04BECA1b4997A91a'),
                                                       abi='[{"inputs":[{"internalType":"address","name":"","type":"address"}],"name":"claimRecord","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function","constant":true},{"inputs":[{"internalType":"bytes32[]","name":"","type":"bytes32[]"},{"internalType":"uint256","name":"","type":"uint256"}],"name":"claim","outputs":[],"stateMutability":"payable","type":"function"}]')
        self.zkpepe_address = self.web3.to_checksum_address('0x7D54a311D56957fa3c9a3e397CA9dC6061113ab3')

        self.max_retries = 5
        self.stats = {}


    def get_async_web3(self, chain_name: str):
        web3 = Web3(Web3.AsyncHTTPProvider(settings.RPCS[chain_name]), modules={'eth': (AsyncEth,)}, middlewares=[])
        return web3


    async def wait_for_gwei(self):
        first_check = True
        while True:
            new_gwei = round(await self.get_async_web3(chain_name='ethereum').eth.gas_price / 10 ** 9, 2)
            if new_gwei < settings.MAX_GWEI:
                if not first_check: logger.debug(f'[•] Web3 | New GWEI is {new_gwei}')
                break
            sleep(5)
            if first_check:
                first_check = False
                logger.debug(f'[•] Web3 | Waiting for GWEI at least {settings.MAX_GWEI}. Now it is {new_gwei}')


    async def get_gas(self, chain_name):
        if chain_name == 'linea': return {'gasPrice': await self.get_async_web3(chain_name=chain_name).eth.gas_price}
        max_priority = await self.get_async_web3(chain_name=chain_name).eth.max_priority_fee
        last_block = await self.get_async_web3(chain_name=chain_name).eth.get_block('latest')
        base_fee = last_block['baseFeePerGas']
        block_filled = last_block['gasUsed'] / last_block['gasLimit'] * 100
        if block_filled > 50: base_fee *= 1.125
        if settings.GWEI_MULTIPLIER > 1: base_fee *= settings.GWEI_MULTIPLIER
        max_fee = int(base_fee + max_priority)

        return {'maxPriorityFeePerGas': max_priority, 'maxFeePerGas': max_fee}


    async def approve(self, chain_name: str, spender: str, token_name: Optional[str] = False, token_address: Optional[str] = False, amount=None, value=None, retry=0):
        try:
            module_str = f'approve {token_name} to {spender}'

            web3 = self.get_async_web3(chain_name=chain_name)
            spender = web3.to_checksum_address(spender)
            if token_name: token_address = config.TOKEN_ADDRESSES[token_name]
            token_contract = web3.eth.contract(address=web3.to_checksum_address(token_address),
                                         abi='[{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]')
            if not token_name: token_name = await token_contract.functions.name().call()
            module_str = f'approve {token_name} to {spender}'

            decimals = await token_contract.functions.decimals().call()
            if amount:
                value = int(amount * 10 ** decimals)
                new_amount = round(amount * randint(10, 40), 5)
                new_value = int(new_amount * 10 ** decimals)
            else:
                new_value = int(value * randint(10, 40))
                new_amount = round(new_value / 10 ** decimals, 5)
            module_str = f'approve {new_amount} {token_name} to {spender}'

            allowance = await token_contract.functions.allowance(self.address, spender).call()
            if allowance < value:
                tx = token_contract.functions.approve(spender, new_value)
                tx_hash = await self.sent_tx(chain_name=chain_name, tx=tx, tx_label=module_str)
                return tx_hash
        except Exception as error:
            if retry < settings.RETRY:
                logger.error(f'{module_str} | {error}')
                logger.info(f'try again | {self.address}')
                await async_sleeping(10)
                return await self.approve(chain_name=chain_name, token_name=token_name, spender=spender, amount=amount, value=value, retry=retry+1)
            else:
                self.tg_report.update_logs(f'❌ {module_str}: {error}')
                raise ValueError(f'{module_str}: {error}')


    async def sent_tx(self, chain_name: str, tx, tx_label, tx_raw=False, value=0, retry=False):
        try:
            web3 = self.get_async_web3(chain_name=chain_name)
            if not tx_raw:
                if type(tx) != dict:
                    tx = await tx.build_transaction({
                        'from': self.address,
                        'chainId': await web3.eth.chain_id,
                        'nonce': await web3.eth.get_transaction_count(self.address),
                        'value': value,
                        **await self.get_gas(chain_name=chain_name),
                        'gas': 0
                    })
                    tx['gas'] = await web3.eth.estimate_gas(tx)
                if retry: tx['gas'] = int(tx['gas'] * 1.7)
            elif tx_raw and retry:
                tx['gas'] = int(tx['gas'] * 1.7)

            signed_tx = web3.eth.account.sign_transaction(tx, self.privatekey)
            raw_tx_hash = await web3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash = web3.to_hex(raw_tx_hash)
            tx_link = f'{config.CHAINS_DATA[chain_name]["explorer"]}{tx_hash}'
            logger.debug(f'[•] Web3 | {self.address}: {tx_label} tx sent: {tx_link}')

            await asyncio.sleep(2)
            while True:
                status = dict(await web3.eth.wait_for_transaction_receipt(tx_hash, timeout=int(settings.TO_WAIT_TX * 60)))['status']
                if status != None: break
                sleep(1)

            if status == 1:
                logger.info(f'[+] Web3 | {self.address}: {tx_label} tx confirmed\n')
                self.tg_report.update_logs(f'✅ {tx_label}')
                return tx_hash
            else:
                if not retry:
                    logger.debug(f'trying to resend transaction with higher gas (status {status})')
                    return await self.sent_tx(chain_name=chain_name, tx=tx, tx_label=tx_label, tx_raw=tx_raw, value=value, retry=True)
                else:
                    self.tg_report.update_logs(f'❌ {tx_label} <a href="{tx_link}">TX</a>')
                    raise ValueError(f'tx failed: {tx_link}')

        except Exception as err:
            if 'already known' in str(err):
                try: raw_tx_hash
                except: raw_tx_hash = ''
                logger.warning(f'{tx_label} | Couldnt get tx hash, thinking tx is success ({raw_tx_hash})')
                await async_sleeping(15)
                return True

            try: encoded_tx = f'\nencoded tx: {tx._encode_transaction_data()}'
            except: encoded_tx = ''
            raise ValueError(f'tx failed error: {err}{encoded_tx}')


    async def get_balance(self, chain_name: str, token_name=False, token_address=False, human=False):
        web3 = self.get_async_web3(chain_name=chain_name)
        if token_name: token_address = config.TOKEN_ADDRESSES[token_name]
        if token_address: contract = web3.eth.contract(address=web3.to_checksum_address(token_address),
                                     abi='[{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"}]')
        while True:
            try:
                if token_address: balance = await contract.functions.balanceOf(self.address).call()
                else: balance = await web3.eth.get_balance(self.address)

                decimals = await contract.functions.decimals().call() if token_address else 18
                if not human: return balance
                return balance / 10 ** decimals
            except Exception as err:
                logger.warning(f'[•] Web3 | Get balance error: {err}')
                sleep(5)


    async def wait_balance(self, chain_name: str, needed_balance: Union[int, float], only_more: bool = False, token_name: Optional[str] = False, token_address: Optional[str] = False):
        " needed_balance: human digit "
        if token_name:
            token_address = config.TOKEN_ADDRESSES[token_name]

        elif token_address:
            contract = self.get_async_web3(chain_name=chain_name).eth.contract(address=Web3().to_checksum_address(token_address),
                                         abi='[{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"}]')
            token_name = await contract.functions.name().call()

        else:
            token_name = 'ETH'

        if only_more: logger.debug(f'[•] Web3 | Waiting for balance more than {round(needed_balance, 6)} {token_name} in {chain_name.upper()}')
        else: logger.debug(f'[•] Web3 | Waiting for {round(needed_balance, 6)} {token_name} balance in {chain_name.upper()}')

        while True:
            try:
                new_balance = await self.get_balance(chain_name=chain_name, human=True, token_address=token_address)

                if only_more: status = new_balance > needed_balance
                else: status = new_balance >= needed_balance
                if status:
                    logger.debug(f'[•] Web3 | New balance: {round(new_balance, 6)} {token_name}\n')
                    return new_balance
                sleep(5)
            except Exception as err:
                logger.warning(f'[•] Web3 | Wait balance error: {err}')
                sleep(10)


    async def get_human_token_amount(self, chain_name: str, token_name: str, value: Union[int, float], human=True):
        if token_name != 'ETH':
            web3 = self.get_async_web3(chain_name=chain_name)
            token_contract = web3.eth.contract(address=web3.to_checksum_address(config.TOKEN_ADDRESSES[token_name]),
                                               abi='[{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"}]')

            decimals = await token_contract.functions.decimals().call()
        else: decimals = 18

        if human: return round(value / 10 ** decimals, 7)
        else: return int(value * 10 ** decimals)


    async def send_to_okx(self, chain: str, retry=0):

        try:
            await self.wait_for_gwei()

            web3 = self.get_async_web3(chain_name=chain)
            keep_values = settings.KEEP_VALUES

            if keep_values['all_balance']:
                balance = await self.get_balance(chain_name=chain, human=False)
                value = balance
            else:
                balance = await self.get_balance(chain_name=chain, human=True)
                amount = round(balance - uniform(keep_values['keep_from'], keep_values['keep_to']), 6)
                value = int(amount * 10 ** 18)

            value = int(value - 21000 * await web3.eth.gas_price * 1.1 // 10 ** 12 * 10 ** 12)  # round value
            amount = round(value / 10 ** 18, 5)

            module_str = f'sent {amount} ETH to {self.recipient}'

            tx = {
                'from': self.address,
                'to': self.recipient,
                'chainId': await web3.eth.chain_id,
                'nonce': await web3.eth.get_transaction_count(self.address),
                'value': value,
                'gas': 21000,
                **await self.get_gas(chain_name=chain),
            }

            await self.sent_tx(chain, tx, module_str, tx_raw=True)
            return amount

        except Exception as error:
            if retry < settings.RETRY:
                logger.error(f'{module_str} | {error}')
                await async_sleeping(10)
                return await self.send_to_okx(chain=chain, retry=retry + 1)
            else:
                self.tg_report.update_logs(f'❌ {module_str}: {error}')
                raise ValueError(f'{module_str}: {error}')


    async def is_airdrop_claimed(self):
        return await self.airdrop_contract.functions.claimRecord(self.address).call()


    async def claim_airdrop(self, proofs: list, amount: float):
        await self.wait_for_gwei()

        value = int(amount * 10 ** 18)
        module_str = f'claim {amount} ZkPepe'

        tx = self.airdrop_contract.functions.claim(proofs, value)

        tx_hash = await self.sent_tx(chain_name=self.chain, tx=tx, tx_label=module_str)
        return tx_hash






