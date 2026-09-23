import csv
import io
import json
import re
import time
from curl_cffi import requests

# ==========================================
# CONFIGURAÇÕES
# ==========================================
GOOGLE_SHEET_ID = "15k76ng_hj93Vj73fCGiKHf4QguGQaMTpLp_0eQqD2vM"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv"

SERVER_TYPE = "NIDHOGG"
CHECK_INTERVAL = 300  # Tempo entre ciclos (300s = 5 min)
DELAY_BETWEEN_ITEMS = 3  # Pausa entre requisições
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1551625864888979517/0RpujeI_JAkXTs1Nc7YW4iZktVGATNq6v5z2Fim1EzqlIjVc9QN8WWeJ_AbttvqU1oEv"  # (Opcional) Webhook do Discord

# Hash fixo do Next-Action capturado no DevTools
NEXT_ACTION_HASH = "4007fc6d83865908f9dc6f5b829ccced4aabbbb4ea"

URL = "https://ro.gnjoyamericas.com/pt/intro/shop-search/trading"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "RSC": "1",
    "Referer": "https://ro.gnjoyamericas.com/pt/intro/shop-search/trading",
}


def clean_base_name(name: str) -> str:
    """Remove refinos (+11) e slots ([1], [2]) para comparar apenas o nome base."""
    name = re.sub(r"^\+\d+\s*", "", name)  # Remove +11 do início
    name = re.sub(r"\[\d+\]", "", name)  # Remove [1] do final
    return name.strip().lower()


def extract_refine_level(item_name: str) -> int:
    """Extrai o número do refino do nome completo (ex: '+11Sapato...' -> 11)."""
    match = re.search(r"\+(\d+)", item_name)
    return int(match.group(1)) if match else 0


def load_items_from_sheets(session: requests.Session) -> list:
    """Carrega a planilha do Google Sheets."""
    try:
        response = session.get(CSV_URL, timeout=10)
        response.raise_for_status()

        csv_data = io.StringIO(response.text)
        reader = csv.DictReader(csv_data)

        items = []
        for row in reader:
            search_word = row.get("searchWord", "").strip()
            if not search_word:
                continue

            raw_price = (
                str(row.get("maxPrice", "0"))
                .replace(".", "")
                .replace(",", "")
                .strip()
            )
            raw_refine = str(row.get("minRefine", "0")).replace("+", "").strip()

            items.append(
                {
                    "searchWord": search_word,
                    "exactName": row.get("exactName", "").strip(),
                    "minRefine": int(raw_refine) if raw_refine.isdigit() else 0,
                    "maxPrice": int(raw_price) if raw_price.isdigit() else 0,
                    "storeType": row.get("storeType", "SELL").strip().upper(),
                }
            )
        return items
    except Exception as e:
        print(f"Erro ao carregar itens do Google Sheets: {e}")
        return []


def parse_rsc_payload(raw_text: str) -> list:
    """Extrai a lista inicial de lojas retornada pelo servidor."""
    match = re.search(r'\{"queryParams":.*?"totalCount":\d+\}', raw_text)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
        return data.get("list", [])
    except json.JSONDecodeError:
        return []


def get_item_details(
    session: requests.Session,
    item: dict,
    search_word: str,
    store_type: str,
) -> dict:
    """Dispara a Server Action POST enviando os cabeçalhos exatos do Next.js."""
    svr_id = int(item.get("svrId", 303))
    map_id = int(item.get("mapId", 835))
    ssi = str(item.get("ssi", ""))

    if not ssi:
        return {}

    post_url = f"{URL}?storeType={store_type}&serverType={SERVER_TYPE}&searchWord={search_word}"

    # Árvore de rotas exigida pelo Next Router do site
    router_tree = f"%5B%22%22%2C%7B%22children%22%3A%5B%22locale%22%2C%22pt%22%2C%22d%22%2C%7B%22children%22%3A%5B%22(primary)%22%2C%7B%22children%22%3A%5B%22intro%22%2C%7B%22children%22%3A%5B%22shop-search%22%2C%7B%22children%22%3A%5B%22id%22%2C%22trading%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22__PAGE__%3F%7B%22storeType%22%3A%22{store_type}%22%2C%22serverType%22%3A%22{SERVER_TYPE}%22%2C%22searchWord%22%3A%22{search_word}%22%7D%22%2C%7B%7D%2C%22pt%2Fintro%2Fshop-search%2Ftrading%3FstoreType%3D{store_type}%26serverType%3D{SERVER_TYPE}%26searchWord%3D{search_word}%22%2C%22refresh%22%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2C%22true%5D"

    post_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/x-component",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "text/plain;charset=UTF-8",
        "Next-Action": NEXT_ACTION_HASH,
        "Next-Router-State-Tree": router_tree,
        "Origin": "https://ro.gnjoyamericas.com",
        "Referer": post_url,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=1, i",
    }

    payload = [
        {
            "type": "store",
            "params": {"svrId": svr_id, "mapId": map_id, "ssi": ssi},
        }
    ]

    try:
        response = session.post(
            post_url,
            headers=post_headers,
            data=json.dumps(payload, separators=(",", ":")),  # JSON compacto sem espaços
            timeout=10,
        )

        if response.status_code == 200:
            text = response.text

            full_name_match = re.search(r'"itemFullName":\s*"([^"]+)"', text)
            map_match = re.search(r'"mapName":\s*"([^"]+)"', text)
            xpos_match = re.search(r'"xpos":\s*"([^"]+)"', text)
            ypos_match = re.search(r'"ypos":\s*"([^"]+)"', text)

            if full_name_match:
                return {
                    "itemFullName": full_name_match.group(1),
                    "mapName": map_match.group(1) if map_match else "",
                    "xpos": xpos_match.group(1) if xpos_match else "",
                    "ypos": ypos_match.group(1) if ypos_match else "",
                }
        else:
            print(f"Erro na consulta do item (SSI: {ssi}): Status {response.status_code}")
    except Exception as e:
        print(f"Erro ao obter detalhes da loja: {e}")

    return {}


