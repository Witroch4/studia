import confetti from "canvas-confetti";

/**
 * Comemoração visual de "virou PRO": rajada inicial + dois jatos laterais que
 * desenham um arco, nas cores da marca (cyan + violeta). Seguro p/ SSR — só
 * roda no cliente (canvas-confetti depende de window).
 */
export function celebrarPro() {
  if (typeof window === "undefined") return;

  const cores = ["#06b6d4", "#8b5cf6", "#22d3ee", "#a78bfa", "#ffffff"];

  // Estouro central imediato.
  confetti({
    particleCount: 140,
    spread: 90,
    startVelocity: 45,
    origin: { y: 0.6 },
    colors: cores,
    zIndex: 9999,
  });

  // Jatos laterais por ~1.2s, formando um leque dos cantos inferiores.
  const fim = Date.now() + 1200;
  (function jato() {
    confetti({ particleCount: 6, angle: 60, spread: 70, origin: { x: 0, y: 0.7 }, colors: cores, zIndex: 9999 });
    confetti({ particleCount: 6, angle: 120, spread: 70, origin: { x: 1, y: 0.7 }, colors: cores, zIndex: 9999 });
    if (Date.now() < fim) requestAnimationFrame(jato);
  })();
}

/**
 * Comemoração de "meta diária batida" (15 questões/dia, PRO): chuva contínua de
 * confetes caindo do topo por ~2.5s — efeito distinto do leque lateral do
 * celebrarPro() (assinatura). Seguro p/ SSR (canvas-confetti depende de window).
 */
export function celebrarMetaDiaria() {
  if (typeof window === "undefined") return;

  const cores = ["#06b6d4", "#8b5cf6", "#22d3ee", "#a78bfa", "#ffffff"];
  const fim = Date.now() + 2500;

  (function chuva() {
    confetti({
      particleCount: 4,
      startVelocity: 0,
      ticks: 200,
      gravity: 0.6,
      spread: 80,
      origin: { x: Math.random(), y: -0.1 },
      colors: cores,
      zIndex: 9999,
    });
    if (Date.now() < fim) requestAnimationFrame(chuva);
  })();
}
