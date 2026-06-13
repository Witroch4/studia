"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

// "Já hidratou no cliente?" sem setState-em-efeito. useSyncExternalStore usa o
// server snapshot (false) DURANTE a hidratação e só depois troca para o client
// snapshot (true) — então SSR e 1º render do cliente batem (ambos placeholder),
// eliminando o mismatch que o next-themes causaria (ele resolve o tema de forma
// síncrona no cliente, antes da hidratação).
const emptySubscribe = () => () => {};
function useHydrated() {
	return useSyncExternalStore(
		emptySubscribe,
		() => true,
		() => false,
	);
}

/**
 * Toggle animado sol/lua (mesmo da plataforma WitDev). Usa next-themes.
 * Renderiza um placeholder até hidratar → zero risco de mismatch de hidratação.
 */
export function AnimatedThemeToggle() {
	const { setTheme, resolvedTheme } = useTheme();
	const hydrated = useHydrated();

	if (!hydrated) {
		return <div className="w-12 h-6" />; // Placeholder com tamanho correto
	}

	const isDark = resolvedTheme === "dark";

	const toggleTheme = () => {
		setTheme(isDark ? "light" : "dark");
	};

	return (
		<button
			type="button"
			onClick={toggleTheme}
			className="flex items-center justify-center focus:outline-hidden focus-visible:ring-2 rounded-full focus-visible:ring-primary shrink-0"
			aria-label="Alternar tema"
		>
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 120 60"
				width="48"
				height="24"
				className={`toggle-wrapper ${isDark ? "is-dark" : ""}`}
			>
				<title>{isDark ? "Alternar para tema claro" : "Alternar para tema escuro"}</title>
				<defs>
					<style>
						{`
            /* Background Pill */
            .bg {
              fill: #48b4e0;
              transition: fill 0.6s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }
            .toggle-wrapper.is-dark .bg {
              fill: #1e293b;
            }

            /* Clouds */
            .cloud {
              fill: #ffffff;
              transition: opacity 0.4s ease, transform 0.6s cubic-bezier(0.4, 0, 0.2, 1) !important;
            }
            .cloud-1 { transform: scale(0.85); opacity: 0.9; }
            .cloud-2 { transform: scale(0.55); opacity: 0.6; }

            .toggle-wrapper.is-dark .cloud-1 {
              opacity: 0;
              transform: translateY(15px) scale(0.85);
            }
            .toggle-wrapper.is-dark .cloud-2 {
              opacity: 0;
              transform: translateY(15px) scale(0.55);
            }

            /* Stars */
            .star {
              opacity: 0;
              transition: opacity 0.6s ease, transform 0.6s cubic-bezier(0.4, 0, 0.2, 1) !important;
              transform: translateY(10px) scale(0.5);
            }
            .toggle-wrapper.is-dark .star {
              opacity: 1;
              transform: translateY(0) scale(1);
            }

            /* Star Twinkle */
            .star-glow {
              animation: twinkle 4s infinite alternate;
              transform-origin: center;
            }
            @keyframes twinkle {
              0%, 100% { opacity: 0.4; transform: scale(0.8); }
              50% { opacity: 1; transform: scale(1.1); }
            }

            /* Thumb Group */
            .thumb-group {
              transition: transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
              transform: translateX(0);
            }
            .toggle-wrapper.is-dark .thumb-group {
              transform: translateX(60px);
            }

            /* Glow Ring */
            .glow-ring {
              fill: none;
              stroke: #ffffff;
              stroke-width: 8;
              opacity: 0.2;
              transition: stroke 0.6s ease, opacity 0.6s ease, stroke-width 0.6s ease !important;
            }
            .toggle-wrapper.is-dark .glow-ring {
              stroke: #e2e8f0;
              opacity: 0.1;
              stroke-width: 12;
            }

            /* Main Body */
            .thumb-body {
              fill: #fbbf24;
              transition: fill 0.6s ease !important;
            }
            .toggle-wrapper.is-dark .thumb-body {
              fill: #f8fafc;
            }

            /* Sun Rays */
            .sun-rays {
              stroke: #fbbf24;
              stroke-width: 3.5;
              stroke-linecap: round;
              transition: stroke 0.6s ease, opacity 0.5s ease, transform 0.6s cubic-bezier(0.4, 0, 0.2, 1) !important;
              transform-origin: 30px 30px;
              opacity: 1;
              transform: rotate(0deg) scale(1);
            }
            .toggle-wrapper.is-dark .sun-rays {
              opacity: 0;
              transform: rotate(45deg) scale(0.5);
            }

            /* Craters */
            .crater {
              fill: #cbd5e1;
              opacity: 0;
              transition: opacity 0.5s ease !important;
            }
            .toggle-wrapper.is-dark .crater {
              opacity: 1;
              transition-delay: 0.2s !important;
            }
            `}
					</style>
				</defs>

				{/* Backing Pill */}
				<rect className="bg" width="120" height="60" rx="30" ry="30" />

				{/* Stars (visible in dark mode) */}
				<g className="stars">
					<g transform="translate(32, 16)">
						<g className="star" style={{ transitionDelay: "0s" }}>
							<polygon fill="#fff" className="star-glow" points="0,4 3,3 4,0 5,3 8,4 5,5 4,8 3,5" />
						</g>
					</g>
					<g transform="translate(20, 35)">
						<g className="star" style={{ transitionDelay: "0.1s" }}>
							<circle cx="0" cy="0" r="1.5" fill="#fff" className="star-glow" style={{ animationDelay: "1s" }} />
						</g>
					</g>
					<g transform="translate(48, 42)">
						<g className="star" style={{ transitionDelay: "0.2s" }}>
							<polygon
								fill="#fff"
								className="star-glow"
								points="0,2.5 2,2 2.5,0 3,2 5,2.5 3,3 2.5,5 2,3"
								style={{ animationDelay: "2s" }}
							/>
						</g>
					</g>
					<g transform="translate(56, 18)">
						<g className="star" style={{ transitionDelay: "0.3s" }}>
							<circle cx="0" cy="0" r="1" fill="#fff" className="star-glow" style={{ animationDelay: "1.5s" }} />
						</g>
					</g>
				</g>

				{/* Clouds (visible in light mode) */}
				<g className="clouds">
					<g transform="translate(65, 12)">
						<path
							className="cloud cloud-1"
							d="M15 20 A6 6 0 0 1 27 20 A7 7 0 0 1 39 23 A4.5 4.5 0 0 1 35 30 L10 30 A5 5 0 0 1 15 20 Z"
						/>
					</g>
					<g transform="translate(45, 28)">
						<path
							className="cloud cloud-2"
							d="M15 20 A6 6 0 0 1 27 20 A7 7 0 0 1 39 23 A4.5 4.5 0 0 1 35 30 L10 30 A5 5 0 0 1 15 20 Z"
						/>
					</g>
				</g>

				{/* Inner toggle component */}
				<g className="thumb-group">
					<circle className="glow-ring" cx="30" cy="30" r="21" />

					<g className="sun-rays">
						<line x1="30" y1="2" x2="30" y2="7" />
						<line x1="30" y1="53" x2="30" y2="58" />
						<line x1="2" y1="30" x2="7" y2="30" />
						<line x1="53" y1="30" x2="58" y2="30" />
						<line x1="10.2" y1="10.2" x2="13.7" y2="13.7" />
						<line x1="49.8" y1="49.8" x2="46.3" y2="46.3" />
						<line x1="10.2" y1="49.8" x2="13.7" y2="46.3" />
						<line x1="49.8" y1="10.2" x2="46.3" y2="13.7" />
					</g>

					<circle className="thumb-body" cx="30" cy="30" r="19" />

					<g className="craters">
						<circle className="crater" cx="24" cy="22" r="3.5" />
						<circle className="crater" cx="35" cy="18" r="2" />
						<circle className="crater" cx="37" cy="33" r="5" />
						<circle className="crater" cx="26" cy="40" r="2.5" />
						<circle className="crater" cx="42" cy="26" r="1.5" />
					</g>
				</g>
			</svg>
		</button>
	);
}
