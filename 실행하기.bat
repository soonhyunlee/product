@echo off
title AI 상품명 정제 프로그램 실행기
echo ===================================================
echo   ? AI 상품명 정제 프로그램을 실행하는 중입니다...
echo   (창이 열릴 때까지 잠시만 기다려 주세요)
echo ===================================================
"C:\Program Files\PostgreSQL\18\pgAdmin 4\python\python.exe" "c:\product\excel_cleaner.py"
if %errorlevel% neq 0 (
    echo.
    echo [오류] 프로그램 실행 중 문제가 발생했습니다.
    pause
)
