import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import BOT_TOKEN, ADMIN_IDS, STORE_NAME
from catalog import PRODUCTS
from db import (
    init_db, register_customer, add_order, get_order, confirm_payment,
    reject_payment, get_orders, get_customers, get_dashboard_stats,
    add_account, get_accounts, get_account, request_account,
    get_account_requests, set_account_status, save_support_message
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hamo-store")
pending = {}
support_mode = set()
reply_targets = {}

CASH_NUMBERS = ["01031921290", "01091924865"]

def is_admin(uid):
    return uid in ADMIN_IDS

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def home():
    return kb([
        [InlineKeyboardButton(text="🪙 شحن العملات", callback_data="catalog")],
        [InlineKeyboardButton(text="🎮 حسابات PUBG", callback_data="accounts:pubg")],
        [InlineKeyboardButton(text="🎵 حسابات TikTok", callback_data="accounts:tiktok")],
        [InlineKeyboardButton(text="📞 الدعم", callback_data="support")]
    ])

def admin_keyboard():
    return kb([
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📦 الطلبات", callback_data="admin:orders"),
         InlineKeyboardButton(text="⏳ المعلقة", callback_data="admin:pending")],
        [InlineKeyboardButton(text="👥 العملاء", callback_data="admin:customers")],
        [InlineKeyboardButton(text="➕ إضافة حساب", callback_data="acctadmin:add")],
        [InlineKeyboardButton(text="🎮 PUBG", callback_data="acctadmin:pubg"),
         InlineKeyboardButton(text="🎵 TikTok", callback_data="acctadmin:tiktok")],
        [InlineKeyboardButton(text="📨 طلبات الحسابات", callback_data="acctadmin:requests")],
        [InlineKeyboardButton(text="📢 رسالة جماعية", callback_data="broadcast")]
    ])

