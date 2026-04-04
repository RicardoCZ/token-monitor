import { defineConfig } from 'vite'

export default defineConfig({
  root: 'src',
  /** 与 root 解耦：静态资源放在仓库 mobile-app/public（Capacitor 需 /icons/*.ico） */
  publicDir: '../public',
  build: {
    outDir: '../www',
    emptyOutDir: true,
    target: 'es2018' // 兼容低版本 WebView
  },
  server: {
    host: '0.0.0.0',
    port: 3000
  }
})
