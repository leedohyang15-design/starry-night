@echo off
chcp 65001 >nul
rem ── Starry Night 원클릭 동기화: 받기 → 내 변경 올리기 ──
cd /d "%~dp0"
echo [1/3] 원격 변경 받는 중...
git pull origin main
if errorlevel 1 (
  echo.
  echo  pull 실패 — 위 메시지를 Claude에게 붙여넣어 주세요.
  pause & exit /b 1
)
echo [2/3] 내 변경 정리 중...
git add -A
git diff --cached --quiet && echo   올릴 변경 없음 — 최신 상태입니다. && pause && exit /b 0
git commit -m "로컬 작업 (%date% %time:~0,5%)"
echo [3/3] 올리는 중...
git push origin main
if errorlevel 1 (
  echo.
  echo  push 실패 — 위 메시지를 Claude에게 붙여넣어 주세요.
  pause & exit /b 1
)
echo.
echo  동기화 완료!
pause
