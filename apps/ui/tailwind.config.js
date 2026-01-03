export default {
    darkMode: 'class',
    content: ['./src/**/*.{html,js,svelte,ts}'],
    theme: {
        extend: {
            colors: {
                // Custom brand colors - nature-inspired teal/green
                brand: {
                    50: '#f0fdfa',
                    100: '#ccfbf1',
                    200: '#99f6e4',
                    300: '#5eead4',
                    400: '#2dd4bf',
                    500: '#14b8a6',
                    600: '#0d9488',
                    700: '#0f766e',
                    800: '#115e59',
                    900: '#134e4a',
                    950: '#042f2e',
                },
                // Nature-inspired background colors
                surface: {
                    light: '#f1f5f4', // Light sage gray for better contrast
                    dark: '#020617',
                },
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'fade-in': 'fadeIn 0.3s ease-out',
                'slide-up': 'slideUp 0.3s ease-out',
                'shimmer': 'shimmer 1.5s infinite',
                'gradient-shift': 'gradientShift 3s ease infinite',
                'glow-pulse': 'glowPulse 2s ease-in-out infinite',
                'count-up': 'countUp 0.6s ease-out forwards',
                'float': 'float 3s ease-in-out infinite',
            },
            keyframes: {
                fadeIn: {
                    '0%': { opacity: '0' },
                    '100%': { opacity: '1' },
                },
                slideUp: {
                    '0%': { opacity: '0', transform: 'translateY(10px)' },
                    '100%': { opacity: '1', transform: 'translateY(0)' },
                },
                shimmer: {
                    '0%': { backgroundPosition: '-200% 0' },
                    '100%': { backgroundPosition: '200% 0' },
                },
                gradientShift: {
                    '0%, 100%': { backgroundPosition: '0% 50%' },
                    '50%': { backgroundPosition: '100% 50%' },
                },
                glowPulse: {
                    '0%, 100%': { boxShadow: '0 0 20px rgba(20, 184, 166, 0.2)' },
                    '50%': { boxShadow: '0 0 40px rgba(20, 184, 166, 0.4)' },
                },
                countUp: {
                    '0%': { opacity: '0', transform: 'translateY(10px) scale(0.9)' },
                    '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
                },
                float: {
                    '0%, 100%': { transform: 'translateY(0)' },
                    '50%': { transform: 'translateY(-5px)' },
                },
            },
            boxShadow: {
                'glow': '0 0 20px rgba(20, 184, 166, 0.3)',
                'glow-lg': '0 0 30px rgba(20, 184, 166, 0.4)',
                'card': '0 1px 3px rgba(0, 0, 0, 0.05), 0 1px 2px rgba(0, 0, 0, 0.1)',
                'card-hover': '0 10px 40px rgba(0, 0, 0, 0.12), 0 4px 12px rgba(0, 0, 0, 0.08)',
                'card-dark': '0 1px 3px rgba(0, 0, 0, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2)',
                'card-dark-hover': '0 10px 40px rgba(0, 0, 0, 0.4), 0 4px 12px rgba(0, 0, 0, 0.3)',
            },
            backgroundImage: {
                'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
                'noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)' opacity='0.05'/%3E%3C/svg%3E\")",
                'gradient-mesh': 'radial-gradient(at 40% 20%, hsla(174, 84%, 45%, 0.12) 0px, transparent 50%), radial-gradient(at 80% 0%, hsla(189, 100%, 56%, 0.08) 0px, transparent 50%), radial-gradient(at 0% 50%, hsla(168, 76%, 46%, 0.08) 0px, transparent 50%)',
                'gradient-shine': 'linear-gradient(135deg, rgba(255,255,255,0.1) 0%, transparent 50%, rgba(255,255,255,0.05) 100%)',
            },
        },
    },
    plugins: [],
}
