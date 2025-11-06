#!/bin/bash
# install_tessdata.sh
# 一鍵安裝 Tesseract 常用語料 (繁體/簡體/英文/直排/OSD)

set -e

TESSDATA_DIR="/usr/share/tesseract-ocr/5/tessdata"

# 確保資料夾存在
sudo mkdir -p "$TESSDATA_DIR"

# 要安裝的語料列表
LANGS=(
  eng.traineddata
  osd.traineddata
  chi_sim.traineddata
  chi_tra.traineddata
  chi_tra_vert.traineddata
)

BASE_URL="https://github.com/tesseract-ocr/tessdata_best/raw/main"

echo "📥 正在下載 Tesseract 語料到 $TESSDATA_DIR ..."

for lang in "${LANGS[@]}"; do
  if [ ! -f "$TESSDATA_DIR/$lang" ]; then
    echo "  → 安裝 $lang"
    sudo wget -q -O "$TESSDATA_DIR/$lang" "$BASE_URL/$lang"
  else
    echo "  ✔ 已存在 $lang"
  fi
done

echo "✅ 語料安裝完成，現在可用語言："
tesseract --list-langs

