import requests
import configparser
import random
import string
from faker import Faker
import time
from datetime import datetime
from colorama import init, Fore, Style
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

init(autoreset=True)

# Load configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Constants
DOMAIN = config['settings']['domain']
PASSWORD = config['settings']['password']
REFCODE = config['settings']['refcode']
RANDOM_PASSWORD = config['settings'].getboolean('random_password', False)

# Captcha settings
CAPTCHA_PROVIDER = config['captcha']['provider']
API_KEY = config['captcha']['api_key']
TURNSTILE_SITEKEY = config['captcha']['site_key']
TURNSTILE_PAGE_URL = f"https://{config['captcha']['site_domain']}"

# API settings
API_URL = "https://api.solixdepin.net/api/auth/register"

# Load proxies
def load_proxies():
    try:
        with open('proxy.txt', 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        return proxies
    except FileNotFoundError:
        log_fail("proxy.txt not found!")
        return []
    except Exception as e:
        log_fail(f"Error loading proxies: {str(e)}")
        return []

# Global proxy list
PROXIES = load_proxies()

headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://dashboard.solixdepin.net",
    "priority": "u=1, i",
    "referer": "https://dashboard.solixdepin.net/",
    "sec-ch-ua": '"Google Chrome";v="135", "Not-A.Brand";v="8", "Chromium";v="135"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
}

def log_info(msg, idx=None):
    if idx is not None:
        print(f"{Fore.CYAN}[{idx}] 🔵 {msg}{Style.RESET_ALL}")
    else:
        print(f"{Fore.CYAN}🔵 {msg}{Style.RESET_ALL}")

def log_success(msg, idx=None):
    if idx is not None:
        print(f"{Fore.GREEN}[{idx}] ✅ {msg}{Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}✅ {msg}{Style.RESET_ALL}")

def log_fail(msg, idx=None):
    if idx is not None:
        print(f"{Fore.RED}[{idx}] ❌ {msg}{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}❌ {msg}{Style.RESET_ALL}")

def generate_email():
    fake = Faker()
    first_name = fake.first_name().lower()
    last_name = fake.last_name().lower()
    random_number = random.randint(10000, 99999)
    return f"{first_name}{last_name}{random_number}@{DOMAIN}"

def generate_random_password():
    """Generate a random password with minimum 12 characters including uppercase, lowercase, digits and symbols"""
    # Define character sets
    uppercase = string.ascii_uppercase
    lowercase = string.ascii_lowercase
    digits = string.digits
    symbols = '!@#$%^&*'
    
    # Ensure at least one character from each set
    password = [
        random.choice(uppercase),
        random.choice(lowercase),
        random.choice(digits),
        random.choice(symbols)
    ]
    
    # Fill the rest randomly
    all_chars = uppercase + lowercase + digits + symbols
    password.extend(random.choice(all_chars) for _ in range(8))  # 8 more characters to reach minimum 12
    
    # Shuffle the password
    random.shuffle(password)
    
    return ''.join(password)

def solve_turnstile_sctg(idx=None):
    """Solve CAPTCHA using SCTG"""
    try:
        params = {
            'key': API_KEY,
            'method': 'turnstile',
            'sitekey': TURNSTILE_SITEKEY,
            'pageurl': TURNSTILE_PAGE_URL
        }
        
        response = requests.post(
            "https://api.sctg.xyz/in.php",
            data=params,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=30
        )
        
        if response.text.startswith('OK|'):
            captcha_id = response.text.split('|')[1]
            return get_sctg_result(captcha_id, idx)
        else:
            log_fail(f"SCTG Error: {response.text}", idx=idx)
            return None
            
    except requests.RequestException as e:
        log_fail(f"SCTG Request Error: {str(e)}", idx=idx)
        return None

def get_sctg_result(captcha_id, idx=None):
    """Check SCTG CAPTCHA solution status"""
    for _ in range(20):  # Max 20 attempts
        time.sleep(5)
        try:
            res = requests.get(
                "https://api.sctg.xyz/res.php",
                params={'key': API_KEY, 'action': 'get', 'id': captcha_id},
                timeout=30
            )
            
            if res.text.startswith('OK|'):
                log_success("SCTG solved OK", idx=idx)
                return res.text.split('|')[1]
            elif res.text != 'CAPCHA_NOT_READY':
                log_fail(f"SCTG Error: {res.text}", idx=idx)
                break
                
        except requests.RequestException as e:
            log_fail(f"SCTG Result Error: {str(e)}", idx=idx)
    return None

def solve_turnstile_2captcha(idx=None):
    """Solve CAPTCHA using 2captcha"""
    try:
        # Submit captcha task
        params = {
            'key': API_KEY,
            'method': 'turnstile',
            'sitekey': TURNSTILE_SITEKEY,
            'pageurl': TURNSTILE_PAGE_URL,
            'json': 1
        }
        
        response = requests.post(
            "https://2captcha.com/in.php",
            data=params,
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=30
        )
        
        if response.json().get('status') == 1:
            captcha_id = response.json()['request']
            return get_2captcha_result(captcha_id, idx)
        else:
            log_fail(f"2captcha Error: {response.text}", idx=idx)
            return None
            
    except requests.RequestException as e:
        log_fail(f"2captcha Request Error: {str(e)}", idx=idx)
        return None

def get_2captcha_result(captcha_id, idx=None):
    """Check 2captcha solution status"""
    for _ in range(20):  # Max 20 attempts
        time.sleep(5)
        try:
            res = requests.get(
                "https://2captcha.com/res.php",
                params={'key': API_KEY, 'action': 'get', 'id': captcha_id, 'json': 1},
                timeout=30
            )
            
            if res.json().get('status') == 1:
                log_success("2captcha solved OK", idx=idx)
                return res.json()['request']
            elif res.json().get('request') != 'CAPCHA_NOT_READY':
                log_fail(f"2captcha Error: {res.text}", idx=idx)
                break
                
        except requests.RequestException as e:
            log_fail(f"2captcha Result Error: {str(e)}", idx=idx)
    return None

