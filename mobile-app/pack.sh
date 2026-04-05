#!/usr/bin/env bash
# Debug APK：vite build → cap sync → assembleDebug
set -euo pipefail
cd "$(dirname "$0")"

# 确保依赖已安装（新环境首次执行需要）
npm install

npm run build
npx cap sync android
(cd android && ./gradlew :app:assembleDebug -q)
APK="$(pwd)/android/app/build/outputs/apk/debug/app-debug.apk"
ls -la "$APK"
echo "APK: $APK"
