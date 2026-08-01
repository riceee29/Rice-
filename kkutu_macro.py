import os
import re
import time
import subprocess
import sys

# --- 자동 라이브러리 설치 로직 ---
def install_dependencies():
    required = ['selenium']
    for package in required:
        try:
            __import__(package)
        except ImportError:
            print(f"[*] Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])

# 프로그램 시작 시 의존성 설치 확인
install_dependencies()

# 설치 후 임포트
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# --- 콘솔 색상 정의 ---
class Color:
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# --- 무지개 배너 출력 함수 ---
def print_rainbow_banner():
    banner_lines = [
        r"    ██████╗ ██╗ ██████╗███████╗    ██████╗ ██████╗  ██████╗ ",
        r"    ██╔══██╗██║██╔════╝██╔════╝    ██╔══██╗██╔══██╗██╔═══██╗",
        r"    ██████╔╝██║██║     █████╗      ██████╔╝██████╔╝██║   ██║",
        r"    ██╔══██╗██║██║     ██╔══╝      ██╔═══╝ ██╔══██╗██║   ██║",
        r"    ██║  ██║██║╚██████╗███████╗    ██║     ██║  ██║╚██████╔╝",
        r"    ╚═╝  ╚═╝╚═╝ ╚═════╝╚══════╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝ "
    ]
    colors = [Color.RED, Color.YELLOW, Color.GREEN, Color.CYAN, Color.BLUE, Color.PURPLE]
    
    for i, line in enumerate(banner_lines):
        print(colors[i % len(colors)] + line + Color.END)

# --- 글로벌 상태 관리 ---
BOT_STATE = {
    "running": True,
    "delay": 0.4,
    "dict_file": "dictionary.txt"
}

ko_map, en_map = {}, {}
all_word_set = set()

JUNK_KEYWORDS = [
    "명사", "어근", "부사", "대사전", "국어원", "CCBYSA", "기호", "번지", "수도", 
    "지명", "역사", "의학", "화학", "종교", "따위", "사람", "사물", "의미", "그린것", 
    "시스템", "업데이트", "공지", "안내", "쿠폰", "준비", "클리어", "낱말", "입력", "차례"
]

DUUM_RULES = {
    "리":"이", "라":"아", "래":"애", "로":"오", "루":"우", "르":"으", 
    "니":"이", "나":"아", "녀":"여", "뇨":"요", "뉴":"유", "내":"애", 
    "네":"에", "률":"율", "렬":"열", "율":"률", "열":"렬", "락":"악", 
    "란":"안", "람":"암", "랍":"압", "랑":"앙", "략":"약", "량":"양", 
    "려":"여", "력":"역", "련":"연", "렴":"염", "렵":"엽", "령":"영", 
    "례":"예", "린":"인", "림":"임", "립":"입"
}

def log(msg, tag="INFO"):
    tag_colors = {
        "INFO": Color.CYAN,
        "SYSTEM": Color.GREEN,
        "GAME": Color.PURPLE,
        "LEARN": Color.YELLOW,
        "INPUT": Color.BLUE,
        "WARN": Color.RED,
        "ERROR": Color.BOLD + Color.RED
    }
    color = tag_colors.get(tag, Color.END)
    print(f"{color}[{tag}]{Color.END} {msg}")

# --- 사전 관리 로직 ---
def update_memory(word):
    if len(word) > 20 or any(junk in word for junk in JUNK_KEYWORDS):
        return False
        
    clean_word = re.sub(r'[^a-zA-Z가-힣]', '', word)
    if len(clean_word) < 2 or clean_word in all_word_set:
        return False
    
    all_word_set.add(clean_word)
    first_char = clean_word[0]
    
    if '가' <= first_char <= '힣':
        if first_char not in ko_map: ko_map[first_char] = []
        ko_map[first_char].append(clean_word)
        ko_map[first_char].sort(key=len, reverse=True)
    elif 'A' <= first_char.upper() <= 'Z':
        first_char = first_char.upper()
        if first_char not in en_map: en_map[first_char] = []
        en_map[first_char].append(clean_word.upper())
        en_map[first_char].sort(key=len, reverse=True)
    return True

def load_dict():
    all_word_set.clear()
    ko_map.clear()
    en_map.clear()
    
    if not os.path.exists(BOT_STATE["dict_file"]):
        open(BOT_STATE["dict_file"], "w", encoding="utf-8").close()
        
    loaded_count = 0
    with open(BOT_STATE["dict_file"], "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            for p in parts:
                if 2 <= len(p) <= 20:
                    if update_memory(p):
                        loaded_count += 1
    return len(all_word_set)

def save_learned_word(word, source="LEARNED"):
    if len(word) > 20 or any(junk in word for junk in JUNK_KEYWORDS):
        return False

    clean_word = re.sub(r'[^a-zA-Z가-힣]', '', word)
    if clean_word in all_word_set or len(clean_word) < 2: 
        return False
    
    try:
        if update_memory(clean_word):
            with open(BOT_STATE["dict_file"], "a", encoding="utf-8") as f:
                f.write(f"{len(clean_word)}\t{clean_word}\t[{source}]\n")
            log(f"New word learned ({source}): {clean_word}", "LEARN")
            return True
    except Exception:
        pass
    return False

# --- Selenium 매크로 엔진 ---
def is_my_turn(driver):
    try:
        turn_el = driver.find_elements(By.XPATH, "//*[contains(text(), '내 차례!')]")
        return len(turn_el) > 0 and turn_el[0].is_displayed()
    except Exception:
        return False

def check_feedback(driver):
    try:
        msg_el = driver.find_element(By.CSS_SELECTOR, ".bg-red\\/80")
        text = msg_el.text.strip()
        if any(x in text for x in ["이미", "무효", "낱말집", "없는", "사전에", "금지", "보호막"]):
            return "SKIP"
    except Exception:
        pass
    return None

def smart_word_stealer(driver):
    try:
        history_elements = driver.find_elements(By.CSS_SELECTOR, "ol li span")
        for el in history_elements:
            txt = el.text.strip()
            main_word = txt.split(' ')[0].split('\n')[0]
            save_learned_word(main_word, source="HISTORY")

        possible_labels = driver.find_elements(By.XPATH, "//*[contains(text(), '가능했던 낱말')]")
        for label in possible_labels:
            parent = label.find_element(By.XPATH, "./..")
            child_divs = parent.find_elements(By.TAG_NAME, "div")
            count = 0
            for div in child_divs:
                word = div.text.strip()
                if word and "낱말" not in word and 2 <= len(word) <= 15:
                    save_learned_word(word, source="POSSIBLE")
                    count += 1
                    if count >= 3: break
    except Exception:
        pass

def macro_worker():
    options = Options()
    options.add_experimental_option("detach", True)
    options.add_argument("--start-maximized")
    options.add_experimental_option('excludeSwitches', ['enable-logging', 'enable-automation'])
    
    try:
        driver = webdriver.Edge(options=options)
        driver.get("https://kkutu.kr/play")
        log("Edge browser started. Please log in and enter a room.", "SYSTEM")
    except Exception as e:
        log(f"Error starting browser: {e}", "ERROR")
        BOT_STATE["running"] = False
        return

    last_round_id, idx, stop_round, my_last_word = "", 0, False, ""

    while BOT_STATE["running"]:
        smart_word_stealer(driver)

        if not is_my_turn(driver):
            if my_last_word and not stop_round:
                save_learned_word(my_last_word, "SUCCESS")
                my_last_word = ""
            idx, stop_round, last_round_id = 0, False, ""
            time.sleep(0.1)
            continue

        try:
            char_el = driver.find_element(By.CSS_SELECTOR, ".m-auto.min-h-15 .mx-auto")
            raw_text = char_el.text.strip()
            current_char = raw_text[0]

            if last_round_id != current_char:
                log(f"My turn! Target char: [{raw_text}]", "GAME")
                last_round_id, idx, stop_round = current_char, 0, False

            if stop_round: 
                time.sleep(0.1)
                continue

            candidates = ko_map.get(current_char, [])
            alt = DUUM_RULES.get(current_char)
            if alt: 
                candidates = list(set(candidates + ko_map.get(alt, [])))
            candidates = sorted(candidates, key=len, reverse=True)

            if idx < len(candidates):
                target = candidates[idx]
                input_box = driver.find_element(By.CSS_SELECTOR, "input, textarea, .chat-input")
                input_box.click()
                input_box.send_keys(Keys.CONTROL + "a")
                input_box.send_keys(Keys.BACKSPACE)
                input_box.send_keys(target)
                input_box.send_keys(Keys.ENTER)
                
                log(f"Inputting: {target} (Delay: {BOT_STATE['delay']}s)", "INPUT")
                time.sleep(BOT_STATE["delay"])

                fb = check_feedback(driver)
                if fb == "SKIP":
                    log(f"Rejected: {target} -> Trying next word", "WARN")
                    idx += 1 
                else:
                    my_last_word = target 
            else:
                if not stop_round:
                    log("No words left for this character.", "WARN")
                    stop_round = True
        except Exception:
            pass
            
        time.sleep(0.05)

    try:
        driver.quit()
    except Exception:
        pass
    log("Macro engine stopped.", "SYSTEM")

# --- 메인 실행부 ---
if __name__ == '__main__':
    # 1. 무지개 로고 출력
    print_rainbow_banner()
    
    # 2. 사전 데이터 로드
    total_words = load_dict()
    print(f"{Color.GREEN}>> Dictionary loaded! Total words: {total_words}{Color.END}\n")
    print(f"{Color.YELLOW}>> Press Ctrl + C to exit.{Color.END}\n")
    
    # 3. 매크로 쓰레드 실행
    try:
        macro_worker()
    except KeyboardInterrupt:
        print(f"\n{Color.RED}>> Terminated by user.{Color.END}")
        BOT_STATE["running"] = False
