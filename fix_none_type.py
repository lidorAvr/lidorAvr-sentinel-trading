with open('main.py', 'r') as f:
    code = f.read()

old_block = """        res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)
        root = ET.fromstring(res.text)
        ref_code = root.find(".//ReferenceCode").text"""

new_block = """        res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)
        root = ET.fromstring(res.text)
        status_tag = root.find(".//Status")
        if status_tag is not None and status_tag.text == "Fail":
            return [] # IBKR is busy, just return empty list and try later quietly
        ref_code_elem = root.find(".//ReferenceCode")
        if ref_code_elem is None:
            return []
        ref_code = ref_code_elem.text"""

if old_block in code:
    code = code.replace(old_block, new_block)
    with open('main.py', 'w') as f:
        f.write(code)
    print("✅ חגורת בטיחות למניעת קריסות של אינטראקטיב נוספה לקוד הגיטהאב.")
