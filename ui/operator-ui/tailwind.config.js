/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: '#4F46E5',  // indigo-600
        secondary: '#10B981', // emerald-500
        dark: '#1F2937',
      },
    },
  },
  plugins: [],
}
