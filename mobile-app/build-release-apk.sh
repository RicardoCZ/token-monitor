#!/usr/bin/env bash
# 生产 release APK：构建 Web → Capacitor 同步 → Gradle 打包 → 移动到仓库根目录 android-apk/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

DEST_DIR="${ROOT}/../android-apk"
DEST_APK="${DEST_DIR}/token-monitor-release.apk"
APK_SRC="${ROOT}/android/app/build/outputs/apk/release/app-release.apk"

echo "==> npm run build"
npm run build

echo "==> npx cap sync android"
npx cap sync android

echo "==> ./gradlew assembleRelease"
(cd "${ROOT}/android" && ./gradlew assembleRelease)

if [[ ! -f "$APK_SRC" ]]; then
  echo "ERROR: 未找到打包产物: $APK_SRC" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
mv -f "$APK_SRC" "$DEST_APK"

echo "==> 已移动到: $DEST_APK"
ls -la "$DEST_APK"
