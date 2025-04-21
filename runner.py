import requests
import asyncio
import aiohttp
from typing import Optional, Tuple, List, Dict
import sys
from colorama import init, Fore, Style
import os
import random
import json
from datetime import datetime
import threading
import time

# Initialize colorama
init(autoreset=True)

# Constants
PING_INTERVAL = 60  # seconds between pings
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds between retries

# API endpoints
LOGIN_URL = 'https://api.solixdepin.net/api/auth/login-password'
PING_URL = 'https://api.solixdepin.net/api/point/get-connection-quality'
POINTS_URL = 'https://api.solixdepin.net/api/point/get-total-point'

# HTTP headers template
headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9,id;q=0.8',
    'content-type': 'application/json',
    'origin': 'https://dashboard.solixdepin.net',
    'referer': 'https://dashboard.solixdepin.net/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'priority': 'u=1, i'
}

# Shared state for account statuses
type StatusDict = Dict[str, Dict]
account_status: StatusDict = {}
status_lock = threading.Lock()

# Proxy list and lock
proxies: List[str] = []
proxy_lock = threading.Lock()

# Rate limiting control
last_request_time: Dict[str, float] = {}
rate_limit_lock = threading.Lock()
MIN_REQUEST_INTERVAL = 1.0  # Minimum seconds between requests per account

