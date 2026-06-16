import type { Metadata } from "next";
import Link from "next/link";
import { siteConfig } from "@/lib/site";
import { LogoMark } from "./components/Logo";
import LandingHeader from "./components/landing/LandingHeader";
import RedirectIfAuthed from "./components/RedirectIfAuthed";
import { BENEFICIOS_PRO, BENEFICIOS_FREE, PRECO_MENSAL_LABEL } from "@/app/lib/planos";

export const metadata: Metadata = {
  title: { absolute: siteConfig.title },
  description: siteConfig.description,
  alternates: { canonical: "/" },
};

/* ── conteúdo ──────────────────────────────────────────────────────────── */

const STATS = [
  { v: "100k+", l: "questões catalogadas" },
  { v: "Todas", l: "as grandes bancas" },
  { v: "IA", l: "resumos & flashcards" },
  { v: "R$0", l: "para começar" },
];

const BANCAS = [
  "Cebraspe",
  "FGV",
  "FCC",
  "VUNESP",
  "Cesgranrio",
  "IBFC",
  "Quadrix",
  "Instituto AOCP",
  "IADES",
  "FUNDATEC",
];

const FEATURES = [
  {
    icon: "fact_check",
    title: "Banco de questões",
    body: "Resolva questões reais das maiores bancas, com filtros por matéria, banca e assunto — e cadernos pra organizar tudo.",
    big: true,
  },
  {
    icon: "bolt",
    title: "Flashcards inteligentes",
    body: "Repetição espaçada que agenda a revisão na hora certa pra fixar de verdade, sem decoreba.",
  },
  {
    icon: "auto_awesome",
    title: "PDF vira aula com IA",
    body: "Suba o PDF; a IA gera resumo, fórmulas e flashcards automaticamente.",
  },
  {
    icon: "forum",
    title: "Tutor por aula",
    body: "Converse com uma IA que conhece o conteúdo da aula e tira sua dúvida na hora.",
  },
  {
    icon: "menu_book",
    title: "Guias de estudo",
    body: "Importe guias inteiros e estude com ordem, foco e progresso visível.",
  },
  {
    icon: "insights",
    title: "Estatísticas & constância",
    body: "Acompanhe acertos, horas e ofensiva diária pra manter o ritmo até a aprovação.",
  },
];

const STEPS = [
  { n: "01", t: "Crie sua conta grátis", d: "Em segundos, sem cartão de crédito. Você já entra resolvendo questões." },
  { n: "02", t: "Escolha como estudar", d: "Questões por banca, flashcards de revisão ou suba o PDF da sua aula." },
  { n: "03", t: "Deixe a IA acelerar", d: "Resumos, explicações e revisões aparecem no tempo certo pra você render mais." },
];

const PLANS = [
  {
    name: "Grátis",
    price: "R$0",
    period: "para sempre",
    desc: "O suficiente pra criar o hábito e conhecer a plataforma.",
    cta: "Criar conta grátis",
    href: "/cadastro",
    featured: false,
    perks: [...BENEFICIOS_FREE],
  },
  {
    name: "Pro",
    price: PRECO_MENSAL_LABEL,
    period: "/mês",
    desc: "Tudo liberado pra quem está no foco da aprovação.",
    cta: "Assinar o Pro",
    href: "/assinar",
    featured: true,
    perks: [...BENEFICIOS_PRO],
  },
];

const FAQ = [
  {
    q: "Preciso de cartão de crédito pra começar?",
    a: "Não. O plano grátis é de verdade: você cria a conta e já começa a resolver questões, sem cartão.",
  },
  {
    q: "Quais bancas estão disponíveis?",
    a: "As principais bancas de concurso do país — Cebraspe, FGV, FCC, VUNESP, Cesgranrio e outras — com questões filtráveis por matéria e assunto.",
  },
  {
    q: "Como a IA gera os resumos e flashcards?",
    a: "Você sobe o PDF da aula e a IA lê o material inteiro, gera um resumo estruturado, extrai fórmulas e cria flashcards prontos pra revisão.",
  },
  {
    q: "Posso cancelar o Pro quando quiser?",
    a: "Sim. A assinatura é mensal e sem fidelidade — você cancela quando quiser e mantém o acesso até o fim do período pago.",
  },
  {
    q: "Funciona no celular?",
    a: "Funciona. A studIA é responsiva e instalável como app (PWA), então você estuda no computador ou no celular com a mesma conta.",
  },
];

