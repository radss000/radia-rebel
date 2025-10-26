/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      // Colors inspired by CoStar - more muted and professional
      colors: {
        costar: {
          // Main colors based on CoStar's actual palette
          'deep-blue': '#0b1724',     // Background
          'dark': '#111827',          // Dark cards
          'darker': '#0f0f0f',       
          'gray-dark': '#1f2937',     // Cards
          'gray-medium': '#374151',   
          'gray-light': '#6b7280',   
          'text-light': '#e5e7eb',    // Main text
          'text-muted': '#9ca3af',    // Muted text
          'card': '#1f2937',          // Card background
          'border': '#374151',        // Border color
        }
      },
      // Typography more refined like CoStar
      fontFamily: {
        'sans': ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', '"Noto Sans"', 'sans-serif'],
        'inter': ['Inter', 'sans-serif'],
      },
      // Smaller, more refined font sizes
      fontSize: {
        'xs': ['11px', { lineHeight: '16px' }],
        'sm': ['12px', { lineHeight: '18px' }],
        'base': ['14px', { lineHeight: '20px' }],
        'lg': ['16px', { lineHeight: '24px' }],
        'xl': ['18px', { lineHeight: '28px' }],
        '2xl': ['20px', { lineHeight: '28px' }],
        '3xl': ['24px', { lineHeight: '32px' }],
        '4xl': ['30px', { lineHeight: '36px' }],
      },
      // Refined spacing
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      // Subtle border radius like CoStar
      borderRadius: {
        'lg': '8px',
        'xl': '12px',
        '2xl': '16px',
      },
      // Subtle shadows
      boxShadow: {
        'costar': '0 1px 3px rgba(0, 0, 0, 0.1), 0 1px 2px rgba(0, 0, 0, 0.06)',
        'costar-lg': '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
      },
      // Smooth animations
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-up': 'slideUp 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        }
      }
    },
  },
  plugins: [],
}