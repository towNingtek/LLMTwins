#!/bin/bash
# 檢查 CORS 配置的使用情況

echo "=== 1. 檢查 server.py 完整的 CORS 設定 ==="
if [ -f "server.py" ]; then
    echo "--- 搜尋 ALLOWED_ORIGINS 和 CORSMiddleware ---"
    grep -n "ALLOWED_ORIGINS\|CORSMiddleware\|allow_origins" server.py
fi

echo -e "\n=== 2. 檢查 config.py 中的 allowed_origins 定義 ==="
if [ -f "app/core/config.py" ]; then
    echo "--- 查看 allowed_origins 及其上下文 ---"
    grep -B 5 -A 5 "allowed_origins" app/core/config.py
fi

echo -e "\n=== 3. 搜尋 settings.allowed_origins 的使用 ==="
grep -rn "settings.allowed_origins\|config.allowed_origins" app/ --include="*.py"

echo -e "\n=== 4. 檢查 server.py 是否使用 settings 物件 ==="
if [ -f "server.py" ]; then
    echo "--- server.py 中關於 settings 的使用 ---"
    grep -n "settings\|load_settings" server.py | head -20
fi

echo -e "\n=== 5. 查看完整的 server.py CORS 區段 ==="
if [ -f "server.py" ]; then
    echo "--- 從 ALLOWED_ORIGINS 到 add_middleware 的完整區段 ---"
    awk '/ALLOWED_ORIGINS/,/add_middleware.*\)/' server.py
fi

echo -e "\n=== 6. 檢查是否有其他地方定義 ALLOWED_ORIGINS ==="
grep -rn "ALLOWED_ORIGINS" . --include="*.py" --exclude-dir=__pycache__

echo -e "\n=== 7. 檢查 config.py 的 Settings 類別結構 ==="
if [ -f "app/core/config.py" ]; then
    echo "--- Settings 類別的 dataclass 定義 ---"
    grep -B 2 "class.*Settings\|@dataclass" app/core/config.py | head -10
fi
