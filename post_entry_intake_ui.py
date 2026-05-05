import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from telebot import types

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "post_entry_intake_state.json"

RTL = "\u200f"
SEP = "━━━━━━━━━━━━"

def _now():
    return datetime.now(timezone.utc).isoformat()

def _load_state():
    if not STATE_FILE.exists():
        return {"campaigns": {}}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"campaigns": {}}

def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def _campaign_state(cid):
    state = _load_state()
    campaigns = state.setdefault("campaigns", {})
    item = campaigns.setdefault(cid, {"events": []})
    return state, item

def _event(cid, event_type, payload=None):
    state, item = _campaign_state(cid)
    item.setdefault("events", []).append({
        "at": _now(),
        "type": event_type,
        "payload": payload or {},
    })
    _save_state(state)

def _first(row, names, default=None):
    for n in names:
        v = row.get(n)
        if v not in (None, "", []):
            return v
    return default

def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default

def _money(v):
    x = _num(v)
    if x is None:
        return "לא ידוע"
    return f"${x:,.2f}"

def _pct(v):
    x = _num(v)
    if x is None:
        return "לא ידוע"
    return f"{x:.0f}%"

def _short(v, default="לא ידוע"):
    if v is None:
        return default
    s = str(v).strip()
    return s if s else default

def _risk_alignment_he(v):
    s = str(v or "").lower()
    if "high" in s or "oversized" in s:
        return "גבוה מדי"
    if "low" in s or "undersized" in s:
        return "נמוך מדי"
    if "aligned" in s:
        return "תקין"
    return _short(v)

def _status_allowed(row, local):
    local_status = local.get("status")
    if local_status in ("approved", "skipped"):
        return False
    status = _first(row, ["task_status", "status"], "pending")
    if str(status).lower() in ("completed", "done", "approved", "closed", "cancelled"):
        return False
    return True

def _safe_answer(bot, call, text="נקלט"):
    try:
        bot.answer_callback_query(call.id, text)
    except Exception:
        pass

def _safe_update(supabase, table, key_col, key_val, candidates):
    for payload in candidates:
        clean = {k: v for k, v in payload.items() if v is not None}
        if not clean:
            continue
        try:
            supabase.table(table).update(clean).eq(key_col, key_val).execute()
            return True
        except Exception:
            continue
    return False

def _get_plan(supabase, campaign_id):
    try:
        rows = supabase.table("campaign_plans").select("*").eq("campaign_id", campaign_id).limit(1).execute().data or []
        return rows[0] if rows else {}
    except Exception:
        return {}

def _get_task_rows(supabase):
    try:
        return supabase.table("campaign_intake_tasks").select("*").limit(200).execute().data or []
    except Exception:
        return []

def _get_pending_items(supabase):
    state = _load_state()
    rows = _get_task_rows(supabase)
    items = []
    for row in rows:
        cid = row.get("campaign_id")
        if not cid:
            continue
        local = state.get("campaigns", {}).get(cid, {})
        snooze_until = local.get("snooze_until")
        if snooze_until:
            try:
                if datetime.fromisoformat(snooze_until) > datetime.now(timezone.utc):
                    continue
            except Exception:
                pass
        if not _status_allowed(row, local):
            continue
        plan = _get_plan(supabase, cid)
        merged = dict(row)
        merged.update({f"plan_{k}": v for k, v in plan.items()})
        items.append((row, plan, merged))
    return items


def _as_obj(v):
    if v in (None, "", []):
        return None
    if isinstance(v, (dict, list)):
        return v
    if isinstance(v, str):
        txt = v.strip()
        if not txt:
            return None
        try:
            return json.loads(txt)
        except Exception:
            return txt
    return v

def _fmt_r(v):
    x = _num(v)
    if x is None:
        return "לא ידוע"
    sign = "+" if x > 0 else ""
    return f"{sign}{x:.2f}R"

def _fmt_confidence_word(v):
    s = str(v or "").strip()
    mapping = {
        "low": "נמוך",
        "medium_low": "בינוני-נמוך",
        "medium": "בינוני",
        "medium_high": "בינוני-גבוה",
        "high": "גבוה",
    }
    return mapping.get(s, s or "לא ידוע")

