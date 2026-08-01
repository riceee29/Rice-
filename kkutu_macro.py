import os
import re
import time
import threading
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

app = Flask(__name__)
app.config['SECRET_KEY'] = 'kkutu_rice_pro_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 글로벌 상태 관리 ---
BOT_STATE = {
    "running": False,
    "delay": 0.4,
    "dict_file": "dictionary.txt",
    "status_msg": "대기 중"
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

# --- 로깅 함수 ---
def send_log(message, log_type="info"):
    socketio.emit('log', {'msg': message, 'type': log_type})

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
            send_log(f"새 단어 학습 완료 ({source}): {clean_word}", "success")
            socketio.emit('dict_updated', {'count': len(all_word_set)})
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
        send_log("Edge 브라우저가 실행되었습니다. 로그인 후 방에 입장해주세요.", "info")
    except Exception as e:
        send_log(f"브라우저 실행 중 오류 발생: {e}", "error")
        BOT_STATE["running"] = False
        socketio.emit('status_change', {'running': False})
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
                send_log(f"내 차례 감지! 제시어: [{raw_text}]", "warn")
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
                
                send_log(f"단어 입력 시도: {target} (딜레이: {BOT_STATE['delay']}초)", "info")
                time.sleep(BOT_STATE["delay"])

                fb = check_feedback(driver)
                if fb == "SKIP":
                    send_log(f"입력 거부됨(무효/금지어 등): {target} -> 다음 단어 탐색", "error")
                    idx += 1 
                else:
                    my_last_word = target 
            else:
                if not stop_round:
                    send_log("사용 가능한 단어를 모두 소모했습니다.", "error")
                    stop_round = True
        except Exception:
            pass
            
        time.sleep(0.05)

    try:
        driver.quit()
    except Exception:
        pass
    send_log("매크로 엔진이 정지되었습니다.", "warn")

# --- Flask 라우트 & API ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/words', methods=['GET'])
def get_words():
    query = request.args.get('search', '').strip()
    words = sorted(list(all_word_set), key=lambda x: (len(x), x), reverse=True)
    if query:
        words = [w for w in words if query in w]
    return jsonify({"count": len(words), "words": words[:500]}) # 최대 500개 표시

@app.route('/api/words/add', methods=['POST'])
def add_words():
    data = request.json
    text = data.get('words', '')
    words = text.split()
    added = 0
    for w in words:
        if save_learned_word(w, source="MANUAL"):
            added += 1
    return jsonify({"success": True, "added": added, "total": len(all_word_set)})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    if 'delay' in data:
        BOT_STATE['delay'] = max(0.05, float(data['delay']))
        send_log(f"응답 딜레이 변경됨: {BOT_STATE['delay']}초", "info")
    return jsonify({"success": True, "delay": BOT_STATE['delay']})

# --- SocketIO 이벤트 ---
@socketio.on('toggle_bot')
def handle_toggle_bot(data):
    target_state = data.get('run', False)
    if target_state and not BOT_STATE["running"]:
        BOT_STATE["running"] = True
        threading.Thread(target=macro_worker, daemon=True).start()
        emit('status_change', {'running': True})
    elif not target_state and BOT_STATE["running"]:
        BOT_STATE["running"] = False
        emit('status_change', {'running': False})

if __name__ == '__main__':
    load_dict()
    print(">> Rice Pro Web Controller 가동 시작: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)