import os, time, requests, sys
import xml.etree.ElementTree as ET
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_ADMIN_ID")
IBKR_TOKEN = os.getenv("IBKR_TOKEN")
IBKR_QUERY_ID = os.getenv("IBKR_QUERY_ID")

def log(msg):
    print(f"[{datetime.now()}] {msg}", flush=True)

def send_telegram_msg(text, keyboard=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        log(f"Failed to send Telegram msg: {e}")

def get_live_price(symbol):
    for attempt in range(3):
        try:
            hist = yf.Ticker(symbol).history(period="1d")
            if hist is not None and not hist.empty:
                return float(hist['Close'].iloc[-1])
        except: pass
        time.sleep(2)
    return 0.0

def get_ibkr_trades():
    try:
        send_url = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest"
        res = requests.get(send_url, params={"t": IBKR_TOKEN, "q": IBKR_QUERY_ID, "v": "3"}, timeout=30)
        root = ET.fromstring(res.text)
        ref_code = root.find(".//ReferenceCode").text

        log(f"✅ Code: {ref_code}. Waiting for report...")
        for attempt in range(3):
            time.sleep(15)
            url_get = "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement"
            res_data = requests.get(url_get, params={"q": ref_code, "t": IBKR_TOKEN, "v": "3"}, timeout=30)
            if "<Flex" in res_data.text or "<Trade" in res_data.text:
                root = ET.fromstring(res_data.text)
                
                # --- שאיבת NAV אוטומטית ---
                try:
                    import json, os
                    nav = None
                    for elem in root.iter():
                        if elem.tag.lower().endswith("changeinnav"):
                            val = elem.attrib.get('endingValue')
                            if val:
                                nav = float(val)
                                break
                    if nav:
                        cfg = "/home/orangepi/sentinel_trading/sentinel_config.json"
                        settings = {"total_deposited": 7500.0, "risk_pct_input": 0.5}
                        if os.path.exists(cfg):
                            with open(cfg, "r") as f: settings = json.load(f)
                        settings["current_nav"] = nav
                        with open(cfg, "w") as f: json.dump(settings, f)
                        log(f"🏦 IBKR NAV updated automatically: ${nav:,.2f}")
                except Exception as e:
                    log(f"⚠️ Error updating NAV: {e}")
                # -------------------------
                    
                return root.findall(".//Trade")
            log(f"⏳ Attempt {attempt+1}/3: Report not ready...")
        return []
    except Exception as e:
        log(f"🚨 IBKR Error: {e}")
        return []

def check_live_alerts():
    log("🔍 Running Live Price Alerts Check (Campaign Aware)...")
    res = supabase.table("trades").select("trade_id,symbol,quantity,price,stop_loss,initial_stop,setup_type,notes,campaign_id").execute()
    if not res.data: return

    df = pd.DataFrame(res.data)
    df['quantity'] = pd.to_numeric(df['quantity']).fillna(0)
    df['price'] = pd.to_numeric(df['price']).fillna(0)
    df['stop_loss'] = pd.to_numeric(df['stop_loss']).fillna(0)
    df['initial_stop'] = pd.to_numeric(df.get('initial_stop', df['stop_loss'])).fillna(0)

    # Filter only OPEN campaigns
    open_pos = []
    # Using campaign_id directly
    for cid, group in df[df['campaign_id'].notnull()].groupby('campaign_id'):
        group = group.sort_values('trade_id')
        net_qty = group['quantity'].sum()
        
        if net_qty > 0.001:
            buys = group[group['quantity'] > 0]
            avg_entry = (buys['price'] * buys['quantity']).sum() / buys['quantity'].sum() if not buys.empty else group.iloc[-1]['price']
            
            # Extract latest relevant stop loss details
            last_trade = group.iloc[-1]
            # Override with the proper campaign details
            last_trade['avg_entry'] = avg_entry
            valid_sls = group[group['stop_loss'] > 0]['stop_loss']
            last_trade['current_stop'] = valid_sls.iloc[-1] if not valid_sls.empty else 0
            
            valid_inits = group[group['initial_stop'] > 0]['initial_stop']
            last_trade['start_stop'] = valid_inits.iloc[0] if not valid_inits.empty else last_trade['current_stop']
            
            open_pos.append(last_trade)

    if not open_pos: return
    df_open = pd.DataFrame(open_pos)

    for _, row in df_open.iterrows():
        sym = row['symbol']
        avg_price = row['avg_entry']
        sl = float(row['current_stop'])
        init_sl = float(row['start_stop'])
        setup = str(row['setup_type']).upper()
        # For alerts, update the originating trade (parent)
        t_id = row['trade_id'] # Fallback
        cid = str(row['campaign_id'])
        current_notes = str(row['notes']) if row['notes'] is not None else ""

        if setup == 'ALGO': continue

        current_price = get_live_price(sym)
        if current_price <= 0: continue

        # 🚨 Hard Override: חגורת בטיחות עליונה
        if sl > 0 and current_price <= sl and "SL_SENT" not in current_notes:
            send_telegram_msg(f"🚨 *התרעת STOP LOSS נחצתה!*\n\n▪️ נכס: `{sym}`\n▪️ מחיר נוכחי: `${current_price:.2f}`\n▪️ סטופ מוגדר: `${sl:.2f}`\n\n⚠️ חגורת הבטיחות נפרצה! המחיר ירד מתחת לסטופ. סגור את הפוזיציה מיד בברוקר.")
            # Update the specific trade note (or preferably, we update all items in the campaign in the future)
            supabase.table("trades").update({"notes": current_notes + " | SL_SENT"}).eq("trade_id", t_id).execute()

        # 🎯 התרעות R-Multiples מבוססות סיכון התחלתי
        elif init_sl > 0 and current_price > avg_price:
            risk = avg_price - init_sl
            if risk > 0:
                rr = (current_price - avg_price) / risk
                if rr >= 3.0 and "3R_SENT" not in current_notes:
                    send_telegram_msg(f"🎯 *התרעת יעד רווח 3R!*\n\n▪️ נכס: `{sym}`\n▪️ R:R צף: `{rr:.2f}R`\n\n💰 המניה הגיעה ליעד פי 3! שקול מימוש חלקי לנעילת רווח.")
                    supabase.table("trades").update({"notes": current_notes + " | 3R_SENT"}).eq("trade_id", t_id).execute()
                elif rr >= 2.0 and rr < 3.0 and "2R_SENT" not in current_notes:
                    send_telegram_msg(f"🎯 *התרעת יעד רווח 2R!*\n\n▪️ נכס: `{sym}`\n▪️ R:R צף: `{rr:.2f}R`\n\n🟢 הגעת ל-2R. שקול קידום סטופ ל-BE (Break Even).")
                    supabase.table("trades").update({"notes": current_notes + " | 2R_SENT"}).eq("trade_id", t_id).execute()

def sync_logic():
    log("🔍 Sync Cycle Started (Campaign Aware)")
    check_live_alerts()
    trades = get_ibkr_trades()

    if not trades:
        log("ℹ️ No new IBKR data available.")
        return

    new_trades_count = 0
    closed_trades_count = 0
    partial_trades_count = 0

    db_data = supabase.table("trades").select("*").execute().data
    df_db = pd.DataFrame(db_data) if db_data else pd.DataFrame(columns=["symbol", "quantity", "side", "setup_type", "quality", "trade_id", "campaign_id"])
    if not df_db.empty:
        df_db['quantity'] = pd.to_numeric(df_db['quantity']).fillna(0)
    
    # Track currently open campaigns
    # We find the net quantity per campaign ID. If > 0, it's open.
    open_campaigns = {} # dict mapping symbol -> {campaign_id, parent_trade_id, net_qty, setup_type}
    if not df_db.empty and 'campaign_id' in df_db.columns:
        for cid, group in df_db[df_db['campaign_id'].notnull()].groupby('campaign_id'):
            net_qty = group['quantity'].sum()
            if net_qty > 0.001:
                sym = group.iloc[0]['symbol']
                setup = group.iloc[0].get('setup_type', 'Unknown')
                parent = group.iloc[0].get('parent_trade_id')
                open_campaigns[sym] = {
                    'campaign_id': cid,
                    'parent_trade_id': parent,
                    'net_qty': net_qty,
                    'setup_type': setup
                }

    for t in trades:
        t_id = str(t.attrib.get('tradeID'))
        symbol = t.attrib.get('symbol')
        side = t.attrib.get('buySell')
        price = float(t.attrib.get('tradePrice'))
        pnl = float(t.attrib.get('fifoPnlRealized', 0))
        raw_date = t.attrib.get('tradeDate')
        fmt_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        qty = float(t.attrib.get('quantity'))

        existing = [x for x in db_data if str(x.get("trade_id")) == t_id] if db_data else []

        if not existing:
            # 🛡️ NEW LOGIC: Campaign Assignment
            current_campaign = open_campaigns.get(symbol)
            is_new_campaign = False
            
            if current_campaign:
                # We have an open campaign for this symbol. Add to it.
                cid = current_campaign['campaign_id']
                parent_id = current_campaign['parent_trade_id']
                new_net = current_campaign['net_qty'] + qty
                open_campaigns[symbol]['net_qty'] = new_net
                setup = current_campaign['setup_type']
            else:
                # No open campaign. If it's a BUY, start a new one.
                if qty > 0:
                    cid = f"{symbol}_{t_id}"
                    parent_id = t_id
                    new_net = qty
                    setup = "Unknown"
                    is_new_campaign = True
                    open_campaigns[symbol] = {
                        'campaign_id': cid,
                        'parent_trade_id': parent_id,
                        'net_qty': new_net,
                        'setup_type': setup
                    }
                else:
                    # Rare edge case: Selling an orphan position we didn't track
                    cid = f"{symbol}_LEGACY_{t_id}"
                    parent_id = t_id
                    new_net = qty
                    setup = "Unknown"

            trade_info = {
                "trade_id": t_id, "symbol": symbol, "side": side,
                "price": price, "pnl_usd": pnl, "trade_date": fmt_date,
                "quantity": qty,
                "campaign_id": cid,
                "parent_trade_id": parent_id,
                "management_state": "full_position",
                "is_closed": True if pnl != 0 else False
            }

            if side.upper() == "SELL":
                # Inherit setup from the open campaign
                trade_info["setup_type"] = str(setup) if pd.notna(setup) else "Unknown"
                
                if new_net > 0.001:
                    trade_info["score"] = 10
                    trade_info["image_url"] = "ScaleOut"
                    trade_info["management_state"] = "runner_mode" # Flag the sell transaction
                    # Update all items in campaign to runner_mode later
                    supabase.table("trades").update({"management_state": "runner_mode"}).eq("campaign_id", cid).execute()

            clean_info = {}
            for k, v in trade_info.items():
                if pd.isna(v): clean_info[k] = None
                elif isinstance(v, bool): clean_info[k] = bool(v)
                elif isinstance(v, (np.integer, int)): clean_info[k] = int(v)
                elif isinstance(v, (np.floating, float)): clean_info[k] = float(v)
                else: clean_info[k] = v if v is None else str(v)
            
            clean_info["is_closed"] = bool(trade_info.get("is_closed", False))

            try:
                supabase.table("trades").insert(clean_info).execute()
                
                if side.upper() == "SELL":
                    if new_net > 0.001:
                        send_telegram_msg(f"💸 *מימוש רווח חלקי (Scale-Out)!*\n\n▪️ נכס: {symbol}\n▪️ מחיר יציאה: `${price:.2f}`\n▪️ רווח שמומש: `${pnl:.2f}`\n▪️ נותרו בפוזיציה: `{new_net}` יח'.\nסטטוס ניהולי עודכן ל: *Runner Mode*")
                        partial_trades_count += 1
                    else:
                        closed_trades_count += 1
                        # Update state to closed
                        supabase.table("trades").update({"management_state": "closed", "is_closed": True}).eq("campaign_id", cid).execute()
                        if symbol in open_campaigns: del open_campaigns[symbol]
                else:
                    if is_new_campaign:
                        new_trades_count += 1

            except Exception as e:
                log(f"🚨 DB Insert Failed: {e}")
                send_telegram_msg(f"🚨 *שגיאת שמירה במסד הנתונים!*\nלא הצלחתי לשמור את {symbol}.\nשגיאה: `{str(e)}`")
                
        else:
            db_trade = existing[0]
            if float(db_trade.get('pnl_usd', 0)) != pnl or db_trade.get('is_closed') == False and pnl != 0:
                update_data = {"pnl_usd": pnl, "is_closed": True if pnl != 0 else False, "price": price}
                supabase.table("trades").update(update_data).eq("trade_id", t_id).execute()

    if new_trades_count > 0 or closed_trades_count > 0 or partial_trades_count > 0:
        summary_msg = "📥 *סנכרון מול אינטראקטיב הושלם:*\n\n"
        if new_trades_count > 0: summary_msg += f"➕ `{new_trades_count}` פוזיציות חדשות נפתחו\n"
        if partial_trades_count > 0: summary_msg += f"💸 `{partial_trades_count}` מימושים חלקיים (Scale-Out)\n"
        if closed_trades_count > 0: summary_msg += f"🏁 `{closed_trades_count}` קמפיינים נסגרו סופית\n"
        summary_msg += "\nלחץ על 🔍 *סריקת יומן (Backlog)* כדי להשלים את הנתונים."
        send_telegram_msg(summary_msg)

    log("🏁 Sync Cycle Finished")

if __name__ == "__main__":
    log("🛡️ Sentinel Direct Sync v15.0 (Campaign Aware) Active")
    while True:
        try:
            sync_logic()
        except Exception as e:
            log(f"🚨 Crash in Main Loop: {e}")
        time.sleep(305)