def _append_rule_lines(lines, obj, mode):
    obj = _as_obj(obj)

    if isinstance(obj, str):
        lines.append(f"{RTL}• {obj}")
        return

    if not isinstance(obj, dict):
        lines.append(f"{RTL}• לפי התוכנית המחושבת של המערכת.")
        return

    if mode == "strength":
        triggers = obj.get("triggers") or []
        stat = obj.get("stat_basis") or {}
        for item in triggers[:4]:
            if not isinstance(item, dict):
                continue
            rule = item.get("rule_he") or item.get("rule") or item.get("trigger")
            action = item.get("preferred_action")
            if rule:
                lines.append(f"{RTL}• {rule}")
            if action:
                lines.append(f"{RTL}  פעולה: {action}")

        if stat:
            sample = stat.get("sample_size")
            avg_win = stat.get("avg_win_r")
            win = stat.get("win_rate")
            exp = stat.get("expectancy_r")
            conf = _fmt_confidence_word(stat.get("confidence"))
            bits = []
            if sample is not None:
                bits.append(f"{sample} קמפיינים מאומתים")
            if avg_win is not None:
                bits.append(f"Avg Win {_fmt_r(avg_win)}")
            if exp is not None:
                bits.append(f"Expectancy {_fmt_r(exp)}")
            if win is not None:
                try:
                    bits.append(f"Win {float(win) * 100:.0f}%" if float(win) <= 1 else f"Win {float(win):.0f}%")
                except Exception:
                    pass
            bits.append(f"ביטחון {conf}")
            lines.append(f"{RTL}  בסיס: " + " | ".join(bits))

        note = obj.get("confidence_note_he")
        if note:
            lines.append(f"{RTL}  הערה: {note}")
        return

    if mode == "weakness":
        rules = obj.get("rules") or []
        for item in rules[:4]:
            if not isinstance(item, dict):
                continue
            rule = item.get("rule_he") or item.get("rule") or item.get("trigger")
            action = item.get("preferred_action")
            deadline = item.get("deadline")
            if rule:
                lines.append(f"{RTL}• {rule}")
            details = []
            if action:
                details.append(f"פעולה: {action}")
            if deadline:
                details.append(f"זמן פעולה: {deadline}")
            if details:
                lines.append(f"{RTL}  " + " | ".join(details))
        return

    if mode == "emergency":
        rule = obj.get("rule_he") or obj.get("rule") or "סטופ נחצה = יציאה מלאה."
        deadline = obj.get("deadline")
        partial = obj.get("partial_loss_sell_allowed")
        lines.append(f"{RTL}• {rule}")
        if deadline:
            lines.append(f"{RTL}  זמן פעולה: {deadline}")
        if partial is False:
            lines.append(f"{RTL}  כלל: אין מכירת חצי בצד ההפסד.")
        return


