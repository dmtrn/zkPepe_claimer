from warnings import filterwarnings
from random import shuffle
import asyncio
import os

from modules.utils import WindowName, TgReport, async_sleeping, logger, sleep
from modules import *
import settings



async def run_accs(acc_data: dict):
    async with sem:
        try:
            browser = Browser()
            await browser.create_session()

            tg_report = TgReport()
            acc_num = windowname.update_accs()
            wallet = Wallet(privatekey=acc_data['privatekey'], recipient=acc_data['recipient'], tg_report=tg_report, browser=browser)

            if not await wallet.is_airdrop_claimed():
                tokens = await browser.get_airdrop_amount(address=wallet.address)
                if tokens == 0:
                    wallet.stats['status'] = 'Zero Airdrop'
                    return True

                proofs = await browser.get_proofs(address=wallet.address)

                await wallet.claim_airdrop(proofs=proofs, amount=tokens)
                wallet.stats['status'] = 'Claimed'
            else:
                wallet.stats['status'] = 'Claimed Before'

            pepe_balance = await wallet.get_balance(chain_name=wallet.chain, token_address=wallet.zkpepe_address, human=True)
            if pepe_balance == 0:
                logger.info(f'{wallet.address}: ZkPepe Already sold')
                wallet.stats['status'] = 'Already sold ZkPepe'
                return True

            if not settings.SELL_TOKENS:
                tg_report.update_logs(text=f'✅ Balance {pepe_balance} ZkPepe')
                if pepe_balance > 0:
                    wallet.stats['status'] = f'{pepe_balance} ZkPepe'
                return True

            await async_sleeping(5, 20)  # задержка после клейма и перед продажей ZkPepe
            eth_got = await Syncswap(wallet=wallet).swap()
            wallet.stats['status'] = f'Sold ZkPepe Drop for {eth_got} ETH'

            if settings.SEND_TO_OKX:
                await async_sleeping(5, 20)  # задержка после продажи ZkPepe и перед отправкой на OKX
                amount_withdrew = await wallet.send_to_okx(chain=wallet.chain)
                wallet.stats['status'] = f'Withdrew {amount_withdrew} ETH'

            return True

        except Exception as err:
            wallet.stats['status'] = '❌ ' + str(err)
            logger.error(f'[-] Account #{acc_num} error: {err}')

        finally:
            excel.edit_table(wallet=wallet)
            await browser.session.close()
            await tg_report.send_log(wallet=wallet, window_name=windowname, acc_num=acc_num)
            await async_sleeping(5, 20) # задержка между аккаунтами


async def runner(accs_data: list):
    results = await asyncio.gather(*[run_accs(acc_data=acc_data) for acc_data in accs_data])
    print('')
    logger.success(f'Successfully did [{results.count(True)}/{len(accs_data)}]')


if __name__ == '__main__':
    filterwarnings("ignore")

    if not os.path.isdir('results'): os.mkdir('results')
    with open('privatekeys.txt') as f: p_keys = f.read().splitlines()
    with open('recipients.txt') as f: recipients = f.read().splitlines()

    if settings.SEND_TO_OKX:
        if len(p_keys) != len(recipients): raise Exception(f'Private keys amount must be equals recipients amount ({len(p_keys)} ≠ {len(recipients)})')
        accs_data = [{'privatekey': pk, 'recipient': address} for pk, address in list(zip(p_keys, recipients))]
    else:
        accs_data = [{'privatekey': pk, 'recipient': None} for pk in p_keys]

    while True:
        try:
            threads = int(input('\nEnter threads count: '))
            sem = asyncio.Semaphore(threads)
            break
        except Exception as err:
            pass

    windowname = WindowName(len(p_keys), threads)
    if settings.SHUFFLE_WALLETS: shuffle(accs_data)
    excel = Excel(len(p_keys))

    try:
        asyncio.run(runner(accs_data))

    except Exception as err:
        logger.error(f'Global error: {err}')

    logger.success(f'All accs done.\n\n')
    sleep(0.1)
    input(' > Exit')
