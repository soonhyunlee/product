import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import os
import urllib3
import time
import sys
import io

# 콘솔 출력 시 인코딩 오류 방지 (Windows cp949 환경 대응)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 경고 메시지 비활성화 (SSL 인증서 경고 방지)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================================
# 1. 설정: 제조사 및 광고성/불필요 문구 사전
# =========================================================================

# 제거할 제조업체명/브랜드명 목록 (길이순 정렬하여 긴 단어가 먼저 매칭되도록 함)
MANUFACTURERS = [
    "삼성전자공식대리점", "삼성전자공식", "삼성전자", "LG전자공식", "LG전자", 
    "소니코리아", "Sony", "소니", "Apple", "애플", "샤오미", "Xiaomi", 
    "다이슨", "Dyson", "필립스", "Philips", "HP", "에이치피", "Dell", "델", 
    "Lenovo", "레노버", "한성컴퓨터", "한성", "Asus", "에이수스", "Acer", "에이서", 
    "MSI", "엠에스아이", "삼성", "LG", "엘지", "쓰리엠", "3M", "폼텍라벨", "폼텍", "다스", "DAS",
    "오공", "일신", "중외"
]

# 제거할 광고성 문구, 혜택, 불필요한 태그/접두사/접미사
PROMOTIONAL_WORDS = [
    "정품인증", "공식인증", "공식대리점", "공식", "정품", "국내정품", "100%정품", "100% 정품",
    "무료배송", "당일배송", "총알배송", "빠른배송", "특가", "초특가", "할인", "이벤트", 
    "기획전", "쿠폰", "사은품", "증정", "추천", "인기", "신상품", "신제품", "최저가", 
    "단독", "한정수량", "한정", "풀패키지", "패키지", "세트", "정식수입", "해외직구", "직구",
    "국산", "실속형", "보급형", "다목적", "모음", "품절/입고", "품절", "입고"
]

# 제거할 단순 서술어 및 상품명에 불필요한 홍보성/꾸밈용 형용사/명사
VERBOSE_WORDS = [
    "19금","추천", "강추", "선물", "선물용", "가정용", "업소용", "사무용", "휴대용",
    "필수템", "인기템", "최고", "인기", "전문", "고급", "최고급", "기능", "성능", "일반"
]

# =========================================================================
# 2. 상품명 정제 알고리즘
# =========================================================================

def clean_brackets_and_junk(text):
    """
    괄호 [ ], ( ) 안에 제조사나 광고 문구가 들어가 있는 경우 괄호째 제거합니다.
    예: '[삼성전자] 파워건' -> ' 파워건'
    """
    if not isinstance(text, str):
        return ""
    
    # [ ] 또는 ( ) 매칭
    brackets = re.findall(r'\[[^\]]*\]|\([^\)]*\)', text)
    for b in brackets:
        inner = b[1:-1].strip().lower()
        # 괄호 안의 내용이 제조사명이나 광고 문구와 매칭되는지 확인
        should_remove = False
        for m in MANUFACTURERS:
            if m.lower() in inner:
                should_remove = True
                break
        for p in PROMOTIONAL_WORDS:
            if p.lower() in inner:
                should_remove = True
                break
        if should_remove:
            text = text.replace(b, " ")
            
    return text

