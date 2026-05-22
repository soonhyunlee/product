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
    
    # 2. 제조사명 제거 (모델명 접두사와 결합된 하이픈 형태는 보호, 예: DAS-B5)
    for m in sorted(MANUFACTURERS, key=len, reverse=True):
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

def refactor_to_concise_name(text):
    """
    정제된 상품명을 6글자 초과할 경우 약 7자 내외로 핵심 특징을 나타내도록 압축합니다.
    """
    if not isinstance(text, str) or not text:
        return ""
    
    text = text.strip()
    
    # 6글자 이하인 경우 압축 불필요
    if len(text) <= 6:
        return text
        
    # 1. 띄어쓰기 결합으로 글자 수 축소 (예: "면 장갑" -> "면장갑")
    compound_words = {
        "면 장갑": "면장갑",
        "황 테이프": "황테이프",
        "스트레치 필름": "스트레치필름",
        "양면 테이프": "양면테이프",
        "방수 스프레이": "방수스프레이",
        "청력 보호구": "청력보호구",
        "접점 부활": "접점부활",
        "에폭시 퍼티": "에폭시퍼티",
        "극세사 행주": "극세사행주",
        "종이 재단기": "종이재단기",
        "레이저 포인터": "레이저포인터",
        "테이프 커터기": "테이프커터기",
        "투명 보호캡": "투명보호캡"
    }
    for k, v in compound_words.items():
        text = text.replace(k, v)
        
    if len(text) <= 7:
        return text

    # 2. 불필요한 서술성 수식어 정밀 제거
    adjectives_to_remove = [
        "대형", "소형", "중형", "고급", "일반", "간편", "안전", "강력", 
        "다용도", "다목적", "어린이용", "가정용", "사무용", "단단한타입", "플러스", "손이편한", "삶아쓰는",
        "19금", "핫멜트", "코팅제", "충진제"
    ]
    for adj in adjectives_to_remove:
        text = text.replace(adj, "").strip()
        
    # 다중 공백 제거
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) <= 8:
        return text

    # 3. 핵심 단어 축약어 및 명사 대체 사전 (7자 최적화)
    synonyms = {
        "화지양면테이프": "양면테이프",
        "양면테이프 9346": "양면테이프",
        "PE 보호 테이프": "PE테이프",
        "PE보호테이프": "PE테이프",
        "스트레치필름": "필름",
        "레이저포인터": "포인터",
        "테이프클리너": "클리너",
        "청력보호구": "",
        "귀덮개": "귀덮개",
        "종이재단기": "재단기",
        "투명보호캡": "보호캡",
        "마루지킴이": "",
        "마루 지킴이": "",
        "접점부활세정제": "접점세정제",
        "접점 부활 세정제": "접점세정제",
        "접점부활 세정제": "접점세정제",
        "어린이용 양손가위": "양손가위",
        "양손가위": "양손가위",
        "화일인덱스용": "인덱스용",
        "물류관리용": "물류용",
        "분류표기용": "분류용",
        "타이어 광택": "타이어광택제",
        "타이어광택": "타이어광택제",
        "틈새 메꾸미": "틈새메꾸미",
        "틈새메꾸미": "틈새메꾸미"
    }
    for k, v in synonyms.items():
        text = text.replace(k, v)
        
    # 다중 공백 및 무의미한 남은 수식어 기호 정리
    text = text.replace("헤드폰형", "").replace("돌돌이", "")
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 4. 규격 및 수량 축약 (예: "25mm x 10M" -> "25mm", "2개입" -> "2개")
    text = text.replace("개입", "개").replace("매입", "매")
    text = re.sub(r'x\s*\d+[a-zA-Z가-힣]+\s*x\s*\d+[a-zA-Z가-힣]+', '', text)
    text = re.sub(r'x\s*\d+[a-zA-Z가-힣]+', '', text)
    text = text.replace("사이즈", "").replace("리필", "리필")
    
    # 모델명 하이픈 뒤의 잉여 공백 제거
    text = re.sub(r'\s*-\s*', '-', text)
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def clean_scraped_title(scraped_title):
    """
    웹 페이지 크롤링 시 포함되는 사이트명 등의 공통 접미사를 필터링합니다.
    예: '삼성 파워건 VS20R9043S3 : 네이버 쇼핑' -> '삼성 파워건 VS20R9043S3'
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
    두 문자열 간의 핵심 단어 오버랩(유사도)을 계산합니다. (Jaccard 유사도 기반)
    크롤링한 페이지가 엉뚱한 페이지거나 차단 페이지인지 확인하는 용도로 사용됩니다.
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
        # 5초 타임아웃 지정 및 SSL 검증 생략
        response = requests.get(url, headers=headers, timeout=5, verify=False)
        if response.status_code != 200:
            print(f"   [크롤링 경고] HTTP 상태 코드 {response.status_code}")
            return None
        
        # HTML 바이트를 먼저 디코딩하여 문자열로 변환 (BeautifulSoup의 오독 방지)
        html_text = None
        apparent = response.apparent_encoding
        if apparent and 'ptcp' not in apparent.lower(): # ptcp(Cyrillic) 오감지 회피
            try:
                html_text = response.content.decode(apparent, errors='replace')
            except Exception:
                pass
                
        # apparent_encoding 실패 혹은 ptcp인 경우 utf-8 및 euc-kr/cp949 순차 시도
        if not html_text:
            for encoding in ['utf-8', 'euc-kr', 'cp949']:
                try:
                    html_text = response.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
                    
        if not html_text:
            html_text = response.content.decode('utf-8', errors='replace')
            
        soup = BeautifulSoup(html_text, 'lxml')
        
        # 1순위: OpenGraph og:title (가장 정제된 경우가 많음)
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title.get("content").strip()
            
        # 2순위: Twitter Title
        twitter_title = soup.find("meta", name="twitter:title")
        if twitter_title and twitter_title.get("content"):
            return twitter_title.get("content").strip()
            
        # 3순위: H1 태그 (보통 상세페이지의 주 상품명)
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
    한글이 아예 없거나, 너무 짧고 코드 형태인 경우 '마땅한 상품명이 아님'으로 판단합니다.
    """
    if not text:
        return False
    # 한글 문자 추출
    hangul = re.findall(r'[가-힣]', text)
    if len(hangul) == 0:
        return False # 한글이 한 글자도 없으면 정상적인 한글 상품명이 아님 (모델코드 등)
    if len(text) <= 5 and not any(noun in text for noun in ["장갑", "가위", "행주", "필름", "퍼티", "테이프"]):
        return False # 5자 이하이고 대표 명사가 없으면 불안정한 상품명
    return True

