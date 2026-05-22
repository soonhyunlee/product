import pandas as pd
import os

# 디렉토리 확인 및 생성
os.makedirs("c:\\product", exist_ok=True)

# 샘플 데이터 구성
# 실존하는 비교적 안정적인 페이지들을 예시로 사용하거나, 크롤링 실패 시 fallback을 확인하기 위해 일반 웹사이트 및 깨진 사이트를 포함합니다.
data = [
    {
        "상품명": "[삼성전자] 파워건 무선 청소기 VS20R9043S3 (정품)",
        "URL": "https://raw.githubusercontent.com/tani/mock-api/master/index.html", # Mock HTML
        "정제된 상품명": ""
    },
    {
        "상품명": "LG전자 디오스 오브제컬렉션 냉장고 870L (화이트)",
        "URL": "https://www.wikipedia.org/", # 일반 사이트
        "정제된 상품명": ""
    },
    {
        "상품명": "Apple 2024 맥북에어 13형 M3 (8GB, SSD 256GB)",
        "URL": "https://github.com/", # 일반 사이트
        "정제된 상품명": ""
    },
    {
        "상품명": "[소니] 헤드폰 WH-1000XM5 노이즈캔슬링 (블랙)",
        "URL": "https://invalid-url-test-12345.com/product/123", # 실패 테스트용 잘못된 URL
        "정제된 상품명": ""
    }
]

# DataFrame 생성
df = pd.DataFrame(data)

# 엑셀 파일 저장
file_path = "c:\\product\\TEST.xlsx"
df.to_excel(file_path, index=False)
print(f"샘플 엑셀 파일이 성공적으로 생성되었습니다: {file_path}")