def _plan_text(task, plan):
    cid = task.get("campaign_id") or plan.get("campaign_id")
    state = _load_state().get("campaigns", {}).get(cid, {})

    symbol = _first(plan, ["symbol"], _first(task, ["symbol"], "UNKNOWN"))
    setup = state.get("setup_override") or _first(plan, ["setup_type", "estimated_setup", "setup"], _first(task, ["setup_type"], "לא מסווג"))
    stop = state.get("stop_override") or _first(plan, ["initial_stop_price", "stop_price", "current_stop", "proposed_stop"])
    target = _first(plan, ["target_risk_usd"])
    actual = _first(plan, ["actual_initial_risk_usd"])
    confidence = _first(plan, ["confidence_score", "confidence"], "")
    quality = _first(plan, ["data_quality_status", "quality"], "verified")
    sample = _first(plan, ["strategy_sample_size", "sample_size"], "")
    scope = _first(plan, ["metric_scope", "strategy_scope"], "YTD_VERIFIED_CAMPAIGNS_ONLY")
    catalyst = state.get("catalyst") or _first(plan, ["catalyst"], None)

    lines = [
        f"{RTL}🧾 תוכנית ניהול - {symbol}",
        f"{RTL}{SEP}",
        f"{RTL}• קמפיין: {cid}",
        f"{RTL}• Setup: {setup}",
        f"{RTL}• סטופ: {_money(stop)}",
        f"{RTL}• סיכון: {_money(actual)} בפועל מול {_money(target)} יעד",
        f"{RTL}• איכות נתונים: {_short(quality)}",
    ]

    if confidence != "":
        lines.append(f"{RTL}• ביטחון: {_pct(confidence)}")
    if sample not in ("", None):
        lines.append(f"{RTL}• סטטיסטיקה: {sample} קמפיינים מאומתים")
    lines.append(f"{RTL}• Scope: {scope}")

    lines += [
        "",
        f"{RTL}📈 לעוצמה:",
        f"{RTL}• סביב 2R: לקדם סטופ לכניסה / סיכון אפס.",
        f"{RTL}• סביב 3R+: לממש 25% כברירת מחדל; אם המהלך מתוח או ותיק, 50%. יתרה עם סטופ SMA10/סיכון אפס.",
        f"{RTL}• קליימקס/גאפ מאוחר/ווליום חריג: למכור לתוך עוצמה או להדק.",
        "",
        f"{RTL}📉 לחולשה:",
        f"{RTL}• סטופ נחצה: יציאה מלאה.",
        f"{RTL}• אין Follow Through: להפחית 50% או לצאת אם חלון הזמן נגמר.",
        f"{RTL}• 3 שפלים יורדים או סגירות חלשות: להקטין חשיפה.",
        "",
        f"{RTL}🚨 חירום:",
        f"{RTL}• סטופ נחצה = סוגרים בברוקר. אין מכירת חצי בצד ההפסד.",
    ]

    if catalyst:
        lines += ["", f"{RTL}🧠 קטליסט", f"{RTL}• {catalyst}"]

    lines += [
        "",
        f"{RTL}אשרי או ערכי רק את מה שבאמת צריך.",
    ]
    return "\n".join(lines)


def _plan_keyboard(cid):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ אשר תוכנית", callback_data=f"intake:approve:{cid}"),
        types.InlineKeyboardButton("✏️ ערוך סטופ", callback_data=f"intake:edit_stop:{cid}"),
    )
    kb.add(
        types.InlineKeyboardButton("🏷️ ערוך Setup", callback_data=f"intake:edit_setup:{cid}"),
        types.InlineKeyboardButton("🧠 הוסף קטליסט", callback_data=f"intake:catalyst:{cid}"),
    )
    kb.add(
        types.InlineKeyboardButton("⏭️ דלג כרגע", callback_data=f"intake:snooze:{cid}"),
        types.InlineKeyboardButton("🔄 רענן", callback_data=f"intake:view:{cid}"),
    )
    return kb

def _list_keyboard(items):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for task, plan, _ in items[:12]:
        cid = task.get("campaign_id") or plan.get("campaign_id")
        symbol = _first(plan, ["symbol"], _first(task, ["symbol"], cid))
        kb.add(types.InlineKeyboardButton(f"🧾 {symbol}", callback_data=f"intake:view:{cid}"))
    return kb

def _send_list(bot, chat_id, supabase):
    items = _get_pending_items(supabase)
    if not items:
        bot.send_message(chat_id, f"{RTL}🧾 אין כרגע תוכניות ניהול שממתינות לאישור.")
        return

    lines = [
        f"{RTL}🧾 תוכניות ניהול שממתינות לאישור",
        f"{RTL}{SEP}",
        f"{RTL}נמצאו {len(items)} קמפיינים פתוחים עם תוכנית ראשונית.",
        f"{RTL}לחצי על סימול כדי לאשר, לערוך סטופ/Setup, או להוסיף קטליסט.",
        "",
        f"{RTL}שימי לב: תמונת גרף נאספת בסגירת קמפיין, לא בפתיחה.",
    ]
    bot.send_message(chat_id, "\n".join(lines), reply_markup=_list_keyboard(items))

def _send_plan(bot, chat_id, supabase, campaign_id):
    task = {}
    for row in _get_task_rows(supabase):
        if row.get("campaign_id") == campaign_id:
            task = row
            break
    plan = _get_plan(supabase, campaign_id)
    if not plan and not task:
        bot.send_message(chat_id, f"{RTL}לא מצאתי תוכנית עבור הקמפיין הזה.")
        return
    bot.send_message(chat_id, _plan_text(task, plan), reply_markup=_plan_keyboard(campaign_id))