def check_model_code_relevance(prod_name_a, scraped_title):
    """
    원본 상품명(A열)의 핵심 모델명이나 고유 숫자 코드가 크롤링한 상품명에 포함되어 있는지 확인합니다.
    이를 통해 70~80% 이상의 실제 상품 연관성이 확보되는 경우 참을 반환합니다.
    """
    if not prod_name_a or not scraped_title:
        return False
        
    # 모델명 패턴 추출 (예: LP-7000, H10A, G-250, ECC, 9346 등 3자리 이상 숫자 및 영숫자 조합)
    model_patterns = re.findall(r'\b[a-zA-Z0-9]+-[a-zA-Z0-9]+\b|\b[a-zA-Z]+[0-9]+[a-zA-Z]*\b|\b[0-9]{3,}\b', prod_name_a)
    
    if not model_patterns:
        return False
        
    scraped_lower = scraped_title.lower()
    for pattern in model_patterns:
        if pattern.lower() in scraped_lower:
            return True # 핵심 모델 코드가 일치하면 70-80% 이상 유사/동일한 상품으로 판정
            
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
        
    # 엑셀 데이터 로드
    df = pd.read_excel(input_path)
    
    # 컬럼 인덱스 매핑 (A열: 0번째, B열: 1번째, C열: 2번째)
    # 컬럼명이 한글이나 영어 어떤 것으로 되어있어도 처리할 수 있도록 위치 기반으로 설정
    orig_cols = df.columns.tolist()
    if len(orig_cols) < 2:
        print("오류: 엑셀 파일은 최소 2개 이상의 열(A열: 상품명, B열: URL)을 포함해야 합니다.")
        return
        
    col_a = orig_cols[0] # A열 (상품명)
    col_b = orig_cols[1] # B열 (URL)
    
    # C열이 없으면 추가 생성
    if len(orig_cols) < 3:
        col_c = "정제된 상품명"
        df[col_c] = ""
    else:
        col_c = orig_cols[2] # C열 (정제 상품명)
        
    # 데이터 타입 변환 (TypeError 방지 및 NaN 처리)
    df[col_c] = df[col_c].fillna("").astype(str)
        
    total_rows = len(df)
    
    for idx, row in df.iterrows():
        prod_name_a = str(row[col_a]).strip()
        url = str(row[col_b]).strip()
        
        print(f"\n[{idx + 1}/{total_rows}] 처리 중...")
        print(f"   - 원본 상품명(A열): {prod_name_a}")
        
        cleaned_result = ""
        scraped_title = None
        
        # 상품명이 7자 이하인 경우 리팩토링 건너뜀 (원본 그대로 보존)
        if len(prod_name_a) <= 7:
            print("   [건너뜀] 상품명이 7자 이하이므로 정제 처리를 건너뛰고 그대로 보존합니다.")
            cleaned_result = prod_name_a
        else:
            # URL이 올바르고 접속 가능한 경우 크롤링 시도
            if url.startswith("http"):
                print(f"   - URL 접속 시도: {url}")
                raw_title = scrape_product_title(url)
                if raw_title:
                    scraped_title = clean_scraped_title(raw_title)
                    print(f"   - 크롤링 성공 상품명: {scraped_title}")
                    
            # 크롤링 성공 시, 원본명과 비교하여 검증
            if scraped_title:
                similarity = calculate_overlap(prod_name_a, scraped_title)
                is_proper_a = is_proper_product_name(prod_name_a)
                has_model_match = check_model_code_relevance(prod_name_a, scraped_title)
                
                print(f"   - 원본 상품명과의 유사도 검증: {similarity:.2f}")
                print(f"   - 원본명 신뢰도 판별: {'정상 한글 상품명' if is_proper_a else '불안정한 상품명(모델코드/기호 중심)'}")
                print(f"   - 핵심 모델/규격 코드 일치 검사: {'일치함' if has_model_match else '일치하지 않음'}")
                
                # A열이 불안정하더라도 모델 코드가 일치하는 경우(70~80% 유사성 확보) 혹은 기본 단어 유사도가 15% 이상인 경우 적용
                if similarity >= 0.15 or (not is_proper_a and has_model_match) or has_model_match:
                    if not is_proper_a and has_model_match:
                        print("   => [유사성 우회 보정] A열이 미비하지만 핵심 모델코드가 일치하여 크롤링 상품명을 70~80% 유사 상품명으로 채택합니다.")
                    cleaned_result = clean_product_name(scraped_title)
                    print(f"   -> [크롤링 데이터 정제] 적용: {cleaned_result}")
                else:
                    # 크롤링한 타이틀이 완전히 다른 경우 (메인 페이지로 튕겼거나, 차단당해 다른 화면이 뜬 경우)
                    print("   [검증 불합격] 크롤링한 상품명이 원본과 일치하지 않아 원본(A열) 기반으로 정제합니다.")
                    cleaned_result = clean_product_name(prod_name_a)
                    print(f"   -> [원본 데이터 정제(Fallback)] 적용: {cleaned_result}")
            else:
                # 크롤링을 아예 하지 못했거나 실패한 경우 원본을 정제하여 사용 (Fallback)
                print("   [접속 불가능] 원본(A열)을 기반으로 정제 처리를 진행합니다.")
                cleaned_result = clean_product_name(prod_name_a)
                print(f"   -> [원본 데이터 정제(Fallback)] 적용: {cleaned_result}")
            
        # 정제 결과명이 6글자를 초과하는 경우 7자 내외로 상품특징 최적화 압축 진행
        if len(cleaned_result) > 6:
            concise_result = refactor_to_concise_name(cleaned_result)
            print(f"   => [7자 최적화 압축 적용]: {cleaned_result} -> {concise_result} (길이: {len(concise_result)}자)")
            cleaned_result = concise_result
            
        # 결과값 기입
        df.at[idx, col_c] = cleaned_result
        if progress_callback:
            progress_callback(idx + 1, total_rows)
        time.sleep(0.5) # 웹서버 부하 경감 및 차단 방지를 위한 대기
        
    # 파일 저장
    df.to_excel(output_path, index=False)
    print("\n" + "=" * 60)
    print(f"처리가 완료되었습니다! 신규 파일이 저장되었습니다: {output_path}")
    print("=" * 60)