def clean_product_name(text):
    """
    텍스트에서 제조사명과 불필요한 단어를 제거하고 깔끔하게 포맷팅합니다.
    """
    if not isinstance(text, str):
        return ""
    
    # 0. 유니코드 특수 공백 치환
    text = text.replace('\xa0', ' ').replace('\u200b', '')
    
    # 1. 특정 괄호 쓰레기 제거
    text = clean_brackets_and_junk(text)
    
    # 2. 제조사명 제거 (영어/숫자로만 이루어진 브랜드는 단어 경계 \b를 적용하여 3mm, 43mm 단위 손상 완벽 차단)
    for m in sorted(MANUFACTURERS, key=len, reverse=True):
        if re.match(r'^[a-zA-Z0-9\s]+$', m):
            pattern = re.compile(rf'\b{re.escape(m)}\b(?!\-[a-zA-Z0-9])', re.IGNORECASE)
        else:
            pattern = re.compile(rf'{re.escape(m)}(?!\-[a-zA-Z0-9])', re.IGNORECASE)
        text = pattern.sub(" ", text)
        
    # 3. 홍보성 키워드 제거
    for p in sorted(PROMOTIONAL_WORDS, key=len, reverse=True):
        pattern = re.compile(rf'\b{re.escape(p)}\b|{re.escape(p)}', re.IGNORECASE)
        text = pattern.sub(" ", text)
        
    # 4. 불필요한 단순 서술어 및 꾸밈 단어 제거
    for v in sorted(VERBOSE_WORDS, key=len, reverse=True):
        pattern = re.compile(rf'\b{re.escape(v)}\b|{re.escape(v)}', re.IGNORECASE)
        text = pattern.sub(" ", text)
        
    # 5. 남아있는 모든 괄호 문자( [, ], (, ), {, } )를 공백으로 치환하여 괄호 자체를 제거하고 띄어쓰기를 보장
    text = text.replace('[', ' ').replace(']', ' ').replace('(', ' ').replace(')', ' ').replace('{', ' ').replace('}', ' ')
    
    # 6. 불필요한 특수문자 제거 (맨 앞이나 맨 뒤의 공백, 하이픈, 쉼표, 슬래시 등 정밀 제거)
    text = re.sub(r'^[\s\-_,\./\:\;]+|[\s\-_,\./\:\;]+$', '', text)
    
    # 7. 중복 단어 제거 (순서는 유지하면서 고유 단어 조합으로 간결화)
    words = text.split()
    unique_words = []
    seen = set()
    for w in words:
        w_clean = re.sub(r'[^\w]', '', w).lower()
        if w_clean and w_clean not in seen:
            seen.add(w_clean)
            unique_words.append(w)
        elif not w_clean:
            unique_words.append(w)
            
    text = " ".join(unique_words)
    
    # 8. 다중 공백 단일화 및 양끝 공백 제거
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def optimize_product_name(text):
    """
    원본 상품명(A열)을 보고 제조사, 광고 문구, 중복 단어 및 단순 부식품/사양 키워드(~포함, ~사용 등)를 
    완벽하게 정밀 제거하여 가장 직관적이고 최적화된 상품명으로 축약해 줍니다 (길이 제한 삭제).
    """
    if not isinstance(text, str) or not text:
        return ""
        
    # 1. 브랜드/괄호/광고문구/중복 단어 기본 제거
    text = clean_product_name(text)
    
    # 2. 단어 분리 후 단순 수식성 접미사 및 단순 부속품 정보 단어 필터링
    words = text.split()
    optimized_words = []
    
    exclude_suffixes = ['포함', '사용', '후속', '기능', '대응', '증정', '사은품', '재질', '베어툴', '본체']
    
    for w in words:
        w_clean = re.sub(r'[^\w]', '', w)
        # 단어가 단순 수식/사양 접미사로 끝나는 경우 제외하여 핵심명만 남김
        if any(w_clean.endswith(s) for s in exclude_suffixes):
            continue
        optimized_words.append(w)
        
    if not optimized_words:
        optimized_words = words
        
    final_text = " ".join(optimized_words)
    return re.sub(r'\s+', ' ', final_text).strip()

def clean_scraped_title(scraped_title):
    """
    웹 페이지 크롤링 시 포함되는 사이트명 등의 공통 접미사를 필터링합니다.
    """
    if not scraped_title:
        return ""
    
    # 유니코드 특수 공백 치환
    scraped_title = scraped_title.replace('\xa0', ' ').replace('\u200b', '')
    
    # 쇼핑몰 공통 접미사 제거를 위한 구분자 분할
    separators = [" - ", " | ", " : ", " _ ", " / "]
    for sep in separators:
        if sep in scraped_title:
            parts = scraped_title.split(sep)
            scraped_title = parts[0]
            
    # 일반적인 쇼핑몰 이름 제거
    mall_suffixes = ["네이버 쇼핑", "쿠팡", "11번가", "G마켓", "옥션", "인터파크", "SSG.COM", "다나와", "에누리"]
    for suffix in mall_suffixes:
        scraped_title = scraped_title.replace(suffix, "")
        
    return scraped_title.strip()

