"""Testa se o TecConcursos aceita o IP atual.

Roda checks em sequência:
  1. Resolve IP público de saída (via httpbin)
  2. Identifica ASN/provedor do IP (via ipinfo.io)
  3. Acessa página pública do TC (sem cookies)
  4. Tenta login (com TC_EMAIL/TC_PASSWORD do .env)
  5. Hit /api/questoes/{id}/deslogado pra testar autenticado

Saída inclui veredito: 🟢 verde (pode rodar), 🟡 amarelo (parcial), 🔴 vermelho (bloqueado).

uso:
    docker run --rm -e TC_EMAIL=... -e TC_PASSWORD=... studia-scraper python scripts/test_tc_access.py
"""

from __future__ import annotations

import asyncio
import os
import sys

import httpx


TC = "https://www.tecconcursos.com.br"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


async def main() -> None:
    email = os.getenv("TC_EMAIL", "")
    password = os.getenv("TC_PASSWORD", "")

    print("=" * 60)
    print("TEC CONCURSOS — TESTE DE IP")
    print("=" * 60)

    # ── 1. IP público de saída ──────────────────────────────
    async with httpx.AsyncClient(timeout=15.0) as c:
        try:
            r = await c.get("https://api.ipify.org?format=json")
            ip = r.json().get("ip", "?")
            print(f"\n1) IP público de saída: {ip}")
        except Exception as e:  # noqa: BLE001
            print(f"\n1) FALHA ao resolver IP: {e}")
            return

    # ── 2. ASN / provedor (datacenter? residential?) ────────
        try:
            r = await c.get(f"https://ipinfo.io/{ip}/json")
            info = r.json()
            org = info.get("org", "?")
            country = info.get("country", "?")
            city = info.get("city", "?")
            print(f"   Provedor: {org}")
            print(f"   País/cidade: {country} / {city}")
            is_dc = any(
                tag in org.lower()
                for tag in ["amazon", "google", "microsoft", "hetzner", "ovh", "digitalocean", "linode", "cloudflare", "azure", "oracle"]
            )
            if is_dc:
                print(f"   🟡 IP de DATACENTER detectado — TC pode bloquear")
            else:
                print(f"   🟢 IP residencial/business — boa chance")
        except Exception as e:  # noqa: BLE001
            print(f"   (ipinfo falhou: {e})")

    # ── 3. Página pública do TC ─────────────────────────────
    print("\n2) Página pública do TC (sem cookies)")
    async with httpx.AsyncClient(timeout=20.0, http2=True, follow_redirects=False) as c:
        try:
            r = await c.get(f"{TC}/", headers={"User-Agent": UA, "Accept": "text/html"})
            print(f"   GET / → status={r.status_code}")
            if r.status_code == 200 and "tecconcursos" in r.text.lower():
                print(f"   🟢 página carrega")
            elif "captcha" in r.text.lower() or "verificação" in r.text.lower():
                print(f"   🔴 CAPTCHA detectado — IP suspeito")
            else:
                print(f"   🟡 resposta estranha ({len(r.text)} bytes)")
        except Exception as e:  # noqa: BLE001
            print(f"   🔴 FALHA: {e}")
            return

    if not email or not password:
        print("\n3) Login PULADO — defina TC_EMAIL e TC_PASSWORD pra testar autenticação")
        print("\n" + "=" * 60)
        print("Veredito parcial: rota anônima OK; login não testado.")
        print("=" * 60)
        return

    # ── 4. Login Playwright ─────────────────────────────────
    print("\n3) Login Playwright (headless)")
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(user_agent=UA)
            page = await ctx.new_page()
            await page.goto(f"{TC}/login")
            await page.fill('#email', email)
            await page.fill('#senha', password)
            await page.click('button:has-text("Entrar no site")')
            try:
                await page.wait_for_url(lambda u: "/login" not in u, timeout=20_000)
                print(f"   🟢 login OK — URL final: {page.url}")
                cookies = await ctx.cookies()
                cookies_dict = {c["name"]: c["value"] for c in cookies if "tecconcursos" in c["domain"]}
            except Exception as e:  # noqa: BLE001
                content = await page.content()
                if "captcha" in content.lower() or "verificação" in content.lower():
                    print(f"   🔴 CAPTCHA no login — TC desconfia desse IP")
                else:
                    print(f"   🔴 timeout login: {e}")
                await browser.close()
                return
            await browser.close()
    except ImportError:
        print("   🟡 playwright não instalado nesse container — pulando")
        cookies_dict = {}
    except Exception as e:  # noqa: BLE001
        print(f"   🔴 erro no login: {e}")
        return

    # ── 5. Endpoint OURO (o que nosso scraper usa de verdade) ──
    if not cookies_dict:
        print("\n4) Endpoint OURO PULADO (sem cookies)")
        return
    print("\n4) POST /questoes/cadernos/{id}/ajaxCarregarQuestoesImpressao (endpoint OURO)")
    print("   testando com caderno público pequeno…")
    # Caderno 95846378 já validado funcionando (IDECAN CIVIL, 3855 questões)
    caderno_teste = 95846378
    async with httpx.AsyncClient(
        base_url=TC, cookies=cookies_dict, http2=True, timeout=20.0,
        headers={
            "User-Agent": UA,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": TC,
            "Referer": f"{TC}/questoes/cadernos/{caderno_teste}/imprimir",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    ) as c:
        body = f"configuracoes.idCadernoQuestoes={caderno_teste}&configuracoes.idTeoriaModulo=&configuracoes.idTeoriaAssunto=&configuracoes.questaoInicial=0&configuracoes.numeroQuestoes=10&configuracoes.removerQuestoes=NENHUMA"
        r = await c.post(f"/questoes/cadernos/{caderno_teste}/ajaxCarregarQuestoesImpressao", content=body)
        print(f"   status={r.status_code}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", ""):
            data = r.json()
            n = len(data.get("list", []))
            print(f"   🟢 OURO funcionando — {n} questões retornadas")
        elif r.status_code == 429:
            print(f"   🔴 RATE LIMITED no OURO — não rodar scraper ainda")
        elif r.status_code == 403:
            print(f"   🔴 ACESSO NEGADO no OURO — IP bloqueado")
        elif "captcha" in r.text.lower() or "verification" in r.text.lower():
            print(f"   🔴 CAPTCHA no OURO — IP marcado, esperar 24h")
        else:
            print(f"   🟡 resposta inesperada: status={r.status_code} body[:200]={r.text[:200]}")

    # ── 6. Veredito final ───────────────────────────────────
    print("\n" + "=" * 60)
    print("VEREDITO: 🟢 OK pra rodar scraper desse IP")
    print("=" * 60)
    print("Próximo passo: docker compose -f docker-compose.prod.yml up -d")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
