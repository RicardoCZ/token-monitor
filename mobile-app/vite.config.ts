import { defineConfig } from 'vite'

export default defineConfig({
  root: 'src',
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
