import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  // servi par le nginx de Faso Données Publiques sous /plan-relance/ : la sortie du build
  // va dans frontend/public/plan-relance (embarquée telle quelle par Vite)
  base: '/plan-relance/',
  plugins: [react()],
  build: { outDir: '../../frontend/public/plan-relance', emptyOutDir: true },
})
