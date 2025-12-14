import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Allow Docker-based tools (like Playwright MCP) to connect via host.docker.internal
    allowedHosts: ['localhost', 'host.docker.internal'],
  },
})