def send_alert(session: requests.Session, message: str):
    """Exibe no terminal e envia no Discord se configurado."""
    print(f"\n[!!!] OPORTUNIDADE ENCONTRADA [!!!]\n{message}\n")
    if DISCORD_WEBHOOK_URL:
        try:
            session.post(
                DISCORD_WEBHOOK_URL,
                json={"content": message},
                timeout=5,
            )
        except Exception as e:
            print(f"Erro ao enviar webhook: {e}")


def check_single_item(session: requests.Session, item_config: dict):
    search_word = item_config["searchWord"]
    exact_name_raw = item_config.get("exactName", "").strip()
    exact_name_clean = clean_base_name(exact_name_raw)
    min_refine = item_config.get("minRefine", 0)
    max_price = item_config["maxPrice"]
    store_type = item_config["storeType"]

    params = {
        "storeType": store_type,
        "serverType": SERVER_TYPE,
        "searchWord": search_word,
    }

    target_label = exact_name_raw or search_word
    if min_refine > 0:
        target_label = f"+{min_refine} {target_label}"

    try:
        response = session.get(
            URL,
            headers=HEADERS,
            params=params,
            timeout=15,
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
    ignored_refine_count = 0

    for item in items:
        item_name_raw = item.get("itemName", "").strip()
        item_name_clean = clean_base_name(item_name_raw)

        # Filtro 1: Nome base do item
        if exact_name_clean and item_name_clean != exact_name_clean:
            ignored_name_count += 1
            continue

        try:
            price = int(item.get("itemPrice", 0))
        except ValueError:
            price = 0

        # Filtro 2: Preço máximo
        if 0 < price <= max_price:
            # Consulta os detalhes (com refino real +11 e coordenadas /navi)
            details = get_item_details(
                session, item, search_word, store_type
            )
            full_name = details.get("itemFullName") or item_name_raw

            item_refine = extract_refine_level(full_name)

            # Filtro 3: Refino mínimo
            if min_refine > 0 and item_refine < min_refine:
                ignored_refine_count += 1
                continue

            found_cheap = True

            map_name = details.get("mapName", "")
            xpos = details.get("xpos", "")
            ypos = details.get("ypos", "")

            location_str = (
                f"/navi {map_name} {xpos}/{ypos}"
                if map_name and xpos and ypos
                else "Não disponível"
            )
            qty = item.get("itemCnt", 1)
            store_name = item.get("storeName", "Sem nome")
            seller_name = item.get("itemSellerCharName", "Desconhecido")

            msg = (
                f"🔥 **Oferta Encontrada!**\n"
                f"• **Item:** {full_name}\n"
                f"• **Preço:** {price:,} Zeny (Limite: {max_price:,} Zeny)\n"
                f"• **Quantidade:** {qty}\n"
                f"• **Localização:** `{location_str}`\n"
                f"• **Loja:** {store_name}\n"
                f"• **Vendedor:** {seller_name}\n"
                f"• **Servidor:** {SERVER_TYPE}\n"
                f"• **Tipo de Loja:** {store_type}"
            )
            send_alert(session, msg)
        else:
            ignored_price_count += 1

    if not found_cheap:
        status_parts = []
        if ignored_price_count > 0:
            status_parts.append(f"{ignored_price_count} acima do preço máximo")
        if ignored_refine_count > 0:
            status_parts.append(f"{ignored_refine_count} com refino abaixo de +{min_refine}")
        if ignored_name_count > 0:
            status_parts.append(f"{ignored_name_count} ignorados por nome")

        details_str = (
            " / ".join(status_parts)
            if status_parts
            else "Nenhum item atendeu aos critérios."
        )
        print(f"[{time.strftime('%H:%M:%S')}] Checagem '{target_label}': {details_str}")


def run_monitor():
    session = requests.Session(impersonate="chrome124")

    items_to_monitor = load_items_from_sheets(session)

    if not items_to_monitor:
        print("Nenhum item encontrado na planilha ou erro ao carregar o CSV.")
        return

    for count, item_config in enumerate(items_to_monitor, start=1):
        # A cada 20 itens processados, faz a pausa de 90s para resetar a janela do Cloudflare
        if count > 1 and (count - 1) % 20 == 0:
            print(f"\n[⏳] Lote de 20 itens processado. Pausando 90s para resfriar a taxa do Cloudflare...\n")
            time.sleep(90)

        check_single_item(session, item_config)
        time.sleep(DELAY_BETWEEN_ITEMS)


if __name__ == "__main__":
    while True:
        run_monitor()
        print(f"\nAguardando {CHECK_INTERVAL}s para o próximo ciclo...\n")
        time.sleep(CHECK_INTERVAL)
