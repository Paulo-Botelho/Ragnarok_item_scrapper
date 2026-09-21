import csv
import io
import json
import re
import time
from curl_cffi import requests

# ==========================================
# CONFIGURAÇÕES
# ==========================================
# Substitua pelo ID da sua planilha do Google Sheets
GOOGLE_SHEET_ID = "15k76ng_hj93Vj73fCGiKHf4QguGQaMTpLp_0eQqD2vM"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"

SERVER_TYPE = "NIDHOGG"
CHECK_INTERVAL = 300
DELAY_BETWEEN_ITEMS = 3
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1551625864888979517/0RpujeI_JAkXTs1Nc7YW4iZktVGATNq6v5z2Fim1EzqlIjVc9QN8WWeJ_AbttvqU1oEv"
URL = "https://ro.gnjoyamericas.com/pt/intro/shop-search/trading"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "RSC": "1",
    "Referer": "https://ro.gnjoyamericas.com/pt/intro/shop-search/trading",
}


def load_items_from_sheets() -> list:
    """Baixa e converte a planilha pública do Google Sheets em lista de itens."""
    try:
        response = requests.get(CSV_URL, timeout=10, impersonate="chrome124")
        response.raise_for_status()

        csv_data = io.StringIO(response.text)
        reader = csv.DictReader(csv_data)

        items = []
        for row in reader:
            search_word = row.get("searchWord", "").strip()
            if not search_word:
                continue

            raw_price = str(row.get("maxPrice", "0")).replace(".", "").replace(",", "").strip()

            items.append({
                "searchWord": search_word,
                "exactName": row.get("exactName", "").strip(),
                "maxPrice": int(raw_price) if raw_price.isdigit() else 0,
                "storeType": row.get("storeType", "SELL").strip().upper(),
            })
        return items
    except Exception as e:
        print(f"Erro ao carregar itens do Google Sheets: {e}")
        return []


def parse_rsc_payload(raw_text: str) -> list:
    """Extrai a lista de produtos retornada no payload Next.js."""
    match = re.search(r'\{"queryParams":.*?"totalCount":\d+\}', raw_text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        return data.get("list", [])
    except json.JSONDecodeError:
        return []


def send_alert(message: str):
    """Exibe o alerta no terminal e envia no Discord se configurado."""
    print(f"\n[!!!] OPORTUNIDADE ENCONTRADA [!!!]\n{message}\n")
    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": message},
                timeout=5,
                impersonate="chrome",
            )
        except Exception as e:
            print(f"Erro ao enviar webhook: {e}")


def check_single_item(item_config: dict):
    search_word = item_config["searchWord"]
    exact_name = item_config.get("exactName", "").strip().lower()
    max_price = item_config["maxPrice"]
    store_type = item_config["storeType"]

    params = {
        "storeType": store_type,
        "serverType": SERVER_TYPE,
        "searchWord": search_word,
    }

    target_label = item_config.get("exactName") or search_word

    try:
        response = requests.get(
            URL,
            headers=HEADERS,
            params=params,
            timeout=15,
            impersonate="chrome124",
        )
        response.raise_for_status()
    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] Erro na busca por '{target_label}': {e}")
        return

    items = parse_rsc_payload(response.text)

    if not items:
        print(f"[{time.strftime('%H:%M:%S')}] Checagem '{target_label}': Nenhuma loja encontrada no site.")
        return

    found_cheap = False
    ignored_name_count = 0
    ignored_price_count = 0

    for item in items:
        item_name = item.get("itemName", "").strip()

        # Filtro de nome exato (se preenchido)
        if exact_name and item_name.lower() != exact_name:
            ignored_name_count += 1
            continue

        try:
            price = int(item.get("itemPrice", 0))
        except ValueError:
            price = 0

        qty = item.get("itemCnt", 1)
        store_name = item.get("storeName", "Sem nome")
        seller_name = item.get("itemSellerCharName", "Desconhecido")

        if 0 < price <= max_price:
            found_cheap = True
            msg = (
                f"🔥 **Oferta Encontrada!**\n"
                f"• **Item:** {item_name}\n"
                f"• **Preço:** {price:,} Zeny (Limite: {max_price:,} Zeny)\n"
                f"• **Quantidade:** {qty}\n"
                f"• **Loja:** {store_name}\n"
                f"• **Vendedor:** {seller_name}\n"
                f"• **Servidor:** {SERVER_TYPE}\n"
                f"• **Tipo de Loja:** {store_type}"
            )
            send_alert(msg)
        else:
            ignored_price_count += 1

    if not found_cheap:
        print(
            f"[{time.strftime('%H:%M:%S')}] Checagem '{target_label}': "
            f"{ignored_price_count} ofertas acima do limite ({max_price:,} Zeny) / {ignored_name_count} ignoradas por nome."
        )


def run_monitor():
    items_to_monitor = load_items_from_sheets()

    if not items_to_monitor:
        print("Nenhum item encontrado na planilha ou erro ao carregar o CSV.")
        return

    print(f"\n--- Iniciando ciclo de checagem ({len(items_to_monitor)} itens na planilha) ---")
    for item_config in items_to_monitor:
        check_single_item(item_config)
        time.sleep(DELAY_BETWEEN_ITEMS)


if __name__ == "__main__":
    print(f"Iniciando checagem de itens...")
    run_monitor()
