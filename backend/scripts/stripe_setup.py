"""Provisiona o produto/preço e o webhook do studIA no Stripe (idempotente).

Uso (com as chaves no ambiente):
    python -m scripts.stripe_setup
    python -m scripts.stripe_setup --webhook-url https://studia.witdev.com.br/api/billing/webhook

Imprime STRIPE_PRICE_ID (e STRIPE_WEBHOOK_SECRET quando cria o webhook) para
colar no .env. Reusa produto/preço/webhook já existentes pelo metadata/URL.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from stripe_client import STRIPE_SECRET_KEY, stripe_request

PRODUTO_NOME = "studIA Pro"
VALOR_CENTAVOS = 2990
MOEDA = "brl"
INTERVALO = "month"
EVENTOS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
]


async def _achar_ou_criar_produto() -> dict:
    prods = await stripe_request("GET", "/products?limit=100&active=true")
    for p in prods.get("data", []):
        if p.get("name") == PRODUTO_NOME or (p.get("metadata") or {}).get("app") == "studia":
            return p
    return await stripe_request(
        "POST",
        "/products",
        {"name": PRODUTO_NOME, "metadata[app]": "studia",
         "description": "Acesso ilimitado a questões no studIA"},
    )


async def _achar_ou_criar_preco(product_id: str) -> dict:
    prices = await stripe_request("GET", f"/prices?product={product_id}&active=true&limit=100")
    for pr in prices.get("data", []):
        rec = pr.get("recurring") or {}
        if (
            pr.get("unit_amount") == VALOR_CENTAVOS
            and pr.get("currency") == MOEDA
            and rec.get("interval") == INTERVALO
        ):
            return pr
    return await stripe_request(
        "POST",
        "/prices",
        {
            "product": product_id,
            "unit_amount": str(VALOR_CENTAVOS),
            "currency": MOEDA,
            "recurring[interval]": INTERVALO,
            "metadata[app]": "studia",
        },
    )


async def _achar_ou_criar_webhook(url: str) -> tuple[dict, bool]:
    hooks = await stripe_request("GET", "/webhook_endpoints?limit=100")
    for h in hooks.get("data", []):
        if h.get("url") == url:
            return h, False
    data = {"url": url, "metadata[app]": "studia"}
    for i, ev in enumerate(EVENTOS):
        data[f"enabled_events[{i}]"] = ev
    return await stripe_request("POST", "/webhook_endpoints", data), True


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook-url", default="https://studia.witdev.com.br/api/billing/webhook")
    ap.add_argument("--skip-webhook", action="store_true")
    args = ap.parse_args()

    if not STRIPE_SECRET_KEY:
        print("ERRO: STRIPE_SECRET_KEY não definido no ambiente.", file=sys.stderr)
        return 1

    produto = await _achar_ou_criar_produto()
    preco = await _achar_ou_criar_preco(produto["id"])
    print(f"# produto: {produto['id']} ({produto.get('name')})", file=sys.stderr)
    print(f"STRIPE_PRICE_ID={preco['id']}")

    if not args.skip_webhook:
        hook, criado = await _achar_ou_criar_webhook(args.webhook_url)
        if criado and hook.get("secret"):
            print(f"STRIPE_WEBHOOK_SECRET={hook['secret']}")
        elif criado:
            print(f"# webhook criado: {hook['id']} (sem secret retornado?)", file=sys.stderr)
        else:
            print(
                f"# webhook já existia: {hook['id']} — o secret só aparece na criação. "
                "Apague-o no dashboard e rode de novo, ou copie o signing secret manualmente.",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
