/**
 * Vite 构建配置
 * 配置 React 插件和开发服务器 API 代理
 */
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      /** 将 /api 请求代理到后端服务，解决开发环境跨域问题 */
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