/* ── JSON-LD ───────────────────────────────────────────────────────────── */

function JsonLd() {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": `${siteConfig.url}/#organization`,
        name: siteConfig.name,
        url: siteConfig.url,
        logo: `${siteConfig.url}/studia-mark.svg`,
      },
      {
        "@type": "WebSite",
        "@id": `${siteConfig.url}/#website`,
        url: siteConfig.url,
        name: siteConfig.name,
        description: siteConfig.description,
        inLanguage: "pt-BR",
        publisher: { "@id": `${siteConfig.url}/#organization` },
      },
      {
        "@type": "SoftwareApplication",
        name: siteConfig.name,
        applicationCategory: "EducationalApplication",
        operatingSystem: "Web",
        description: siteConfig.description,
        offers: [
          { "@type": "Offer", price: "0", priceCurrency: "BRL", name: "Grátis" },
          { "@type": "Offer", price: "29.90", priceCurrency: "BRL", name: "Pro" },
        ],
      },
      {
        "@type": "FAQPage",
        mainEntity: FAQ.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      },
    ],
  };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  );
}

/* ── página ────────────────────────────────────────────────────────────── */

export default function Landing() {
  return (
    // `dark` fixo: a landing neon-noir é sempre escura, independe do toggle do app
    <div className="dark lp-bg lp-grain relative min-h-screen w-full overflow-x-clip text-gray-300">
      {/* fontes da landing (escopo local; React 19 hoista o <link> pro <head>) */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      <link
        href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;700&display=swap"
        rel="stylesheet"
      />

      <JsonLd />
      <RedirectIfAuthed />
      <LandingHeader />

      {/* ───────── Hero ───────── */}
      <section className="relative overflow-hidden px-5 pb-20 pt-32 md:pt-40">
        <div className="pointer-events-none absolute inset-0 lp-aurora" aria-hidden />
        <div className="pointer-events-none absolute inset-0 lp-grid" aria-hidden />

        <div className="relative mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="lp-rise">
            <span className="lp-mono inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[0.68rem] uppercase tracking-[0.18em] text-primary">
              <span className="h-1.5 w-1.5 rounded-full bg-primary shadow-[0_0_10px_2px_rgba(6,182,212,0.7)]" />
              Estudos · Inteligência Artificial
            </span>

            <h1 className="lp-display mt-6 text-balance text-5xl leading-[1.02] text-white sm:text-6xl md:text-7xl">
              Estude para concursos como se tivesse um{" "}
              <em className="lp-grad-text font-normal italic">tutor particular</em> de IA.
            </h1>

            <p className="mt-6 max-w-xl text-pretty text-base leading-relaxed text-gray-400 md:text-lg">
              Banco de questões das maiores bancas, flashcards com repetição espaçada e uma IA que
              transforma o PDF da sua aula em resumo, fórmulas e revisões. Tudo num lugar só.
            </p>

            <div className="mt-9 flex flex-col gap-3 sm:flex-row sm:items-center">
              <Link
                href="/cadastro"
                className="group inline-flex items-center justify-center gap-2 rounded-full bg-primary px-6 py-3.5 text-sm font-semibold text-white shadow-[0_14px_40px_-12px_rgba(6,182,212,0.8)] transition-all hover:bg-primary-600"
              >
                Começar grátis
                <span className="material-symbols-outlined text-[20px] transition-transform group-hover:translate-x-0.5">
                  arrow_forward
                </span>
              </Link>
              <a
                href="#recursos"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/[0.02] px-6 py-3.5 text-sm font-semibold text-gray-200 transition-colors hover:border-white/25 hover:bg-white/[0.05]"
              >
                Ver recursos
              </a>
            </div>

            <p className="lp-mono mt-5 text-xs uppercase tracking-wider text-gray-500">
              Sem cartão · Plano grátis para sempre
            </p>
          </div>

          {/* mock de questão flutuante */}
          <div className="lp-rise relative hidden lg:block" style={{ animationDelay: "0.15s" }}>
            <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-gradient-to-br from-primary/20 to-secondary/20 blur-2xl" />
            <div className="lp-card rounded-2xl p-6 backdrop-blur-sm">
              <div className="flex items-center justify-between">
                <span className="lp-mono rounded-md bg-primary/15 px-2 py-1 text-[0.65rem] font-medium uppercase tracking-wider text-primary">
                  Cebraspe · 2024
                </span>
                <span className="lp-mono text-[0.65rem] text-gray-500">Direito Constitucional</span>
              </div>
              <p className="mt-4 text-sm leading-relaxed text-gray-200">
                A respeito dos direitos e garantias fundamentais, julgue o item: a liberdade de
                expressão é um direito absoluto, não admitindo qualquer restrição.
              </p>
              <div className="mt-5 space-y-2">
                {[
                  { k: "C", t: "Certo", ok: false },
                  { k: "E", t: "Errado", ok: true },
                ].map((o) => (
                  <div
                    key={o.k}
                    className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                      o.ok
                        ? "border-accent-success/40 bg-accent-success/10 text-accent-success"
                        : "border-white/8 bg-white/[0.02] text-gray-300"
                    }`}
                  >
                    <span className="lp-mono flex h-6 w-6 items-center justify-center rounded-md border border-white/15 text-xs">
                      {o.k}
                    </span>
                    {o.t}
                    {o.ok && <span className="material-symbols-outlined ml-auto text-[18px]">check_circle</span>}
                  </div>
                ))}
              </div>
              <div className="mt-5 flex items-center gap-2 rounded-lg border border-secondary/30 bg-secondary/10 px-3 py-2.5">
                <span className="material-symbols-outlined text-[20px] text-secondary">auto_awesome</span>
                <span className="text-xs text-gray-300">
                  <span className="font-semibold text-secondary">IA explica:</span> nenhum direito
                  fundamental é absoluto — todos admitem restrição proporcional.
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* faixa de stats */}
        <div className="relative mx-auto mt-20 grid max-w-6xl grid-cols-2 gap-px overflow-hidden rounded-2xl border border-white/8 bg-white/[0.02] md:grid-cols-4">
          {STATS.map((s) => (
            <div key={s.l} className="bg-[#0a0a0c]/40 px-6 py-7 text-center">
              <div className="lp-display cc-num text-4xl text-white md:text-5xl">{s.v}</div>
              <div className="lp-mono mt-1 text-[0.7rem] uppercase tracking-wider text-gray-500">{s.l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ───────── Bancas (marquee) ───────── */}
      <section className="border-y border-white/8 py-7" aria-label="Bancas disponíveis">
        <div className="mx-auto mb-5 max-w-6xl px-5">
          <p className="lp-mono text-center text-[0.7rem] uppercase tracking-[0.2em] text-gray-600">
            Questões das bancas que mais cobram em concurso
          </p>
        </div>
        <div className="relative flex overflow-hidden [mask-image:linear-gradient(90deg,transparent,#000_12%,#000_88%,transparent)]">
          <div className="lp-marquee flex shrink-0 items-center gap-12 pr-12">
            {[...BANCAS, ...BANCAS].map((b, i) => (
              <span key={`${b}-${i}`} className="lp-display whitespace-nowrap text-2xl text-gray-600">
                {b}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── Recursos (bento) ───────── */}
      <section id="recursos" className="scroll-mt-24 px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHead
            eyebrow="O que tem dentro"
            title="Tudo para passar, sem 12 abas abertas"
            sub="Questões, flashcards e IA conversam entre si — você estuda em vez de organizar ferramenta."
          />

          <div className="mt-14 grid gap-4 md:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className={`lp-card group rounded-2xl p-6 ${f.big ? "md:col-span-2" : ""}`}
              >
                <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
                  <span className="material-symbols-outlined text-[24px]">{f.icon}</span>
                </div>
                <h3 className="mt-5 text-lg font-semibold text-white">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-gray-400">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── Como funciona ───────── */}
      <section id="como-funciona" className="scroll-mt-24 px-5 py-24">
        <div className="mx-auto max-w-6xl">
          <SectionHead eyebrow="Como funciona" title="Do zero ao ritmo de estudo em 3 passos" />
          <div className="mt-14 grid gap-px overflow-hidden rounded-2xl border border-white/8 md:grid-cols-3">
            {STEPS.map((s) => (
              <div key={s.n} className="relative bg-white/[0.015] p-8">
                <span className="lp-display lp-grad-text text-6xl">{s.n}</span>
                <h3 className="mt-4 text-xl font-semibold text-white">{s.t}</h3>
                <p className="mt-2 text-sm leading-relaxed text-gray-400">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── Banda de IA ───────── */}
      <section className="px-5 py-12">
        <div className="relative mx-auto max-w-6xl overflow-hidden rounded-3xl border border-white/10 p-10 md:p-14">
          <div className="pointer-events-none absolute inset-0 lp-aurora opacity-80" aria-hidden />
          <div className="relative grid items-center gap-8 md:grid-cols-[1fr_auto]">
            <div>
              <span className="lp-mono text-[0.7rem] uppercase tracking-[0.2em] text-secondary">
                Movido por IA de ponta
              </span>
              <h2 className="lp-display mt-3 text-3xl text-white md:text-5xl">
                A IA faz o trabalho braçal. Você foca em <em className="lp-grad-text italic">aprender</em>.
              </h2>
              <p className="mt-4 max-w-2xl text-sm leading-relaxed text-gray-300 md:text-base">
                Modelos de última geração leem o PDF inteiro da sua aula, escrevem resumos
                estruturados, extraem fórmulas e montam flashcards — enquanto um tutor por chat
                explica cada dúvida com o contexto do material na ponta.
              </p>
              <div className="mt-7 flex flex-wrap gap-2.5">
                {["Resumos automáticos", "Fórmulas extraídas", "Flashcards gerados", "Chat com a aula"].map(
                  (t) => (
                    <span
                      key={t}
                      className="lp-mono rounded-full border border-white/12 bg-white/[0.03] px-3.5 py-1.5 text-xs text-gray-300"
                    >
                      {t}
                    </span>
                  ),
                )}
              </div>
            </div>
            <div className="hidden md:block">
              <LogoMark size={140} className="opacity-90 drop-shadow-[0_12px_40px_rgba(6,182,212,0.45)]" />
            </div>
          </div>
        </div>
      </section>

      {/* ───────── Planos ───────── */}
      <section id="planos" className="scroll-mt-24 px-5 py-24">
        <div className="mx-auto max-w-5xl">
          <SectionHead
            eyebrow="Planos"
            title="Comece de graça. Vire Pro quando quiser."
            sub="Sem fidelidade, sem pegadinha. Cancele a qualquer momento."
          />
          <div className="mt-14 grid gap-5 md:grid-cols-2">
            {PLANS.map((p) => (
              <div
                key={p.name}
                className={`relative rounded-3xl p-8 ${
                  p.featured
                    ? "border border-primary/40 bg-gradient-to-b from-primary/[0.08] to-transparent shadow-[0_30px_80px_-40px_rgba(6,182,212,0.6)]"
                    : "lp-card"
                }`}
              >
                {p.featured && (
                  <span className="lp-mono absolute -top-3 left-8 rounded-full bg-primary px-3 py-1 text-[0.65rem] font-semibold uppercase tracking-wider text-white">
                    Mais popular
                  </span>
                )}
                <h3 className="text-lg font-semibold text-white">{p.name}</h3>
                <p className="mt-1 text-sm text-gray-400">{p.desc}</p>
                <div className="mt-6 flex items-end gap-1">
                  <span className="lp-display text-5xl text-white">{p.price}</span>
                  <span className="lp-mono mb-1.5 text-xs text-gray-500">{p.period}</span>
                </div>
                <ul className="mt-7 space-y-3">
                  {p.perks.map((perk) => (
                    <li key={perk} className="flex items-start gap-2.5 text-sm text-gray-300">
                      <span className="material-symbols-outlined mt-0.5 text-[18px] text-primary">check_circle</span>
                      {perk}
                    </li>
                  ))}
                </ul>
                <Link
                  href={p.href}
                  className={`mt-8 inline-flex w-full items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-semibold transition-all ${
                    p.featured
                      ? "bg-primary text-white shadow-[0_14px_40px_-12px_rgba(6,182,212,0.8)] hover:bg-primary-600"
                      : "border border-white/15 text-gray-100 hover:border-white/30 hover:bg-white/[0.04]"
                  }`}
                >
                  {p.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── FAQ ───────── */}
      <section id="faq" className="scroll-mt-24 px-5 py-24">
        <div className="mx-auto max-w-3xl">
          <SectionHead eyebrow="Dúvidas" title="Perguntas frequentes" />
          <div className="mt-12 divide-y divide-white/8 border-y border-white/8">
            {FAQ.map((f) => (
              <details key={f.q} className="group py-5">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-base font-medium text-white marker:hidden">
                  {f.q}
                  <span className="material-symbols-outlined text-gray-500 transition-transform group-open:rotate-45">
                    add
                  </span>
                </summary>
                <p className="mt-3 text-sm leading-relaxed text-gray-400">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ───────── CTA final ───────── */}
      <section className="px-5 pb-28 pt-8">
        <div className="relative mx-auto max-w-5xl overflow-hidden rounded-3xl border border-white/10 px-6 py-16 text-center">
          <div className="pointer-events-none absolute inset-0 lp-grid" aria-hidden />
          <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary to-transparent" />
          <h2 className="lp-display relative text-4xl text-white md:text-6xl">
            Sua aprovação começa com a{" "}
            <span className="lp-grad-text">próxima questão</span>.
          </h2>
          <p className="relative mx-auto mt-4 max-w-xl text-sm text-gray-400 md:text-base">
            Crie a conta grátis e comece a estudar com IA agora — leva menos de um minuto.
          </p>
          <Link
            href="/cadastro"
            className="group relative mt-9 inline-flex items-center justify-center gap-2 rounded-full bg-primary px-8 py-4 text-sm font-semibold text-white shadow-[0_14px_40px_-12px_rgba(6,182,212,0.8)] transition-all hover:bg-primary-600"
          >
            Criar conta grátis
            <span className="material-symbols-outlined text-[20px] transition-transform group-hover:translate-x-0.5">
              arrow_forward
            </span>
          </Link>
        </div>
      </section>

      {/* ───────── Footer ───────── */}
      <footer className="border-t border-white/8 px-5 py-12">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-8 md:flex-row md:items-start">
          <div className="max-w-xs text-center md:text-left">
            <Link href="/" className="inline-flex items-center">
              <LogoMark size={28} />
              <span className="ml-2.5 text-xl font-bold tracking-tight text-white">
                stud<span className="lp-grad-text">IA</span>
              </span>
            </Link>
            <p className="mt-3 text-sm text-gray-500">
              Estudo inteligente para concursos. Questões, flashcards e IA num lugar só.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-10 text-center sm:grid-cols-3 md:text-left">
            <FooterCol
              title="Produto"
              links={[
                { t: "Recursos", h: "#recursos" },
                { t: "Como funciona", h: "#como-funciona" },
                { t: "Planos", h: "#planos" },
              ]}
            />
            <FooterCol
              title="Conta"
              links={[
                { t: "Entrar", h: "/login" },
                { t: "Criar conta", h: "/cadastro" },
                { t: "Assinar Pro", h: "/assinar" },
              ]}
            />
            <FooterCol title="Ajuda" links={[{ t: "Perguntas frequentes", h: "#faq" }]} />
          </div>
        </div>
        <div className="mx-auto mt-10 max-w-6xl border-t border-white/8 pt-6">
          <p className="lp-mono text-center text-[0.7rem] uppercase tracking-wider text-gray-600">
            © {new Date().getFullYear()} studIA · feito por {siteConfig.author}
          </p>
        </div>
      </footer>
    </div>
  );
}

/* ── helpers ───────────────────────────────────────────────────────────── */

function SectionHead({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="max-w-2xl">
      <span className="lp-mono text-[0.7rem] uppercase tracking-[0.2em] text-primary">{eyebrow}</span>
      <h2 className="lp-display mt-3 text-3xl leading-tight text-white md:text-5xl">{title}</h2>
      {sub && <p className="mt-4 text-sm leading-relaxed text-gray-400 md:text-base">{sub}</p>}
    </div>
  );
}

function FooterCol({ title, links }: { title: string; links: { t: string; h: string }[] }) {
  return (
    <div>
      <p className="lp-mono text-[0.7rem] uppercase tracking-wider text-gray-500">{title}</p>
      <ul className="mt-3 space-y-2.5">
        {links.map((l) => (
          <li key={l.t}>
            <Link href={l.h} className="text-sm text-gray-400 transition-colors hover:text-white">
              {l.t}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
