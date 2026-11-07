import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The desk runs on http://localhost:5173 (the origin the FastAPI backend allows).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
})