def calculate_overlap(str1, str2):
    """
    두 문자열 간의 핵심 단어 오버랩(유사도)을 계산합니다.
    """
    words1 = set([w for w in re.findall(r'\w+', str1.lower()) if len(w) > 1])
    words2 = set([w for w in re.findall(r'\w+', str2.lower()) if len(w) > 1])
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    return len(intersection) / len(union)

# =========================================================================
# 3. 크롤링 로직 (상세 화면 확인)
# =========================================================================

def scrape_product_title(url):
    """
    상세화면 URL에 접속하여 상품명을 추출해 옵니다.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        if response.status_code != 200:
            print(f"   [크롤링 경고] HTTP 상태 코드 {response.status_code}")
            return None
        
        html_text = None
        
        # 1. 헤더에 charset이 선언되어 있는 경우 우선 사용
        content_type = response.headers.get("Content-Type", "").lower()
        if "charset=" in content_type:
            try:
                header_encoding = response.encoding
                if header_encoding and 'iso-8859-1' not in header_encoding.lower():
                    html_text = response.content.decode(header_encoding)
            except Exception:
                pass

        # 2. apparent_encoding이 한국어/유니코드 계열인 경우에만 신뢰
        if not html_text:
            apparent = response.apparent_encoding
            if apparent:
                apparent_lower = apparent.lower()
                if any(enc in apparent_lower for enc in ['utf-8', 'utf_8', 'utf8', 'euc-kr', 'euckr', 'cp949', 'cp-949']):
                    try:
                        html_text = response.content.decode(apparent)
                    except Exception:
                        pass

        # 3. 순차 디코딩 테스트
        if not html_text:
            for encoding in ['utf-8', 'cp949', 'euc-kr']:
                try:
                    html_text = response.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

        # 4. 마지막 보루: UTF-8 강제 변환
        if not html_text:
            html_text = response.content.decode('utf-8', errors='replace')
            
        soup = BeautifulSoup(html_text, 'lxml')
        
        # 1순위: OpenGraph og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title.get("content").strip()
            
        # 2순위: Twitter Title
        twitter_title = soup.find("meta", name="twitter:title")
        if twitter_title and twitter_title.get("content"):
            return twitter_title.get("content").strip()
            
        # 3순위: H1 태그
        h1 = soup.find("h1")
        if h1 and h1.text:
            h1_text = h1.text.strip()
            if len(h1_text) > 3:
                return h1_text
                
        # 4순위: 일반 Title 태그
        if soup.title and soup.title.text:
            return soup.title.text.strip()
            
    except Exception as e:
        print(f"   [크롤링 실패] URL 접속 오류: {e}")
        
    return None

def is_proper_product_name(text):
    """
    상품명이 한글 명사를 포함하는 정상적인 상품명인지 판별합니다.
    """
    if not text:
        return False
    hangul = re.findall(r'[가-힣]', text)
    if len(hangul) == 0:
        return False
    if len(text) <= 5 and not any(noun in text for noun in ["장갑", "가위", "행주", "필름", "퍼티", "테이프"]):
        return False
    return True

def check_model_code_relevance(prod_name_a, scraped_title):
    """
    원본 상품명(A열)의 핵심 모델명이나 고유 숫자 코드가 크롤링한 상품명에 포함되어 있는지 확인합니다.
    """
    if not prod_name_a or not scraped_title:
        return False
        
    model_patterns = re.findall(r'\b[a-zA-Z0-9]+-[a-zA-Z0-9]+\b|\b[a-zA-Z]+[0-9]+[a-zA-Z]*\b|\b[0-9]{3,}\b', prod_name_a)
    
    if not model_patterns:
        return False
        
    scraped_lower = scraped_title.lower()
    for pattern in model_patterns:
        if pattern.lower() in scraped_lower:
            return True
            
    return False

# =========================================================================
# 4. 메인 실행 프로세스
# =========================================================================

def process_excel(input_path, output_path, progress_callback=None):
    print("=" * 60)
    print(f"엑셀 파일 처리 시작: {input_path}")
    print(f"결과 저장 대상 파일: {output_path}")
    print("=" * 60)
    
    if not os.path.exists(input_path):
        print(f"오류: {input_path} 파일이 존재하지 않습니다.")
        return
        
    df = pd.read_excel(input_path)
    
    orig_cols = df.columns.tolist()
    if len(orig_cols) < 2:
        print("오류: 엑셀 파일은 최소 2개 이상의 열(A열: 상품명, B열: URL)을 포함해야 합니다.")
        return
        
    col_a = orig_cols[0]
    col_b = orig_cols[1]
    
    if len(orig_cols) < 3:
        col_c = "정제된 상품명"
        df[col_c] = ""
    else:
        col_c = orig_cols[2]
        
    df[col_c] = df[col_c].fillna("").astype(str)
    total_rows = len(df)
    
    for idx, row in df.iterrows():
        prod_name_a = str(row[col_a]).strip()
        
        print(f"\n[{idx + 1}/{total_rows}] 처리 중...")
        print(f"   - 원본 상품명(A열): {prod_name_a}")
        
        # C열 정제된 상품명의 길이 제한은 모두 삭제하고 A열의 상품명을 직접 분석하여 최적의 상품명으로 정제 및 축약합니다.
        cleaned_result = optimize_product_name(prod_name_a)
        print(f"   -> [최적 상품명 정제] 적용: {cleaned_result}")
            
        df.at[idx, col_c] = cleaned_result
        if progress_callback:
            progress_callback(idx + 1, total_rows)
        time.sleep(0.01)
        
    df.to_excel(output_path, index=False)
    print("\n" + "=" * 60)
    print(f"처리가 완료되었습니다! 신규 파일이 저장되었습니다: {output_path}")
    print("=" * 60)

# =========================================================================
# 5. 웹 서비스 (Flask GUI) 구현부
# =========================================================================

import sys
import threading
import webbrowser
from flask import Flask, render_template_string, jsonify, request
import tempfile
from flask import send_from_directory

app = Flask(__name__)

progress_state = {
    "current": 0,
    "total": 0,
    "percent": 0,
    "logs": [],
    "finished": False,
    "error": None,
    "output_path": ""
}

class WebRedirector:
    def __init__(self):
        self.original_stdout = sys.stdout

    def write(self, string):
        if string.strip():
            progress_state["logs"].append(string.strip())
        try:
            self.original_stdout.write(string)
        except Exception:
            try:
                self.original_stdout.write(string.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))
            except Exception:
                pass

    def flush(self):
        try:
            self.original_stdout.flush()
        except Exception:
            pass

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AI 상품명 초간결 정제 솔루션</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body {
            font-family: 'Inter', 'Malgun Gothic', sans-serif;
            background: #0f0f12;
            color: #e2e2e9;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 80vh;
        }
        .container {
            width: 100%;
            max-width: 800px;
            background: #16161a;
            border: 1px solid #282830;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            background-image: radial-gradient(at top left, rgba(56, 239, 125, 0.03) 0%, transparent 50%),
                              radial-gradient(at bottom right, rgba(17, 153, 142, 0.03) 0%, transparent 50%);
        }
        h1 {
            font-size: 28px;
            font-weight: 700;
            margin-top: 0;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #38ef7d 0%, #11998e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .subtitle {
            color: #8c8c9a;
            font-size: 15px;
            margin-bottom: 30px;
            line-height: 1.6;
        }
        
        /* 탭 스타일 */
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 24px;
            border-bottom: 1px solid #202026;
            padding-bottom: 8px;
        }
        .tab {
            padding: 10px 16px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            color: #8c8c9a;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid transparent;
        }
        .tab:hover {
            color: #e2e2e9;
        }
        .tab.active {
            background: rgba(56, 239, 125, 0.08);
            color: #38ef7d;
            border: 1px solid rgba(56, 239, 125, 0.15);
        }
        
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        
        /* 업로드 구역 */
        .upload-zone {
            border: 2px dashed #282830;
            border-radius: 12px;
            padding: 45px 20px;
            text-align: center;
            background: #09090b;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 24px;
        }
        .upload-zone:hover, .upload-zone.dragover {
            border-color: #38ef7d;
            background: rgba(56, 239, 125, 0.02);
        }
        .upload-icon {
            font-size: 44px;
            margin-bottom: 14px;
            color: #8c8c9a;
        }
        .upload-text {
            font-size: 15px;
            color: #e2e2e9;
            font-weight: 500;
            margin-bottom: 6px;
        }
        .upload-subtext {
            font-size: 12px;
            color: #8c8c9a;
        }
        
        .form-group {
            margin-bottom: 24px;
        }
        label {
            display: block;
            font-size: 13px;
            font-weight: 600;
            color: #a1a1aa;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        input[type="text"] {
            width: 100%;
            padding: 14px 16px;
            background: #09090b;
            border: 1px solid #202026;
            border-radius: 10px;
            color: #f4f4f5;
            font-size: 14px;
            box-sizing: border-box;
            transition: all 0.2s;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: #11998e;
            box-shadow: 0 0 0 2px rgba(17, 153, 142, 0.2);
        }
        .btn {
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: #05140e;
            border: none;
            border-radius: 10px;
            padding: 14px 28px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            width: 100%;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
        }
        .btn:hover {
            opacity: 0.95;
            transform: translateY(-1px);
        }
        .btn:disabled {
            background: #27272a;
            color: #71717a;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-download {
            background: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            color: #050e14;
            font-size: 16px;
            font-weight: 700;
            box-shadow: 0 4px 15px rgba(0, 242, 254, 0.2);
            text-decoration: none;
        }
        .btn-download:hover {
            opacity: 0.95;
            transform: translateY(-1px);
        }
        
        .progress-container {
            margin-top: 35px;
            display: none;
        }
        .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            font-size: 14px;
        }
        .progress-status {
            font-weight: 500;
            color: #38ef7d;
        }
        .progress-bar-bg {
            width: 100%;
            height: 12px;
            background: #202026;
            border-radius: 6px;
            overflow: hidden;
        }
        .progress-bar-fill {
            width: 0%;
            height: 100%;
            background: linear-gradient(90deg, #38ef7d 0%, #11998e 100%);
            border-radius: 6px;
            transition: width 0.3s;
        }
        .terminal-container {
            margin-top: 30px;
            background: #09090b;
            border: 1px solid #202026;
            border-radius: 12px;
            overflow: hidden;
            display: none;
        }
        .terminal-header {
            background: #16161a;
            padding: 10px 16px;
            font-size: 12px;
            color: #8c8c9a;
            border-bottom: 1px solid #202026;
            display: flex;
            align-items: center;
        }
        .terminal-dot { width: 10px; height: 10px; border-radius: 50%; background: #ff5f56; margin-right: 6px; }
        .terminal-dot.yellow { background: #ffbd2e; }
        .terminal-dot.green { background: #27c93f; }
        .terminal-body {
            height: 250px;
            overflow-y: auto;
            padding: 16px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            line-height: 1.6;
            color: #38ef7d;
        }
        .terminal-line {
            margin-bottom: 6px;
            white-space: pre-wrap;
        }
        .success-box {
            background: rgba(56, 239, 125, 0.05);
            border: 1px solid rgba(56, 239, 125, 0.2);
            border-radius: 12px;
            padding: 24px;
            margin-top: 30px;
            text-align: center;
            display: none;
        }
        .success-title {
            color: #38ef7d;
            font-size: 17px;
            font-weight: 600;
            margin-bottom: 12px;
        }
        .success-path {
            font-family: 'Consolas', monospace;
            font-size: 13px;
            color: #a1a1aa;
            margin-bottom: 20px;
        }
        
        #file_input {
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>✨ AI 상품명 초간결 정제 솔루션</h1>
        <div class="subtitle">
            스마트스토어/쿠팡 등록을 위해 불필요한 단어를 제거하고, <strong>한글 기준 9글자 이내</strong> 및 <strong>수량(1p, 20매 등) 보존</strong> 조건에 맞춰 핵심 단어를 지능형으로 축약합니다.
        </div>
        
        <!-- 탭 전환 장치 -->
        <div class="tabs">
            <div class="tab active" onclick="switchTab('upload')">📁 클라우드 간편 정제 (추천)</div>
            <div class="tab" onclick="switchTab('path')">💻 로컬 서버 직접 경로 지정</div>
        </div>

        <!-- 탭 1: 파일 업로드/다운로드 -->
        <div id="tab_upload" class="tab-content active">
            <input type="file" id="file_input" accept=".xlsx, .xls" onchange="handleFileSelect(event)">
            <div class="upload-zone" id="drop_zone" onclick="document.getElementById('file_input').click()">
                <div class="upload-icon">📊</div>
                <div class="upload-text" id="upload_text">여기에 엑셀 파일을 드래그하여 올려놓거나 클릭하여 선택하세요</div>
                <div class="upload-subtext">지원 포맷: .xlsx, .xls (A열: 상품명, B열: URL)</div>
            </div>
            <button id="btn_upload_run" class="btn" onclick="startUploadRun()" disabled>
                <span>선택된 파일 정제 시작</span>
            </button>
        </div>

        <!-- 탭 2: 로컬 직접 경로 기입 -->
        <div id="tab_path" class="tab-content">
            <div class="form-group">
                <label for="input_path">입력 엑셀 파일 경로 (A열: 상품명, B열: URL)</label>
                <input type="text" id="input_path" value="c:\\product\\TEST.xlsx" placeholder="예: C:\\product\\TEST.xlsx">
            </div>

            <div class="form-group">
                <label for="output_path">결과 엑셀 파일 저장 경로 (C열 자동 추가)</label>
                <input type="text" id="output_path" value="c:\\product\\TEST_cleaned.xlsx" placeholder="예: C:\\product\\TEST_cleaned.xlsx">
            </div>

            <button id="btn_path_run" class="btn" onclick="startPathRun()">
                <span>상품명 정제 시작</span>
            </button>
        </div>

        <!-- 진행바 영역 (공통) -->
        <div class="progress-container" id="progress_area">
            <div class="progress-header">
                <span class="progress-status" id="status_text">정제 프로세스 준비 중...</span>
                <span id="percent_text">0%</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="bar_fill"></div>
            </div>
        </div>

        <!-- 터미널 모니터링 영역 (공통) -->
        <div class="terminal-container" id="terminal_area">
            <div class="terminal-header">
                <div class="terminal-dot"></div>
                <div class="terminal-dot yellow"></div>
                <div class="terminal-dot green"></div>
                <span style="margin-left: 8px; font-weight: 500; color: #8c8c9a;">Engine Monitor Logs</span>
            </div>
            <div class="terminal-body" id="terminal_body"></div>
        </div>

        <!-- 최종 완료 및 다운로드 영역 -->
        <div class="success-box" id="success_area">
            <div class="success-title">🎉 모든 상품명 정제가 완료되었습니다!</div>
            <div class="success-path" id="success_path">결과 파일이 성공적으로 보존되었습니다.</div>
            <a href="#" id="btn_download" class="btn btn-download" style="display: none;">📥 정제 완료 엑셀 다운로드</a>
        </div>
    </div>

    <script>
        let intervalId = null;
        let lastLogIndex = 0;
        let selectedFile = null;
        let currentMode = 'upload'; // 'upload' or 'path'
        let downloadFilename = "";

        // 탭 전환 핸들러
        function switchTab(mode) {
            if (intervalId) {
                alert('현재 정제 작업이 진행 중입니다. 완료 후 전환해 주세요.');
                return;
            }
            currentMode = mode;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            if (mode === 'upload') {
                document.querySelector('.tabs .tab:nth-child(1)').classList.add('active');
                document.getElementById('tab_upload').classList.add('active');
            } else {
                document.querySelector('.tabs .tab:nth-child(2)').classList.add('active');
                document.getElementById('tab_path').classList.add('active');
            }
            
            // 공통 컴포넌트 초기화
            document.getElementById('progress_area').style.display = 'none';
            document.getElementById('terminal_area').style.display = 'none';
            document.getElementById('success_area').style.display = 'none';
        }

        // 파일 드래그앤드롭 이벤트 리스너 설정
        const dropZone = document.getElementById('drop_zone');
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            }, false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files.length > 0) {
                setFile(files[0]);
            }
        });

        function handleFileSelect(e) {
            const files = e.target.files;
            if (files.length > 0) {
                setFile(files[0]);
            }
        }

        function setFile(file) {
            if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
                alert('엑셀 파일(.xlsx, .xls)만 업로드할 수 있습니다.');
                return;
            }
            selectedFile = file;
            document.getElementById('upload_text').innerText = `선택된 파일: ${file.name} (${(file.size/1024).toFixed(1)} KB)`;
            document.getElementById('upload_text').style.color = '#38ef7d';
            document.getElementById('btn_upload_run').disabled = false;
        }

        // 방식 1: 파일 업로드 실행
        function startUploadRun() {
            if (!selectedFile) return;

            // UI 셋업
            disableAllControls();
            document.getElementById('progress_area').style.display = 'block';
            document.getElementById('terminal_area').style.display = 'block';
            document.getElementById('success_area').style.display = 'none';
            document.getElementById('btn_download').style.display = 'none';
            document.getElementById('terminal_body').innerHTML = "";
            lastLogIndex = 0;

            const formData = new FormData();
            formData.append('file', selectedFile);

            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    downloadFilename = data.output_filename;
                    intervalId = setInterval(trackProgress, 800);
                } else {
                    alert('오류: ' + data.message);
                    enableAllControls();
                }
            })
            .catch(err => {
                alert('업로드 중 네트워크 오류가 발생했습니다.');
                enableAllControls();
            });
        }

        // 방식 2: 로컬 경로 실행
        function startPathRun() {
            const inPath = document.getElementById('input_path').value.trim();
            const outPath = document.getElementById('output_path').value.trim();

            if (!inPath || !outPath) {
                alert('경로를 모두 기입해 주세요.');
                return;
            }

            disableAllControls();
            document.getElementById('progress_area').style.display = 'block';
            document.getElementById('terminal_area').style.display = 'block';
            document.getElementById('success_area').style.display = 'none';
            document.getElementById('btn_download').style.display = 'none';
            document.getElementById('terminal_body').innerHTML = "";
            lastLogIndex = 0;

            fetch('/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_path: inPath, output_path: outPath })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    downloadFilename = "";
                    intervalId = setInterval(trackProgress, 800);
                } else {
                    alert('에러: ' + data.message);
                    enableAllControls();
                }
            })
            .catch(err => {
                alert('요청 중 네트워크 오류가 발생했습니다.');
                enableAllControls();
            });
        }

        function trackProgress() {
            fetch('/progress')
            .then(res => res.json())
            .then(state => {
                const percent = state.percent || 0;
                const current = state.current || 0;
                const total = state.total || 0;
                
                document.getElementById('bar_fill').style.width = percent + '%';
                document.getElementById('percent_text').innerText = percent + '%';
                document.getElementById('status_text').innerText = `진행률: ${current} / ${total} 개 처리 중...`;

                // 실시간 터미널 로그 추가
                if (state.logs && state.logs.length > lastLogIndex) {
                    const terminal = document.getElementById('terminal_body');
                    for (let i = lastLogIndex; i < state.logs.length; i++) {
                        const line = document.createElement('div');
                        line.className = 'terminal-line';
                        line.innerHTML = escapeHtml(state.logs[i]);
                        terminal.appendChild(line);
                    }
                    lastLogIndex = state.logs.length;
                    terminal.scrollTop = terminal.scrollHeight;
                }

                // 에러 발생 시
                if (state.error) {
                    clearInterval(intervalId);
                    alert('프로세스 도중 오류가 발생했습니다: ' + state.error);
                    enableAllControls();
                    return;
                }

                // 완료 처리
                if (state.finished) {
                    clearInterval(intervalId);
                    intervalId = null;
                    document.getElementById('status_text').innerText = '정제 완료!';
                    
                    if (currentMode === 'upload' && downloadFilename) {
                        document.getElementById('success_path').innerText = '클라우드 정제가 완료되었습니다. 아래 버튼을 눌러 결과 파일을 즉시 다운로드하세요!';
                        document.getElementById('btn_download').href = `/download/${downloadFilename}`;
                        document.getElementById('btn_download').style.display = 'inline-flex';
                    } else {
                        document.getElementById('success_path').innerText = '결과 파일 저장 완료: ' + state.output_path;
                        document.getElementById('btn_download').style.display = 'none';
                    }
                    
                    document.getElementById('success_area').style.display = 'block';
                    enableAllControls();
                }
            });
        }

        function disableAllControls() {
            document.getElementById('btn_upload_run').disabled = true;
            document.getElementById('btn_path_run').disabled = true;
            document.getElementById('btn_upload_run').innerText = "정제 진행 중...";
            document.getElementById('btn_path_run').innerText = "정제 진행 중...";
        }

        function enableAllControls() {
            document.getElementById('btn_upload_run').innerText = "선택된 파일 정제 시작";
            document.getElementById('btn_path_run').innerText = "상품명 정제 시작";
            if (selectedFile) {
                document.getElementById('btn_upload_run').disabled = false;
            }
            document.getElementById('btn_path_run').disabled = false;
        }

        function escapeHtml(unsafe) {
            return unsafe
                 .replace(/&/g, "&amp;")
                 .replace(/</g, "&lt;")
                 .replace(/>/g, "&gt;")
                 .replace(/"/g, "&quot;")
                 .replace(/'/g, "&#039;");
        }
    </script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "업로드된 파일이 없습니다."})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "선택된 파일명이 비어 있습니다."})
        
    if file and file.filename.endswith(('.xlsx', '.xls')):
        temp_dir = tempfile.gettempdir()
        input_filename = "upload_" + str(int(time.time())) + "_" + file.filename
        input_path = os.path.join(temp_dir, input_filename)
        file.save(input_path)
        
        output_filename = "cleaned_" + input_filename
        output_path = os.path.join(temp_dir, output_filename)
        
        progress_state["current"] = 0
        progress_state["total"] = 0
        progress_state["percent"] = 0
        progress_state["logs"] = []
        progress_state["finished"] = False
        progress_state["error"] = None
        progress_state["output_path"] = output_path
        
        def run_thread():
            sys.stdout = WebRedirector()
            try:
                def progress_cb(current, total):
                    progress_state["current"] = current
                    progress_state["total"] = total
                    progress_state["percent"] = int((current / total) * 100)
                    
                process_excel(input_path, output_path, progress_callback=progress_cb)
            except Exception as e:
                progress_state["error"] = str(e)
                print(f"\n[오류 발생] {e}")
            finally:
                sys.stdout = sys.__stdout__
                progress_state["finished"] = True
                
        threading.Thread(target=run_thread, daemon=True).start()
        return jsonify({"status": "started", "output_filename": output_filename})
        
    return jsonify({"status": "error", "message": "엑셀 파일만 업로드할 수 있습니다."})

@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    temp_dir = tempfile.gettempdir()
    return send_from_directory(temp_dir, filename, as_attachment=True)

@app.route('/start', methods=['POST'])
def start_processing():
    data = request.json
    in_path = data.get('input_path')
    out_path = data.get('output_path')
    
    if not in_path or not os.path.exists(in_path):
        return jsonify({"status": "error", "message": "입력 파일이 존재하지 않습니다."})
        
    progress_state["current"] = 0
    progress_state["total"] = 0
    progress_state["percent"] = 0
    progress_state["logs"] = []
    progress_state["finished"] = False
    progress_state["error"] = None
    progress_state["output_path"] = out_path
    
    def run_thread():
        sys.stdout = WebRedirector()
        try:
            def progress_cb(current, total):
                progress_state["current"] = current
                progress_state["total"] = total
                progress_state["percent"] = int((current / total) * 100)
                
            process_excel(in_path, out_path, progress_callback=progress_cb)
        except Exception as e:
            progress_state["error"] = str(e)
            print(f"\n[오류 발생] {e}")
        finally:
            sys.stdout = sys.__stdout__
            progress_state["finished"] = True
            
    threading.Thread(target=run_thread, daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/progress', methods=['GET'])
def get_progress():
    return jsonify(progress_state)

if __name__ == "__main__":
    def open_browser():
        if "RENDER" not in os.environ:
            time.sleep(1.5)
            webbrowser.open("http://127.0.0.1:5000/")

    if "RENDER" not in os.environ:
        threading.Thread(target=open_browser, daemon=True).start()
        app.run(host="127.0.0.1", port=5000, debug=False)
    else:
        # Render.com 배포 환경 지원 (Port 및 Host 동적 매핑)
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