# --------------------------------------------------
# Utility functions
# --------------------------------------------------

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def load_proxies(filename: str = 'proxy.txt') -> None:
    global proxies
    try:
        with open(filename, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        print(f"{Fore.GREEN}✅ Loaded {len(proxies)} proxies{Style.RESET_ALL}")
    except FileNotFoundError:
        print(f"{Fore.RED}❌ Error: proxy.txt not found{Style.RESET_ALL}")


def get_random_proxy() -> Optional[str]:
    with proxy_lock:
        return random.choice(proxies) if proxies else None


# Read credentials: 'email:password' per line

def read_credentials(filename: str = 'akun.txt') -> List[Tuple[str, str]]:
    accounts = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                if ':' in line:
                    email, pwd = line.strip().split(':', 1)
                    accounts.append((email, pwd))
        if not accounts:
            print(f"{Fore.RED}❌ Error: No accounts in {filename}{Style.RESET_ALL}")
    except FileNotFoundError:
        print(f"{Fore.RED}❌ Error: {filename} not found{Style.RESET_ALL}")
    return accounts


async def get_token_async(session: aiohttp.ClientSession, email: str, password: str) -> Optional[str]:
    data = {'email': email, 'password': password}
    proxy = get_random_proxy()
    proxy_kw = {'proxy': proxy} if proxy else {}
    
    try:
        async with session.post(LOGIN_URL, headers=headers, json=data, **proxy_kw) as resp:
            if resp.status in (200, 201):
                js = await resp.json()
                if js.get('result') == 'success':
                    return js['data']['accessToken']
            print(f"{Fore.RED}❌ Login failed for {email} (status {resp.status}){Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ Login error for {email}: {e}{Style.RESET_ALL}")
    return None


async def update_status(email: str, connection_quality: int, internet_points: float, total_points: float, error: str = None) -> None:
    with status_lock:
        # Only update points if they are not '--'
        current_status = account_status[email]
        if connection_quality != '--':
            current_status['connection_quality'] = connection_quality
        if internet_points != '--':
            current_status['internet_points'] = internet_points
        if total_points != '--':
            current_status['total_points'] = total_points
        
        current_status.update({
            'next_ping': PING_INTERVAL,
            'error': error
        })


def start_countdown_task():
    async def countdown():
        while True:
            with status_lock:
                for status in account_status.values():
                    if isinstance(status.get('next_ping'), int) and status['next_ping'] > 0:
                        status['next_ping'] -= 1
            await asyncio.sleep(1)
    return asyncio.create_task(countdown())


def format_points(points: float) -> str:
    if points == '--':
        return '--'
    return f"{points:.2f}"

def get_quality_emoji(quality: int) -> str:
    if quality == '--':
        return '❓'
    if quality >= 90:
        return '🔥'
    elif quality >= 70:
        return '⚡'
    elif quality >= 50:
        return '✅'
    elif quality >= 30:
        return '⚠️'
    else:
        return '❌'

def get_quality_color(quality: int) -> str:
    if quality == '--':
        return Fore.WHITE
    if quality >= 90:
        return Fore.RED
    elif quality >= 70:
        return Fore.YELLOW
    elif quality >= 50:
        return Fore.GREEN
    elif quality >= 30:
        return Fore.CYAN
    else:
        return Fore.MAGENTA

def mask_email(email: str) -> str:
    if '@' not in email:
        return email
    name, domain = email.split('@')
    domain_name, tld = domain.split('.')
    
    # Mask name (keep first 4 chars and last 4 chars)
    if len(name) > 8:
        masked_name = name[:4] + '*' * (len(name) - 8) + name[-4:]
    else:
        masked_name = name[:2] + '*' * (len(name) - 2)
    
    # Mask domain (keep first char and last char)
    masked_domain = domain_name[0] + '*' * (len(domain_name) - 1)
    
    return f"{masked_name}@{masked_domain}.{tld}"

def start_display_task():
    async def display():
        while True:
            with status_lock:
                clear_screen()
                print(f"{Fore.CYAN}=== 🚀 Solix Account Monitor 🚀 ==={Style.RESET_ALL}")
                print(f"{Fore.CYAN}📊 Monitoring {len(account_status)} accounts{Style.RESET_ALL}")
                print(f"{Fore.CYAN}🔄 Pinging every {PING_INTERVAL} seconds{Style.RESET_ALL}")
                print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
                for email, st in account_status.items():
                    masked_email = mask_email(email)
                    quality_emoji = get_quality_emoji(st['connection_quality'])
                    quality_color = get_quality_color(st['connection_quality'])
                    
                    print(
                        f"{Fore.CYAN}{masked_email} | "
                        f"{quality_color}Quality: {st['connection_quality']}{quality_emoji} | "
                        f"{Fore.GREEN}Internet: {format_points(st['internet_points'])} | "
                        f"{Fore.YELLOW}Total: {format_points(st['total_points'])} | "
                        f"{Fore.BLUE}Next: {st['next_ping']}s{Style.RESET_ALL}"
                    )
            await asyncio.sleep(1)
    return asyncio.create_task(display())


async def ping_account(session: aiohttp.ClientSession, email: str, token: str) -> bool:
    hdr = headers.copy()
    hdr['authorization'] = f"Bearer {token}"
    proxy = get_random_proxy()
    proxy_kw = {'proxy': proxy} if proxy else {}
    
    # Rate limiting check
    with rate_limit_lock:
        current_time = time.time()
        last_time = last_request_time.get(email, 0)
        if current_time - last_time < MIN_REQUEST_INTERVAL:
            await asyncio.sleep(MIN_REQUEST_INTERVAL - (current_time - last_time))
        last_request_time[email] = time.time()
    
    for _ in range(MAX_RETRIES):
        try:
            async with session.get(PING_URL, headers=hdr, **proxy_kw) as resp:
                if resp.status == 200:
                    try:
                        text = await resp.text()
                        try:
                            d = json.loads(text)
                            if isinstance(d, dict) and 'data' in d:
                                cq = d.get('data', 0)
                                async with session.get(POINTS_URL, headers=hdr, **proxy_kw) as pr:
                                    if pr.status == 200:
                                        try:
                                            pd = await pr.json()
                                            if isinstance(pd, dict) and pd.get('result') == 'success':
                                                data = pd['data']
                                                await update_status(
                                                    email,
                                                    cq,
                                                    data.get('totalPointInternet', 0),
                                                    data.get('total', 0)
                                                )
                                                return True
                                            else:
                                                await update_status(
                                                    email,
                                                    account_status[email]['connection_quality'],
                                                    account_status[email]['internet_points'],
                                                    account_status[email]['total_points'],
                                                    f"Points API error: {pd.get('message', 'Unknown error')}"
                                                )
                                                return False
                                        except json.JSONDecodeError:
                                            await update_status(
                                                email,
                                                account_status[email]['connection_quality'],
                                                account_status[email]['internet_points'],
                                                account_status[email]['total_points'],
                                                f"Invalid JSON from points API"
                                            )
                                            return False
                                    else:
                                        await update_status(
                                            email,
                                            account_status[email]['connection_quality'],
                                            account_status[email]['internet_points'],
                                            account_status[email]['total_points'],
                                            f"Points API status: {pr.status}"
                                        )
                                        return False
                            else:
                                await update_status(
                                    email,
                                    account_status[email]['connection_quality'],
                                    account_status[email]['internet_points'],
                                    account_status[email]['total_points'],
                                    f"Invalid ping response format"
                                )
                                return False
                        except json.JSONDecodeError:
                            await update_status(
                                email,
                                account_status[email]['connection_quality'],
                                account_status[email]['internet_points'],
                                account_status[email]['total_points'],
                                f"Invalid JSON from ping API"
                            )
                            return False
                    except Exception as e:
                        await update_status(
                            email,
                            account_status[email]['connection_quality'],
                            account_status[email]['internet_points'],
                            account_status[email]['total_points'],
                            f"Error reading response: {str(e)}"
                        )
                        return False
                else:
                    await update_status(
                        email,
                        account_status[email]['connection_quality'],
                        account_status[email]['internet_points'],
                        account_status[email]['total_points'],
                        f"Ping API status: {resp.status}"
                    )
                    return False
        except aiohttp.ClientError as e:
            await update_status(
                email,
                account_status[email]['connection_quality'],
                account_status[email]['internet_points'],
                account_status[email]['total_points'],
                f"Network error: {str(e)}"
            )
            await asyncio.sleep(RETRY_DELAY)
        except Exception as e:
            await update_status(
                email,
                account_status[email]['connection_quality'],
                account_status[email]['internet_points'],
                account_status[email]['total_points'],
                f"Unexpected error: {str(e)}"
            )
            await asyncio.sleep(RETRY_DELAY)
    return False


def create_worker(email: str, password: str):
    async def worker():
        async with aiohttp.ClientSession() as session:
            token = await get_token_async(session, email, password)
            if not token:
                await update_status(
                    email,
                    '--',
                    '--',
                    '--',
                    "Failed to get token"
                )
                return
                
            while True:
                with status_lock:
                    nping = account_status[email]['next_ping']
                if nping <= 0:
                    ok = await ping_account(session, email, token)
                    if not ok:
                        token = await get_token_async(session, email, password) or token
                await asyncio.sleep(1)
    return worker


# Main async entry
async def main_async():
    # Load setup
    load_proxies()
    accounts = read_credentials()
    if not accounts:
        return

    # Initialize state
    for email, _ in accounts:
        account_status[email] = {
            'connection_quality': '--',
            'internet_points': '--',
            'total_points': '--',
            'next_ping': PING_INTERVAL,
            'error': None
        }

    # Start background tasks inside event loop
    countdown_task = start_countdown_task()
    display_task = start_display_task()
    workers = [asyncio.create_task(create_worker(email, pwd)()) for email, pwd in accounts]

    # Await indefinitely
    await asyncio.gather(countdown_task, display_task, *workers)


def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