def solve_turnstile_capsolver(idx=None):
    """Solve CAPTCHA using capsolver"""
    try:
        data = {
            "clientKey": API_KEY,
            "task": {
                "type": "TurnstileTask",
                "websiteURL": TURNSTILE_PAGE_URL,
                "websiteKey": TURNSTILE_SITEKEY
            }
        }
        
        response = requests.post(
            "https://api.capsolver.com/createTask",
            json=data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.json().get('errorId') == 0:
            task_id = response.json()['taskId']
            return get_capsolver_result(task_id, idx)
        else:
            log_fail(f"Capsolver Error: {response.text}", idx=idx)
            return None
            
    except requests.RequestException as e:
        log_fail(f"Capsolver Request Error: {str(e)}", idx=idx)
        return None

def get_capsolver_result(task_id, idx=None):
    """Check capsolver solution status"""
    for _ in range(20):  # Max 20 attempts
        time.sleep(5)
        try:
            data = {
                "clientKey": API_KEY,
                "taskId": task_id
            }
            
            res = requests.post(
                "https://api.capsolver.com/getTaskResult",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            if res.json().get('status') == 'ready':
                log_success("Capsolver solved OK", idx=idx)
                return res.json()['solution']['token']
            elif res.json().get('status') != 'processing':
                log_fail(f"Capsolver Error: {res.text}", idx=idx)
                break
                
        except requests.RequestException as e:
            log_fail(f"Capsolver Result Error: {str(e)}", idx=idx)
    return None

def solve_turnstile(idx=None):
    """Solve CAPTCHA based on provider"""
    if CAPTCHA_PROVIDER.lower() == '2captcha':
        return solve_turnstile_2captcha(idx=idx)
    elif CAPTCHA_PROVIDER.lower() == 'capsolver':
        return solve_turnstile_capsolver(idx=idx)
    elif CAPTCHA_PROVIDER.lower() == 'sctg':
        return solve_turnstile_sctg(idx=idx)
    else:
        log_fail(f"Unsupported captcha provider: {CAPTCHA_PROVIDER}", idx=idx)
        return None

def register_account(idx=None):
    email = generate_email()
    log_info(f"Attempting to register: {email}", idx=idx)
    
    # Generate or use fixed password
    account_password = generate_random_password() if RANDOM_PASSWORD else PASSWORD
    
    # Get proxy for this registration
    proxy = None
    if PROXIES:
        proxy = random.choice(PROXIES)
        proxy_dict = {
            'http': proxy,
            'https': proxy
        }
        log_info(f"Using proxy: {proxy}", idx=idx)
    else:
        proxy_dict = None
    
    # Get captcha token
    captcha_token = solve_turnstile(idx=idx)
    if not captcha_token:
        log_fail("Failed to solve captcha", idx=idx)
        return False
    
    # Prepare registration data
    data = {
        "email": email,
        "password": account_password,
        "captchaToken": captcha_token,
        "referralCode": REFCODE
    }
    
    try:
        response = requests.post(
            API_URL,
            json=data,
            headers=headers,
            proxies=proxy_dict,
            timeout=30
        )
        
        if response.status_code == 201:
            log_success(f"Successfully registered: {email}", idx=idx)
            with open("akun.txt", "a") as f:
                f.write(f"{email}:{account_password}\n")
            return True
        else:
            log_fail(f"Registration failed: {response.text}", idx=idx)
            return False
            
    except Exception as e:
        log_fail(f"Registration error: {str(e)}", idx=idx)
        return False

def print_welcome_message():
    print(Fore.WHITE + r"""

   /$$               /$$                                       /$$                                  
  | $$              | $$                                      | $$                                  
 /$$$$$$   /$$   /$$| $$   /$$  /$$$$$$  /$$$$$$$   /$$$$$$  /$$$$$$   /$$   /$$  /$$$$$$  /$$   /$$
|_  $$_/  | $$  | $$| $$  /$$/ |____  $$| $$__  $$ /$$__  $$|_  $$_/  | $$  | $$ /$$__  $$| $$  | $$
  | $$    | $$  | $$| $$$$$$/   /$$$$$$$| $$  \ $$| $$  \ $$  | $$    | $$  | $$| $$  \__/| $$  | $$
  | $$ /$$| $$  | $$| $$_  $$  /$$__  $$| $$  | $$| $$  | $$  | $$ /$$| $$  | $$| $$      | $$  | $$
  |  $$$$/|  $$$$$$/| $$ \  $$|  $$$$$$$| $$  | $$|  $$$$$$$  |  $$$$/|  $$$$$$/| $$      |  $$$$$$/
   \___/   \______/ |__/  \__/ \_______/|__/  |__/ \____  $$   \___/   \______/ |__/       \______/ 
                                                   /$$  \ $$                                        
                                                  |  $$$$$$/                                        
                                                   \______/                                         

          """)
    print(Fore.GREEN + Style.BRIGHT + "Solix Depin Auto Reff")
  



def main():
    print_welcome_message()
    
    # Number of accounts to create
    num_accounts = int(input("Enter number of accounts to create: "))
    num_threads = int(input("Enter number of threads: "))
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = {
            executor.submit(register_account, i): i
            for i in range(1, num_accounts + 1)
        }
        
        for future in as_completed(futures):
            future.result()

if __name__ == "__main__":
    main()
