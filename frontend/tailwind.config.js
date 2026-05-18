/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Microsoft YaHei UI', 'Microsoft YaHei', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'ui-monospace', 'monospace']
      },
      boxShadow: {
        soft: '0 24px 70px rgba(15, 23, 42, 0.08)',
        lift: '0 16px 44px rgba(20, 83, 45, 0.12)'
      }
    }
  },
  plugins: []
}