def cancel_markup():
    return kb([[InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")]])

def with_cancel(rows):
    return kb(rows + [[InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")]])

def payment_methods():
    return with_cancel([
        [InlineKeyboardButton(text="📱 فودافون كاش", callback_data="pay:vodafone")],
        [InlineKeyboardButton(text="💳 إنستا باي", callback_data="pay:instapay")]
    ])

def recipient_numbers_keyboard():
    return with_cancel([
        [InlineKeyboardButton(text=f"📱 {CASH_NUMBERS[0]}", callback_data="recipient:0")],
        [InlineKeyboardButton(text=f"📱 {CASH_NUMBERS[1]}", callback_data="recipient:1")]
    ])

def receipt_buttons(oid, uid):
    return kb([[InlineKeyboardButton(text="✅ تأكيد بعد التحقق", callback_data=f"approve:{oid}:{uid}"),
                InlineKeyboardButton(text="❌ رفض الدفع", callback_data=f"reject:{oid}:{uid}")]])

def account_buttons(aid):
    return with_cancel([[InlineKeyboardButton(text="🛒 اطلب الحساب", callback_data=f"buyacc:{aid}")]])

def account_admin_buttons(aid, status):
    if status == "available":
        return kb([[InlineKeyboardButton(text="✅ مباع", callback_data=f"accsold:{aid}"),
                    InlineKeyboardButton(text="🙈 إخفاء", callback_data=f"acchide:{aid}")]])
    return kb([[InlineKeyboardButton(text="♻️ إتاحته للبيع", callback_data=f"accavailable:{aid}")]])

async def notify_admins(bot, text, **kwargs):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, text, **kwargs)
        except Exception:
            log.exception("Admin notification failed for %s", aid)

async def start(message: Message):
    pending.pop(message.from_user.id, None)
    support_mode.discard(message.from_user.id)
    await register_customer(message.from_user.id, message.from_user.username)
    await message.answer(
        f"🖤 أهلاً بك في {STORE_NAME}\nمتجر شحن العملات وبيع الحسابات\n\nاختار الخدمة:",
        reply_markup=home())


async def on_cancel(c: CallbackQuery):
    uid = c.from_user.id
    pending.pop(uid, None)
    support_mode.discard(uid)
    reply_targets.pop(uid, None)
    await c.answer("تم إلغاء العملية.")
    await c.message.answer(
        f"❌ تم إلغاء العملية الحالية.\n\n🖤 أهلاً بك في {STORE_NAME}\nاختار الخدمة:",
        reply_markup=home()
    )

async def on_catalog(c: CallbackQuery):
    rows = []
    for p in PRODUCTS.values():
        if int(p["price"]) <= 0:
            continue
        rows.append([InlineKeyboardButton(
            text=f'{p["coins"]:,} عملة — {p["price"]} جنيه',
            callback_data=f'buy:{p["code"]}')])
    if not rows:
        await c.answer("الباقات غير مفعلة. راجع أسعار app/catalog.py", show_alert=True)
    else:
        await c.message.answer("🪙 اختر باقة الشحن:", reply_markup=with_cancel(rows))
        await c.answer()

async def on_buy(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    if code not in PRODUCTS or int(PRODUCTS[code]["price"]) <= 0:
        await c.answer("الباقة غير متاحة حالياً.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "tiktok_id", "code": code}
    await c.message.answer("أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:", reply_markup=cancel_markup())
    await c.answer()

async def on_accounts(c: CallbackQuery):
    category = c.data.split(":")[1]
    accounts = await get_accounts(category)
    name = "PUBG Mobile" if category == "pubg" else "TikTok"
    if not accounts:
        await c.message.answer(f"📭 لا توجد حسابات {name} متاحة حالياً.")
    else:
        await c.message.answer(f"🔥 الحسابات المتاحة - {name}")
        for a in accounts:
            caption = f"🎮 {a[2]}\n\n📝 {a[3] or 'لا يوجد وصف'}\n💰 السعر: {a[4]} جنيه"
            if a[5]:
                await c.message.answer_photo(a[5], caption=caption, reply_markup=account_buttons(a[0]))
            else:
                await c.message.answer(caption, reply_markup=account_buttons(a[0]))
    await c.answer()

async def on_buy_account(c: CallbackQuery):
    try:
        aid = int(c.data.split(":")[1])
        a = await get_account(aid)
        if not a or a[6] != "available":
            await c.answer("الحساب لم يعد متاحاً.", show_alert=True)
            return
        rid = await request_account(aid, c.from_user.id, c.from_user.username)
        if rid is None:
            await c.answer("الحساب لم يعد متاحاً.", show_alert=True)
            return
        await c.message.answer(f"✅ استلمنا طلبك رقم #{rid} للحساب {a[2]} بسعر {a[4]} جنيه. الإدارة هتتواصل معاك.")
        await notify_admins(c.bot,
            f"🛒 طلب حساب جديد #{rid}\nالحساب: {a[2]}\nالسعر: {a[4]} جنيه\nالعميل: {c.from_user.id}\nUsername: @{c.from_user.username or 'غير متوفر'}",
            reply_markup=kb([[InlineKeyboardButton(text="📩 مراسلة العميل", callback_data=f"reply:{c.from_user.id}")],
                             [InlineKeyboardButton(text="✅ تحديد كمباع", callback_data=f"accsold:{aid}")]]))
        await c.answer("تم إرسال الطلب.")
    except Exception:
        log.exception("Account request failed")
        await c.answer("حصل خطأ، حاول مرة أخرى.", show_alert=True)

async def on_support(c: CallbackQuery):
    support_mode.add(c.from_user.id)
    await c.message.answer("📞 اكتب رسالتك هنا، وسيتم إرسالها للإدارة:", reply_markup=cancel_markup())
    await c.answer()

async def on_admin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    section = c.data.split(":")[1]
    if section == "stats":
        s = await get_dashboard_stats()
        await c.message.answer(
            f"📊 الإحصائيات\nالطلبات: {s['orders']}\nالمعلقة: {s['pending']}\nالمدفوعة: {s['paid']}\nالعملاء: {s['customers']}\nالحسابات: {s['accounts']}")
    elif section in ("orders", "pending"):
        orders = await get_orders(40, "pending" if section == "pending" else None)
        if not orders:
            await c.message.answer("لا توجد طلبات.")
        for o in orders:
            await c.message.answer(
                f"طلب #{o[0]}\nالعميل: {o[1]}\nTikTok: @{o[3]}\nالكمية: {o[5]} Coins\nالسعر: {o[6]} جنيه\nالدفع: {o[7]}\nالحالة: {o[9]}",
                reply_markup=receipt_buttons(o[0], o[1]) if o[9] == "pending" else None)
    elif section == "customers":
        customers = await get_customers(1000)
        await c.message.answer(f"👥 عدد العملاء المسجلين: {len(customers)}")
    await c.answer()

async def on_acctadmin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    section = c.data.split(":")[1]
    if section == "add":
        pending[c.from_user.id] = {"step":"account_category"}
        await c.message.answer("اكتب نوع الحساب: pubg أو tiktok", reply_markup=cancel_markup())
    elif section == "requests":
        reqs = await get_account_requests(40)
        if not reqs:
            await c.message.answer("لا توجد طلبات شراء حسابات.")
        for r in reqs:
            await c.message.answer(
                f"طلب حساب #{r[0]}\nالحساب: {r[7]}\nالنوع: {r[6]}\nالسعر: {r[8]} جنيه\nالعميل: {r[2]}\nالحالة: {r[4]}",
                reply_markup=with_cancel([[InlineKeyboardButton(text="📩 مراسلة العميل", callback_data=f"reply:{r[2]}")]]))
    else:
        accounts = await get_accounts(section, available_only=False)
        if not accounts:
            await c.message.answer("لا توجد حسابات في هذا القسم.")
        for a in accounts:
            text = f"#{a[0]} — {a[2]}\nالسعر: {a[4]} جنيه\nالحالة: {a[6]}"
            if a[5]:
                await c.message.answer_photo(a[5], caption=text, reply_markup=account_admin_buttons(a[0], a[6]))
            else:
                await c.message.answer(text, reply_markup=account_admin_buttons(a[0], a[6]))
    await c.answer()

async def on_account_status(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    action, raw = c.data.split(":")
    status = {"accsold":"sold", "acchide":"hidden", "accavailable":"available"}[action]
    await set_account_status(int(raw), status)
    await c.answer("تم تحديث حالة الحساب.")
    await c.message.answer("✅ تم تحديث حالة الحساب.")

async def on_payment(c: CallbackQuery):
    data = pending.get(c.from_user.id)
    if not data or data.get("step") != "payment":
        await c.answer("ابدأ طلب شحن جديد.", show_alert=True)
        return
    method = c.data.split(":")[1]
    data["payment_method"] = "فودافون كاش" if method == "vodafone" else "إنستا باي"
    data["step"] = "recipient"
    await c.message.answer(
        "اختار الرقم اللي هتحوّل عليه المبلغ، وبعد التحويل ابعت صورة الإيصال:",
        reply_markup=recipient_numbers_keyboard()
    )
    await c.answer()


async def on_recipient(c: CallbackQuery):
    data = pending.get(c.from_user.id)
    if not data or data.get("step") != "recipient":
        await c.answer("ابدأ طلب شحن جديد.", show_alert=True)
        return
    try:
        index = int(c.data.split(":")[1])
        recipient = CASH_NUMBERS[index]
    except (ValueError, IndexError):
        await c.answer("اختيار غير صحيح.", show_alert=True)
        return
    data["recipient_number"] = recipient
    data["step"] = "receipt"
    await c.message.answer(
        f"حوّل المبلغ إلى الرقم المحدد فقط:\n📱 {recipient}\n\n"
        "بعد التحويل أرسل صورة الإيصال هنا. الإدارة هتراجع وصول المبلغ "
        "يدويًا على الرقم ده قبل تأكيد الطلب.",
        reply_markup=cancel_markup()
    )
    await c.answer("تم تحديد رقم التحويل.")


async def on_approval(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    action, oid_s, uid_s = c.data.split(":")
    oid, uid = int(oid_s), int(uid_s)
    order = await get_order(oid)
    if not order or order[9] != "pending":
        await c.answer("الطلب غير موجود أو تمت مراجعته.", show_alert=True)
        return
    if action == "approve":
        await confirm_payment(oid)
        status_text = "تم تأكيد الدفع بنجاح."
        customer_text = f"✅ تم تأكيد الدفع للطلب #{oid}. سيتم تنفيذ طلبك."
    else:
        await reject_payment(oid)
        status_text = "تم رفض الإيصال."
        customer_text = f"❌ تم رفض إيصال الطلب #{oid}. تواصل مع الدعم للمراجعة."
    try:
        await c.bot.send_message(uid, customer_text)
    except Exception:
        pass
    await c.message.answer(status_text)
    await c.answer("تم تحديث الطلب.")

async def on_reply(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    uid = int(c.data.split(":")[1])
    reply_targets[c.from_user.id] = uid
    await c.message.answer(f"اكتب رسالتك للعميل {uid}:", reply_markup=cancel_markup())
    await c.answer()

async def on_broadcast(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    pending[c.from_user.id] = {"step":"broadcast"}
    await c.message.answer("أرسل نص الإعلان الجماعي الآن:", reply_markup=cancel_markup())
    await c.answer()

async def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()
    if txt == "/cancel":
        pending.pop(uid, None)
        support_mode.discard(uid)
        reply_targets.pop(uid, None)
        await m.answer("تم الإلغاء.")
        return

    if uid in reply_targets and is_admin(uid):
        customer_id = reply_targets.pop(uid)
        try:
            await m.bot.send_message(customer_id, f"📩 رسالة من إدارة HAMO STORE:\n\n{txt}")
            await save_support_message(customer_id, txt, "admin", uid)
            await m.answer("✅ تم إرسال الرد للعميل.")
        except Exception:
            await m.answer("تعذر إرسال الرسالة لهذا العميل.")
        return

    data = pending.get(uid)
    if data:
        step = data.get("step")
        if step == "broadcast" and is_admin(uid):
            customers = await get_customers(100000)
            sent = failed = 0
            for customer_id, _ in customers:
                try:
                    await m.bot.send_message(customer_id, f"📢 HAMO STORE\n\n{txt}")
                    sent += 1
                except (TelegramForbiddenError, TelegramBadRequest):
                    failed += 1
                except Exception:
                    failed += 1
            pending.pop(uid, None)
            await m.answer(f"انتهى الإرسال.\nتم الإرسال: {sent}\nتعذر الإرسال: {failed}")
            return
        if step == "account_category" and is_admin(uid):
            category = txt.lower()
            if category not in ("pubg", "tiktok"):
                await m.answer("اكتب pubg أو tiktok فقط.", reply_markup=cancel_markup())
                return
            data.update(step="account_title", category=category)
            await m.answer("اكتب اسم أو عنوان الحساب:", reply_markup=cancel_markup())
            return
        if step == "account_title":
            data.update(step="account_description", title=txt)
            await m.answer("اكتب وصف الحساب أو اكتب: بدون", reply_markup=cancel_markup())
            return
        if step == "account_description":
            data.update(step="account_price", description="" if txt == "بدون" else txt)
            await m.answer("اكتب السعر بالجنيه المصري (أرقام فقط):", reply_markup=cancel_markup())
            return
        if step == "account_price":
            try:
                price = int(txt)
                if price <= 0: raise ValueError
            except ValueError:
                await m.answer("اكتب سعراً صحيحاً أكبر من صفر.")
                return
            data.update(step="account_photo", price=price)
            await m.answer("أرسل صورة الحساب أو اكتب تخطي:", reply_markup=cancel_markup())
            return
        if step == "account_photo":
            if txt != "تخطي":
                await m.answer("أرسل صورة أو اكتب تخطي.")
                return
            await finish_account(m, data, None)
            return
        if step == "tiktok_id":
            target = txt.lstrip("@")
            if not 2 <= len(target) <= 64:
                await m.answer("TikTok ID غير صحيح، حاول مرة أخرى.")
                return
            data.update(step="payment", tiktok_id=target)
            p = PRODUCTS[data["code"]]
            await m.answer(f"الحساب: @{target}\nالباقة: {p['coins']} كوين\nالسعر: {p['price']} جنيه\nاختر وسيلة الدفع:", reply_markup=payment_methods())
            return
    if uid in support_mode:
        support_mode.discard(uid)
        await save_support_message(uid, txt, "customer")
        await notify_admins(m.bot, f"📞 رسالة دعم جديدة\nالعميل: {uid}\nUsername: @{m.from_user.username or 'غير متوفر'}\n\n{txt}",
            reply_markup=kb([[InlineKeyboardButton(text="↩️ الرد على العميل", callback_data=f"reply:{uid}")]]))
        await m.answer("✅ وصلت رسالتك للإدارة.")
        return

async def finish_account(m, data, photo_id):
    try:
        aid = await add_account(data["category"], data["title"], data["description"], data["price"], photo_id)
        pending.pop(m.from_user.id, None)
        await m.answer(f"✅ تمت إضافة الحساب بنجاح. رقم الحساب: #{aid}")
    except Exception:
        log.exception("Could not save account")
        await m.answer("حدث خطأ أثناء إضافة الحساب.")

async def on_photo(m: Message):
    data = pending.get(m.from_user.id)
    photo_id = m.photo[-1].file_id
    if data and data.get("step") == "account_photo":
        await finish_account(m, data, photo_id)
        return
    if not data or data.get("step") != "receipt":
        return
    p = PRODUCTS[data["code"]]
    try:
        oid = await add_order(m.from_user.id, m.from_user.username, data["tiktok_id"], p, data["payment_method"], photo_id)
        pending.pop(m.from_user.id, None)
        await m.answer(f"✅ تم استلام الإيصال. رقم الطلب: #{oid}\nالحالة: بانتظار مراجعة الإدارة.")
        caption = (f"🧾 طلب جديد #{oid}\\nالعميل: {m.from_user.id}\\n"
                   f"Username: @{m.from_user.username or 'غير متوفر'}\\nTikTok: @{data['tiktok_id']}\\n"
                   f"الباقة: {p['coins']} Coins\\nالسعر: {p['price']} جنيه\\nالدفع: {data['payment_method']}\\n"
                   f"📌 رقم التحويل المختار: {data.get('recipient_number', 'غير محدد')}\\n"
                   "⚠️ راجع سجل التحويل على الرقم المحدد. لا تضغط تأكيد إلا بعد التأكد من وصول المبلغ.")
        for aid in ADMIN_IDS:
            try:
                await m.bot.send_photo(aid, photo_id, caption=caption,
                                       reply_markup=receipt_buttons(oid, m.from_user.id))
            except Exception:
                log.exception("Receipt notification failed")
    except Exception:
        log.exception("Receipt processing failed")
        await m.answer("حدث خطأ أثناء تسجيل الإيصال. حاول مرة أخرى.")

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير مضبوط في Environment Variables")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS غير مضبوط. ضع Telegram user ID واحداً على الأقل.")
    await init_db()
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.message.register(admin_start, Command("admin"))
    dp.message.register(on_photo, F.photo)
    dp.message.register(on_text, F.text)

    dp.callback_query.register(on_cancel, F.data == "cancel")
    dp.callback_query.register(on_catalog, F.data == "catalog")
    dp.callback_query.register(on_buy, F.data.startswith("buy:"))
    dp.callback_query.register(on_accounts, F.data.startswith("accounts:"))
    dp.callback_query.register(on_buy_account, F.data.startswith("buyacc:"))
    dp.callback_query.register(on_support, F.data == "support")
    dp.callback_query.register(on_admin, F.data.startswith("admin:"))
    dp.callback_query.register(on_acctadmin, F.data.startswith("acctadmin:"))
    dp.callback_query.register(on_account_status, F.data.startswith(("accsold:", "acchide:", "accavailable:")))
    dp.callback_query.register(on_payment, F.data.startswith("pay:"))
    dp.callback_query.register(on_recipient, F.data.startswith("recipient:"))
    dp.callback_query.register(on_approval, F.data.startswith(("approve:", "reject:")))
    dp.callback_query.register(on_reply, F.data.startswith("reply:"))
    dp.callback_query.register(on_broadcast, F.data == "broadcast")

    log.info("%s is running", STORE_NAME)
    try:
        await dp.start_polling(bot, close_bot_session=True)
    finally:
        await bot.session.close()

async def admin_start(m: Message):
    if not is_admin(m.from_user.id):
        return
    pending.pop(m.from_user.id, None)
    await m.answer("🛠️ HAMO STORE — لوحة الإدارة", reply_markup=admin_keyboard())

if __name__ == "__main__":
    asyncio.run(main())