if __name__ == "__main__":
    import threading
    import time
    import webbrowser
    from flask import Flask, render_template_string, jsonify, request

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
            self.original_stdout.write(string)

        def flush(self):
            self.original_stdout.flush()

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
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }
        .header {
            margin-bottom: 25px;
            border-bottom: 1px solid #282830;
            padding-bottom: 20px;
        }
        .header h1 {
            font-size: 24px;
            font-weight: 700;
            color: #00F2FE;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header p {
            color: #8c8c9a;
            font-size: 14px;
            margin: 8px 0 0 0;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: #e2e2e9;
            margin-bottom: 8px;
        }
        .input-group {
            display: flex;
            gap: 10px;
        }
        .input-group input {
            flex: 1;
            background: #0f0f12;
            border: 1px solid #282830;
            color: #e2e2e9;
            padding: 12px 16px;
            border-radius: 8px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }
        .input-group input:focus {
            border-color: #00F2FE;
        }
        .btn {
            background: #2563eb;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }
        .btn:hover {
            background: #1d4ed8;
        }
        .btn:active {
            transform: scale(0.98);
        }
        .btn-large {
            width: 100%;
            padding: 15px;
            font-size: 16px;
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: #0f0f12;
            font-weight: 700;
            box-shadow: 0 4px 15px rgba(0, 242, 254, 0.2);
            margin-top: 10px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }
        .btn-large:hover {
            opacity: 0.9;
        }
        .btn-disabled {
            background: #2c2c35 !important;
            color: #5c5c6a !important;
            cursor: not-allowed;
            box-shadow: none !important;
            opacity: 0.7 !important;
        }
        .progress-container {
            margin-top: 30px;
            display: none;
        }
        .progress-header {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            margin-bottom: 8px;
        }
        .progress-bar-bg {
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
            gap: 8px;
        }
        .terminal-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #ff5f56;
        }
        .terminal-dot.yellow { background: #ffbd2e; }
        .terminal-dot.green { background: #27c93f; }
        .terminal-body {
            height: 250px;
            overflow-y: auto;
            padding: 16px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
            line-height: 1.6;
            color: #8af294;
        }
        .terminal-line {
            margin-bottom: 6px;
            white-space: pre-wrap;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚡ AI PRODUCT NAME REFACTORER</h1>
            <p>상세페이지 크롤링 분석 및 상품명 7자 초간결 최적화 정제 솔루션 (Web Interface)</p>
        </div>
        
        <div class="form-group">
            <label>입력 엑셀 파일 경로</label>
            <div class="input-group">
                <input type="text" id="input_path" value="c:\\product\\TEST.xlsx" placeholder="예: c:\\product\\TEST.xlsx">
            </div>
        </div>

        <div class="form-group">
            <label>정제 후 저장할 신규 파일명 경로</label>
            <div class="input-group">
                <input type="text" id="output_path" value="c:\\product\\TEST_cleaned.xlsx" placeholder="예: c:\\product\\TEST_cleaned.xlsx">
            </div>
        </div>

        <button class="btn btn-large" id="btn_run" onclick="startProcessing()">상품명 정제 시작</button>

        <div class="progress-container" id="progress_section">
            <div class="progress-header">
                <span id="status_text">대기 중...</span>
                <span id="percent_text">0%</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="progress_fill"></div>
            </div>
        </div>

        <div class="terminal-container" id="terminal_section">
            <div class="terminal-header">
                <div class="terminal-dot"></div>
                <div class="terminal-dot yellow"></div>
                <div class="terminal-dot green"></div>
                <span>실시간 정제 모니터링 로그</span>
            </div>
            <div class="terminal-body" id="terminal_body"></div>
        </div>
    </div>

    <script>
        let intervalId = null;

        function startProcessing() {
            const inputPath = document.getElementById('input_path').value.trim();
            const outputPath = document.getElementById('output_path').value.trim();

            if (!inputPath || !outputPath) {
                alert('파일 경로를 올바르게 입력해 주세요.');
                return;
            }

            // UI 상태 변경
            const btn = document.getElementById('btn_run');
            btn.className = "btn btn-large btn-disabled";
            btn.disabled = true;
            btn.innerText = "정제 처리 진행 중...";

            document.getElementById('progress_section').style.display = 'block';
            document.getElementById('terminal_section').style.display = 'block';
            document.getElementById('terminal_body').innerHTML = '';

            fetch('/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ input_path: inputPath, output_path: outputPath })
            })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'started') {
                    // 폴링 시작
                    intervalId = setInterval(checkProgress, 1000);
                } else {
                    alert('처리를 시작하지 못했습니다: ' + data.message);
                    resetUI();
                }
            })
            .catch(err => {
                alert('서버와의 통신 오류: ' + err);
                resetUI();
            });
        }

        function checkProgress() {
            fetch('/progress')
            .then(res => res.json())
            .then(data => {
                // 프로그레스 바 및 텍스트 업데이트
                document.getElementById('percent_text').innerText = data.percent + '%';
                document.getElementById('progress_fill').style.width = data.percent + '%';
                
                if (data.total > 0) {
                    document.getElementById('status_text').innerText = `정제 진행 중: ${data.percent}% (${data.current} / ${data.total} 완료)`;
                } else {
                    document.getElementById('status_text').innerText = '상세페이지 스캔 시작 대기 중...';
                }

                // 로그 업데이트
                const term = document.getElementById('terminal_body');
                let newHtml = '';
                data.logs.forEach(log => {
                    newHtml += `<div class="terminal-line">${escapeHtml(log)}</div>`;
                });
                term.innerHTML = newHtml;
                term.scrollTop = term.scrollHeight;

                if (data.finished) {
                    clearInterval(intervalId);
                    document.getElementById('status_text').innerText = '모든 작업이 성공적으로 완료되었습니다!';
                    document.getElementById('status_text').style.color = '#38ef7d';
                    
                    if (data.error) {
                        alert('작업 중 오류가 발생했습니다:\\n' + data.error);
                    } else {
                        alert('처리가 완료되었습니다!\\n결과 파일: ' + data.output_path);
                    }
                    resetUI();
                }
            });
        }

        function resetUI() {
            const btn = document.getElementById('btn_run');
            btn.className = "btn btn-large";
            btn.disabled = false;
            btn.innerText = "상품명 정제 시작";
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

    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:5000/")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
