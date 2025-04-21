import requests
import time
from datetime import datetime
import json
import random
from colorama import init, Fore, Style
import asyncio
import aiohttp
from typing import Dict, Optional, Tuple, List
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Initialize colorama
init(autoreset=True)

# List of task IDs to rotate through
TASK_IDS = [
    "67dfc3529fa45a72cc5dc571",
    "67dfc3529fa45a72cc5dc572",
    "67dfc3529fa45a72cc5dc573",
    "67dfc3529fa45a72cc5dc574",
    "67dfc3529fa45a72cc5dc575",
    "67dfc3529fa45a72cc5dc576",
    "67dfc3529fa45a72cc5dc577"
]

# Semaphore to control concurrent requests
MAX_CONCURRENT_REQUESTS = 5  # Reduced to 5 workers

# Proxy management
proxies = []
proxy_lock = threading.Lock()

def load_proxies(filename='proxy.txt'):
    global proxies
    try:
        with open(filename, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if not proxies:
            print(f"{Fore.RED}❌ Error: No proxies found in proxy.txt{Style.RESET_ALL}")
        else:
            print(f"{Fore.GREEN}✅ Loaded {len(proxies)} proxies{Style.RESET_ALL}")
    except FileNotFoundError:
        print(f"{Fore.RED}❌ Error: proxy.txt not found{Style.RESET_ALL}")

def get_random_proxy():
    with proxy_lock:
        if not proxies:
            return None
        return random.choice(proxies)

def read_credentials(filename='akun.txt') -> List[Tuple[str, str]]:
    accounts = []
    try:
        with open(filename, 'r') as f:
            for line in f:
                if ':' in line:
                    email, password = line.strip().split(':', 1)
                    accounts.append((email, password))
        if not accounts:
            print(f"{Fore.RED}❌ Error: No accounts found in akun.txt{Style.RESET_ALL}")
        return accounts
    except FileNotFoundError:
        print(f"{Fore.RED}❌ Error: akun.txt not found{Style.RESET_ALL}")
        return []

def get_token(email: str, password: str) -> Optional[str]:
    url = 'https://api.solixdepin.net/api/auth/login-password'
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9,id;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://dashboard.solixdepin.net',
        'referer': 'https://dashboard.solixdepin.net/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    
    data = {
        'email': email,
        'password': password
    }
    
    proxy = get_random_proxy()
    proxy_dict = {'http': proxy, 'https': proxy} if proxy else None
    
    try:
        response = requests.post(url, headers=headers, json=data, proxies=proxy_dict)
        if response.status_code in [200, 201]:
            data = response.json()
            if data.get('result') == 'success':
                return data.get('data', {}).get('accessToken')
        print(f"{Fore.RED}❌ Login failed for {email}! Status: {response.status_code}{Style.RESET_ALL}")
        return None
    except Exception as e:
        print(f"{Fore.RED}❌ Error during login for {email}: {str(e)}{Style.RESET_ALL}")
        return None

async def get_total_points_async(session: aiohttp.ClientSession, token: str) -> Optional[float]:
    url = 'https://api.solixdepin.net/api/point/get-total-point'
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9,id;q=0.8',
        'authorization': f'Bearer {token}',
        'origin': 'https://dashboard.solixdepin.net',
        'referer': 'https://dashboard.solixdepin.net/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    
    proxy = get_random_proxy()
    
    try:
        async with session.get(url, headers=headers, proxy=proxy) as response:
            if response.status == 200:
                data = await response.json()
                return data.get('data', {}).get('total', 0)
            return None
    except Exception as e:
        print(f"{Fore.RED}❌ Error getting points: {str(e)}{Style.RESET_ALL}")
        return None

async def claim_task_async(session: aiohttp.ClientSession, token: str, task_id: str) -> Tuple[int, str]:
    url = 'https://api.solixdepin.net/api/task/claim-task'
    
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'en-US,en;q=0.9,id;q=0.8',
        'authorization': f'Bearer {token}',
        'content-type': 'application/json',
        'origin': 'https://dashboard.solixdepin.net',
        'referer': 'https://dashboard.solixdepin.net/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
    }
    
    data = {
        'taskId': task_id
    }
    
    proxy = get_random_proxy()
    
    try:
        async with session.post(url, headers=headers, json=data, proxy=proxy) as response:
            return response.status, await response.text()
    except Exception as e:
        return None, str(e)