def register(bot, get_supabase, get_user_state):
    def supa():
        return get_supabase()

    def state():
        return get_user_state()

    @bot.message_handler(commands=["intake", "plans"])
    def _cmd_intake(message):
        _send_list(bot, message.chat.id, supa())

    @bot.message_handler(func=lambda m: (m.text or "").strip() in ["🧾 תוכניות ניהול", "תוכניות ניהול", "/intake", "/plans"])
    def _text_intake(message):
        _send_list(bot, message.chat.id, supa())

    @bot.message_handler(func=lambda m: state().get(str(m.chat.id), {}).get("flow", "").startswith("intake_"))
    def _flow_text(message):
        chat_id = message.chat.id
        key = str(chat_id)
        st = state().get(key, {})
        flow = st.get("flow")
        cid = st.get("campaign_id")
        text = (message.text or "").strip()

        if not cid:
            state().pop(key, None)
            bot.send_message(chat_id, f"{RTL}הפעולה בוטלה כי חסר מזהה קמפיין.")
            return

        if flow == "intake_edit_stop":
            val = text.replace("$", "").replace(",", "").strip()
            try:
                stop = float(val)
            except Exception:
                bot.send_message(chat_id, f"{RTL}לא הצלחתי לקרוא את הסטופ. שלחי מספר בלבד, לדוגמה: 133.50")
                return

            s, item = _campaign_state(cid)
            item["stop_override"] = stop
            item["status"] = "pending_review"
            _save_state(s)
            _event(cid, "edit_stop", {"stop": stop})

            _safe_update(supa(), "campaign_plans", "campaign_id", cid, [
                {"user_initial_stop_price": stop, "plan_review_status": "edited", "updated_at": _now()},
                {"initial_stop_price": stop, "plan_status": "pending_review", "updated_at": _now()},
                {"stop_price": stop, "updated_at": _now()},
            ])

            state().pop(key, None)
            bot.send_message(chat_id, f"{RTL}✅ הסטופ עודכן ל־{_money(stop)}.")
            _send_plan(bot, chat_id, supa(), cid)
            return

        if flow == "intake_setup_other":
            setup = text[:60]
            s, item = _campaign_state(cid)
            item["setup_override"] = setup
            item["status"] = "pending_review"
            _save_state(s)
            _event(cid, "edit_setup_other", {"setup": setup})

            _safe_update(supa(), "campaign_plans", "campaign_id", cid, [
                {"user_setup_type": setup, "plan_review_status": "edited", "updated_at": _now()},
                {"setup_type": setup, "plan_status": "pending_review", "updated_at": _now()},
            ])

            state().pop(key, None)
            bot.send_message(chat_id, f"{RTL}✅ ה־Setup עודכן ל־{setup}.")
            _send_plan(bot, chat_id, supa(), cid)
            return

        if flow == "intake_catalyst":
            if text.lower() in ["דלג", "skip"]:
                catalyst = None
                msg = "דילגתי על קטליסט."
            else:
                catalyst = text[:500]
                msg = "הקטליסט נשמר."

            s, item = _campaign_state(cid)
            if catalyst:
                item["catalyst"] = catalyst
            item["status"] = "pending_review"
            _save_state(s)
            _event(cid, "catalyst", {"catalyst": catalyst})

            if catalyst:
                _safe_update(supa(), "campaign_plans", "campaign_id", cid, [
                    {"catalyst": catalyst, "plan_review_status": "edited", "updated_at": _now()},
                    {"user_notes": catalyst, "updated_at": _now()},
                ])

            state().pop(key, None)
            bot.send_message(chat_id, f"{RTL}✅ {msg}")
            _send_plan(bot, chat_id, supa(), cid)
            return

    @bot.callback_query_handler(func=lambda call: (call.data or "").startswith("intake:"))
    def _callback(call):
        data = call.data or ""
        parts = data.split(":")
        action = parts[1] if len(parts) > 1 else ""
        cid = parts[2] if len(parts) > 2 else ""
        chat_id = call.message.chat.id

        if not cid:
            _safe_answer(bot, call, "חסר קמפיין")
            return

        if action == "view":
            _safe_answer(bot, call)
            _send_plan(bot, chat_id, supa(), cid)
            return

        if action == "approve":
            s, item = _campaign_state(cid)
            item["status"] = "approved"
            item["approved_at"] = _now()
            _save_state(s)
            _event(cid, "approve_plan", {})

            _safe_update(supa(), "campaign_plans", "campaign_id", cid, [
                {"plan_status": "approved", "approved_at": _now(), "updated_at": _now()},
                {"plan_review_status": "approved", "reviewed_at": _now(), "updated_at": _now()},
                {"status": "approved", "updated_at": _now()},
            ])
            _safe_update(supa(), "campaign_intake_tasks", "campaign_id", cid, [
                {"task_status": "completed", "completed_at": _now(), "updated_at": _now()},
                {"status": "completed", "completed_at": _now(), "updated_at": _now()},
            ])

            _safe_answer(bot, call, "אושר")
            bot.send_message(chat_id, f"{RTL}✅ תוכנית הניהול אושרה.\nהיא תיכנס ליומן כבסיס ניהול הקמפיין.")
            return

        if action == "snooze":
            s, item = _campaign_state(cid)
            item["status"] = "skipped"
            item["snooze_until"] = (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()
            _save_state(s)
            _event(cid, "snooze_plan", {"hours": 8})
            _safe_answer(bot, call, "הושתק זמנית")
            bot.send_message(chat_id, f"{RTL}⏭️ דילגתי כרגע.\nהתוכנית לא אושרה, והיא תוכל לחזור בהמשך.")
            return

        if action == "edit_stop":
            state()[str(chat_id)] = {"flow": "intake_edit_stop", "campaign_id": cid}
            _safe_answer(bot, call)
            bot.send_message(chat_id, f"{RTL}✏️ שלחי סטופ חדש לקמפיין.\nסטופ = המקום שבו אם אני טועה, אני יוצא. זה שדה חובה לניהול סיכון אמיתי.")
            return

        if action == "edit_setup":
            kb = types.InlineKeyboardMarkup(row_width=2)
            for setup in ["EP", "VCP", "ALGO", "SWING"]:
                kb.add(types.InlineKeyboardButton(setup, callback_data=f"intake:set_setup:{cid}:{setup}"))
            kb.add(types.InlineKeyboardButton("אחר", callback_data=f"intake:set_setup_other:{cid}"))
            _safe_answer(bot, call)
            bot.send_message(chat_id, f"{RTL}🏷️ בחרי Setup.\nSetup = סוג הרעיון/השיטה, כדי שהסטטיסטיקה תימדד נכון.", reply_markup=kb)
            return

        if action == "set_setup":
            setup = parts[3] if len(parts) > 3 else ""
            s, item = _campaign_state(cid)
            item["setup_override"] = setup
            item["status"] = "pending_review"
            _save_state(s)
            _event(cid, "edit_setup", {"setup": setup})

            _safe_update(supa(), "campaign_plans", "campaign_id", cid, [
                {"user_setup_type": setup, "plan_review_status": "edited", "updated_at": _now()},
                {"setup_type": setup, "plan_status": "pending_review", "updated_at": _now()},
            ])

            _safe_answer(bot, call, "עודכן")
            bot.send_message(chat_id, f"{RTL}✅ ה־Setup עודכן ל־{setup}.")
            _send_plan(bot, chat_id, supa(), cid)
            return

        if action == "set_setup_other":
            state()[str(chat_id)] = {"flow": "intake_setup_other", "campaign_id": cid}
            _safe_answer(bot, call)
            bot.send_message(chat_id, f"{RTL}כתבי שם Setup חדש.\nלדוגמה: Pullback, Earnings Gap, Re-entry.")
            return

        if action == "catalyst":
            state()[str(chat_id)] = {"flow": "intake_catalyst", "campaign_id": cid}
            _safe_answer(bot, call)
            bot.send_message(chat_id, f"{RTL}🧠 כתבי קטליסט, או שלחי 'דלג'.\nקטליסט = הסיבה שהמניה מעניינת: דוח, חוזה, Guidance, אנליסט, מומנטום חריג.")
            return

        _safe_answer(bot, call, "פעולה לא מוכרת")
