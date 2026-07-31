#!/bin/bash
# ============================================
# V0.7.0 → GitHub 推送脚本（在【你本机】跑，别在沙盒跑）
# 用法：
#   1. 把下面 TOKEN= 那行换成你【新生成】的 classic token（只勾 repo）
#   2. chmod +x push_v0.7.0.sh && ./push_v0.7.0.sh
#   3. 跑完立刻去 GitHub 撤销这个 token
# ============================================
set -e

TOKEN="PASTE_YOUR_NEW_CLASSIC_TOKEN_HERE"

if [ "$TOKEN" = "PASTE_YOUR_NEW_CLASSIC_TOKEN_HERE" ]; then
    echo "❌ 先编辑这个文件，把 TOKEN= 换成你新生成的 classic token"
    exit 1
fi

cd "$(dirname "$0")"

# 确保 remote 干净
git remote remove origin 2>/dev/null || true

# 用 token 临时认证
git remote add origin "https://183kugua:${TOKEN}@github.com/183kugua/astrbot_plugin_winremote.git"

echo "🚀 推送中..."
git push -u origin main --force

# 立刻抹掉 token
git remote set-url origin "https://github.com/183kugua/astrbot_plugin_winremote.git"

echo ""
echo "✅ 推送完成！现在去 GitHub 撤销这个 token："
echo "   https://github.com/settings/tokens"
echo ""
echo "🔍 验证：打开 https://github.com/183kugua/astrbot_plugin_winremote"
echo "   应该能看到："
echo "   ✅ astrbot_plugin_winremote.py（入口文件）"
echo "   ✅ metadata.yaml"
echo "   ✅ LICENSE (AGPL-3.0)"
echo "   ✅ .astrbot-plugin/i18n/ 目录（点进去有 4 个文件）"
echo "   ✅ pages/ 三个子目录"