async def claim_worker(session: aiohttp.ClientSession, token: str, task_id: str, semaphore: asyncio.Semaphore,
                      stats: Dict, last_points: float, max_points: float) -> bool:
    async with semaphore:
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"\n{Fore.YELLOW}⏳ Claiming task {task_id} at {current_time}{Style.RESET_ALL}")
        
        status_code, response = await claim_task_async(session, token, task_id)
        
        if status_code in [200, 201]:
            print(f"{Fore.GREEN}✅ Success! Task {task_id} - Status Code: {status_code}{Style.RESET_ALL}")
            stats['successful_claims'] += 1
            
            # Check points after successful claim
            current_points = await get_total_points_async(session, token)
            if current_points is not None:
                points_gained = current_points - last_points
                print(f"{Fore.GREEN}💰 Current Points: {current_points:,.2f} (+{points_gained:,.2f}){Style.RESET_ALL}")
                stats['last_points'] = current_points
                
                # Check if max points reached
                if current_points >= max_points:
                    print(f"{Fore.YELLOW}🎯 Max points ({max_points}) reached! Moving to next account...{Style.RESET_ALL}")
                    return True
            else:
                print(f"{Fore.RED}❌ Failed to get updated points{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ Failed! Task {task_id} - Status Code: {status_code}{Style.RESET_ALL}")
            stats['failed_claims'] += 1
            
            if status_code == 429:
                wait_time = random.uniform(1, 3)
                print(f"{Fore.YELLOW}⚠️ Rate limited for task {task_id}! Waiting {wait_time:.2f}s...{Style.RESET_ALL}")
                await asyncio.sleep(wait_time)
            elif status_code == 401:
                stats['token_expired'] = True
        return False

async def process_account(email: str, password: str, max_points: float) -> None:
    print(f"\n{Fore.CYAN}=== 🚀 Processing Account: {email} 🚀 ==={Style.RESET_ALL}")
    
    token = get_token(email, password)
    if not token:
        return
    
    async with aiohttp.ClientSession() as session:
        initial_points = await get_total_points_async(session, token)
        if initial_points is None:
            print(f"{Fore.RED}❌ Failed to get current points for {email}{Style.RESET_ALL}")
            return
            
        if initial_points >= max_points:
            print(f"{Fore.YELLOW}🎯 Account {email} already has {initial_points:,.2f} points (max: {max_points}) - Skipping{Style.RESET_ALL}")
            return
            
        print(f"{Fore.GREEN}💎 Current total points: {initial_points:,.2f}{Style.RESET_ALL}")
        
        stats = {
            'successful_claims': 0,
            'failed_claims': 0,
            'last_points': initial_points,
            'token_expired': False
        }
        
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        while True:
            tasks = []
            for task_id in TASK_IDS:
                tasks.append(claim_worker(session, token, task_id, semaphore, stats, stats['last_points'], max_points))
            
            results = await asyncio.gather(*tasks)
            
            if any(results):  # If any worker returned True (max points reached)
                break
                
            if stats['token_expired']:
                print(f"{Fore.YELLOW}🔄 Token expired for {email}, refreshing...{Style.RESET_ALL}")
                token = get_token(email, password)
                if not token:
                    print(f"{Fore.RED}❌ Failed to refresh token for {email}. Moving to next account...{Style.RESET_ALL}")
                    break
                print(f"{Fore.GREEN}✅ Token refreshed for {email}!{Style.RESET_ALL}")
                stats['token_expired'] = False
            
            # Small delay between batches
            delay = random.uniform(7, 10)
            print(f"\n{Fore.CYAN}⏳ Waiting {delay:.2f}s before next batch...{Style.RESET_ALL}")
            await asyncio.sleep(delay)
        
        print(f"\n{Fore.CYAN}=== 🏁 Account Summary: {email} ==={Style.RESET_ALL}")
        print(f"{Fore.GREEN}✅ Successful claims: {stats['successful_claims']}{Style.RESET_ALL}")
        print(f"{Fore.RED}❌ Failed claims: {stats['failed_claims']}{Style.RESET_ALL}")
        
        final_points = await get_total_points_async(session, token)
        if final_points is not None:
            total_points_gained = final_points - initial_points
            print(f"{Fore.CYAN}✨ Total points gained: {total_points_gained:,.2f}{Style.RESET_ALL}")
            if stats['successful_claims'] > 0:
                avg_points = total_points_gained/stats['successful_claims']
                print(f"{Fore.CYAN}📊 Average points per claim: {avg_points:,.2f}{Style.RESET_ALL}")

async def main_async():
    print(f"\n{Fore.CYAN}=== 🚀 Solix Multi-Account Task Claimer 🚀 ==={Style.RESET_ALL}")
    
    # Load proxies first
    load_proxies()
    
    # Read accounts from file
    accounts = read_credentials()
    if not accounts:
        return
    
    # Get max points limit
    while True:
        try:
            max_points = float(input(f"\n{Fore.YELLOW}🎯 Enter maximum points per account: {Style.RESET_ALL}"))
            if max_points > 0:
                break
            print(f"{Fore.RED}Please enter a positive number{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Please enter a valid number{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}📊 Processing {len(accounts)} accounts with max {max_points} points each{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")
    
    for email, password in accounts:
        await process_account(email, password, max_points)
        print(f"{Fore.CYAN}{'=' * 50}{Style.RESET_ALL}")

def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main_async())

if __name__ == "__main__":
    main()