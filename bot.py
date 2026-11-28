import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from config import BOT_TOKEN, ADMIN_IDS, STORE_NAME, DB_PATH
from catalog import PRODUCTS, UC_PRODUCTS
from db import (
    init_db, register_customer, add_order, get_order, confirm_payment,
    reject_payment, get_orders, get_customers, get_dashboard_stats,
    add_account, get_accounts, get_account, request_account,
    get_account_requests, set_account_status, save_support_message,
    add_account_submission, get_pending_account_submissions, review_account_submission,
    init_product_prices, get_product_prices, set_product_price,
    init_product_statuses, get_product_statuses, set_product_status,
    add_custom_product, get_custom_products, delete_custom_product
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
        [InlineKeyboardButton(text="🪙 شحن عملات TikTok", callback_data="catalog")],
        [InlineKeyboardButton(text="🎮 شحن شدات PUBG UC", callback_data="uc_catalog")],
        [InlineKeyboardButton(text="🎮 حسابات PUBG", callback_data="accounts:pubg")],
        [InlineKeyboardButton(text="🎵 حسابات TikTok", callback_data="accounts:tiktok")],
        [InlineKeyboardButton(text="💼 اعرض حسابك للبيع", callback_data="sellaccount")],
        [InlineKeyboardButton(text="🤖 اطلب بوت لمتجرك", callback_data="botstore")],
        [InlineKeyboardButton(text="📞 الدعم", callback_data="support")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")]
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
        [InlineKeyboardButton(text="📝 مراجعة عروض العملاء", callback_data="acctadmin:submissions")],
        [InlineKeyboardButton(text="💰 تعديل أسعار الشحن", callback_data="admin:prices")],
        [InlineKeyboardButton(text="🧰 إدارة المنتجات", callback_data="admin:products")],
        [InlineKeyboardButton(text="📢 رسالة جماعية", callback_data="broadcast")]
    ])

def cancel_markup():
    return kb([
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")]
    ])

def with_cancel(rows):
    return kb(rows + [
        [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="home")],
        [InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel")]
    ])

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


async def on_home(c: CallbackQuery):
    uid = c.from_user.id
    pending.pop(uid, None)
    support_mode.discard(uid)
    reply_targets.pop(uid, None)
    await c.answer()
    await c.message.answer(
        f"🖤 أهلاً بك في {STORE_NAME}\nاختار الخدمة:",
        reply_markup=home()
    )


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
        if int(p["price"]) <= 0 or not PRODUCT_STATUS.get(p["code"], True):
            continue
        rows.append([InlineKeyboardButton(
            text=f'{p["coins"]:,} عملة — {p["price"]} جنيه',
            callback_data=f'buy:{p["code"]}')])
    if not rows:
        await c.answer("الباقات غير مفعلة. راجع أسعار app/catalog.py", show_alert=True)
    else:
        await c.message.answer("🪙 اختر باقة الشحن:", reply_markup=with_cancel(rows))
        await c.answer()

async def on_uc_catalog(c: CallbackQuery):
    rows = []
    for p in UC_PRODUCTS.values():
        if not PRODUCT_STATUS.get(p["code"], True):
            continue
        rows.append([InlineKeyboardButton(
            text=f"{p['coins']:,} UC — {p['price']} جنيه",
            callback_data=f"buyuc:{p['code']}")])
    await c.message.answer("🎮 اختر باقة شدات PUBG Mobile:", reply_markup=with_cancel(rows))
    await c.answer()


async def on_buy_uc(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    if code not in UC_PRODUCTS or not PRODUCT_STATUS.get(code, True):
        await c.answer("الباقة غير متاحة حالياً.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "pubg_id", "code": code, "service": "pubg_uc"}
    await c.message.answer(
        "🎮 أرسل Player ID الخاص بحساب PUBG Mobile بدقة، وتأكد منه قبل الإرسال:",
        reply_markup=cancel_markup()
    )
    await c.answer()


async def on_buy(c: CallbackQuery):
    code = c.data.split(":", 1)[1]
    if code not in PRODUCTS or int(PRODUCTS[code]["price"]) <= 0 or not PRODUCT_STATUS.get(code, True):
        await c.answer("الباقة غير متاحة حالياً.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "tiktok_id", "code": code}
    await c.message.answer("أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:", reply_markup=cancel_markup())
    await c.answer()

async def on_accounts(c: CallbackQuery):
    category = c.data.split(":")[1].strip().lower()
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

async def on_sell_account(c: CallbackQuery):
    pending[c.from_user.id] = {"step": "sell_category"}
    await c.message.answer(
        "💼 اعرض حسابك للبيع على HAMO STORE\n\nاختار نوع الحساب بكتابة pubg أو tiktok:",
        reply_markup=cancel_markup()
    )
    await c.answer()

async def on_sell_submission_review(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    action, raw_id = c.data.split(":")
    result = await review_account_submission(int(raw_id), approve=(action == "sellapprove"))
    if not result:
        await c.answer("العرض غير موجود أو تمت مراجعته بالفعل.", show_alert=True)
        return
    uid = result["user_id"]
    if action == "sellapprove":
        message = f"🎉 تمت الموافقة على عرض حسابك!\nرقم الحساب في المتجر: #{result['account_id']}\nأصبح متاحاً للعملاء."
        await c.message.answer(f"✅ تمت الموافقة على العرض وإضافته للمتجر برقم #{result['account_id']}.")
    else:
        message = "نعتذر، لم تتم الموافقة على عرض حسابك للبيع. يمكنك التواصل مع الدعم لمعرفة التفاصيل."
        await c.message.answer("تم رفض العرض.")
    try:
        await c.bot.send_message(uid, message)
    except Exception:
        log.exception("Could not notify account seller %s", uid)
    await c.answer("تمت مراجعة العرض.")

BOT_PACKAGES = {
    "basic": ("الباقة الأساسية", 3000, "بوت متجر جاهز بالهوية الأساسية وقائمة خدمات وطلبات العملاء"),
    "pro": ("الباقة الاحترافية", 6000, "كل مميزات الأساسية مع لوحة إدارة وإدارة الطلبات والعملاء"),
    "vip": ("باقة VIP", 10000, "تخصيص متقدم للمتجر ومزايا إضافية حسب الاتفاق")
}

async def on_botstore(c: CallbackQuery):
    rows = [
        [InlineKeyboardButton(text="🥉 الأساسية — 3,000 جنيه", callback_data="botpackage:basic")],
        [InlineKeyboardButton(text="🥈 الاحترافية — 6,000 جنيه", callback_data="botpackage:pro")],
        [InlineKeyboardButton(text="🥇 VIP — 10,000 جنيه", callback_data="botpackage:vip")]
    ]
    await c.message.answer(
        "🤖 خدمات تصميم وبيع بوتات المتاجر من HAMO STORE\\n\\n"
        "اختار الباقة المناسبة، وبعدها هنجمع بيانات طلبك ونتواصل معاك لتأكيد التفاصيل والسعر النهائي.",
        reply_markup=with_cancel(rows)
    )
    await c.answer()

async def on_bot_package(c: CallbackQuery):
    key = c.data.split(":", 1)[1]
    package = BOT_PACKAGES.get(key)
    if not package:
        await c.answer("الباقة غير متاحة.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "botstore_name", "package": key}
    await c.message.answer(
        f"✅ اخترت {package[0]} بسعر مبدئي {package[1]:,} جنيه.\\n"
        f"{package[2]}\\n\\n"
        "اكتب اسمك أو اسم المتجر:",
        reply_markup=cancel_markup()
    )
    await c.answer()

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
    elif section == "products":
        rows = []
        for p in PRODUCTS.values():
            enabled = PRODUCT_STATUS.get(p["code"], True)
            label = "🟢 ظاهر" if enabled else "⚫ مخفي"
            rows.append([InlineKeyboardButton(text=f"{label} | TikTok {p['coins']:,} عملة", callback_data=f"producttoggle:{p['code']}")])
        for p in UC_PRODUCTS.values():
            enabled = PRODUCT_STATUS.get(p["code"], True)
            label = "🟢 ظاهر" if enabled else "⚫ مخفي"
            rows.append([InlineKeyboardButton(text=f"{label} | PUBG {p['coins']:,} UC", callback_data=f"producttoggle:{p['code']}")])
        for p in list(PRODUCTS.values()) + list(UC_PRODUCTS.values()):
            rows.append([InlineKeyboardButton(text=f"🗑 حذف {p['coins']:,} ({'TikTok' if p['code'] in PRODUCTS else 'PUBG'})", callback_data=f"productdelete:{p['code']}")])
        rows.insert(0, [InlineKeyboardButton(text="➕ إضافة باقة جديدة", callback_data="productadd")])
        await c.message.answer("🧰 إدارة المنتجات\nاضغط على ظاهر/مخفي لتغيير العرض. للحذف اضغط زر الحذف ثم أكد. الطلبات القديمة تظل محفوظة.", reply_markup=with_cancel(rows))
    elif section == "prices":
        rows = []
        for p in PRODUCTS.values():
            rows.append([InlineKeyboardButton(text=f"🪙 TikTok {p['coins']:,} — {p['price']} جنيه", callback_data=f"price:{p['code']}")])
        for p in UC_PRODUCTS.values():
            rows.append([InlineKeyboardButton(text=f"🎮 PUBG {p['coins']:,} UC — {p['price']} جنيه", callback_data=f"price:{p['code']}")])
        await c.message.answer("💰 اختار الباقة اللي عايز تعدل سعرها:", reply_markup=with_cancel(rows))
    await c.answer()

async def on_acctadmin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    section = c.data.split(":")[1]
    if section == "add":
        pending[c.from_user.id] = {"step":"account_category"}
        await c.message.answer("اكتب نوع الحساب: pubg أو tiktok", reply_markup=cancel_markup())
    elif section == "submissions":
        submissions = await get_pending_account_submissions(40)
        if not submissions:
            await c.message.answer("لا توجد عروض حسابات جديدة للمراجعة.")
        for s in submissions:
            sid, seller_id, username, category, title, description, price, photo_id, status = s
            category_name = "TikTok" if category == "tiktok" else "PUBG"
            caption = (f"📝 عرض حساب للبيع #{sid}\nالنوع: {category_name}\n"
                       f"العنوان: {title}\nالوصف: {description or 'بدون وصف'}\n"
                       f"السعر المطلوب: {price} جنيه\nالبائع: {seller_id}\n"
                       f"Username: @{username or 'غير متوفر'}\n\n"
                       "راجع العرض قبل الموافقة؛ الموافقة ستنشره مباشرة في المتجر.")
            markup = kb([[InlineKeyboardButton(text="✅ موافقة ونشر", callback_data=f"sellapprove:{sid}"),
                          InlineKeyboardButton(text="❌ رفض", callback_data=f"sellreject:{sid}")]])
            if photo_id:
                await c.message.answer_photo(photo_id, caption=caption, reply_markup=markup)
            else:
                await c.message.answer(caption, reply_markup=markup)
    elif section == "requests":
        reqs = await get_account_requests(40)
        if not reqs:
            await c.message.answer("لا توجد طلبات شراء حسابات.")
        for r in reqs:
            await c.message.answer(
                f"طلب حساب #{r[0]}\nالحساب: {r[7]}\nالنوع: {r[6]}\nالسعر: {r[8]} جنيه\nالعميل: {r[2]}\nالحالة: {r[4]}",
                reply_markup=with_cancel([[InlineKeyboardButton(text="📩 مراسلة العميل", callback_data=f"reply:{r[2]}")]]))
    else:
        section = section.strip().lower()
        accounts = await get_accounts(section, available_only=False)
        if not accounts:
            await c.message.answer("لا توجد حسابات في هذا القسم. لو كنت أضفت حساباً ولم يظهر، راجع سجل Render للتأكد من قاعدة البيانات المستخدمة.")
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

async def on_price(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    code = c.data.split(":", 1)[1]
    product = PRODUCTS.get(code) or UC_PRODUCTS.get(code)
    if not product:
        await c.answer("الباقة غير موجودة.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "price_edit", "code": code}
    service = "TikTok" if code in PRODUCTS else "PUBG UC"
    await c.message.answer(
        f"✏️ تعديل سعر {service} {product['coins']:,}\nالسعر الحالي: {product['price']} جنيه\nأرسل السعر الجديد بالجنيه المصري (أرقام فقط):",
        reply_markup=cancel_markup()
    )
    await c.answer()


async def on_product_add(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    pending[c.from_user.id] = {"step": "new_product_category"}
    await c.message.answer("اختار نوع الباقة واكتب: tiktok أو pubg", reply_markup=cancel_markup())
    await c.answer()

async def on_product_delete(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    code = c.data.split(":", 1)[1]
    product = PRODUCTS.get(code) or UC_PRODUCTS.get(code)
    if not product:
        await c.answer("المنتج غير موجود.", show_alert=True)
        return
    rows = [[InlineKeyboardButton(text="🗑 نعم، احذف نهائياً", callback_data=f"productdelconfirm:{code}")],
            [InlineKeyboardButton(text="↩️ إلغاء", callback_data="admin:products")]]
    await c.message.answer(f"تأكيد حذف باقة {product['coins']:,}؟\nلن تظهر للعملاء بعد الحذف، لكن الطلبات القديمة لن تُمسح.", reply_markup=kb(rows))
    await c.answer()

async def on_product_delete_confirm(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    code = c.data.split(":", 1)[1]
    product = PRODUCTS.pop(code, None) or UC_PRODUCTS.pop(code, None)
    if not product:
        await c.answer("المنتج غير موجود أو تم حذفه.", show_alert=True)
        return
    await delete_custom_product(code)
    PRODUCT_STATUS.pop(code, None)
    await c.answer("تم حذف المنتج نهائياً.")
    await c.message.answer("✅ تم حذف الباقة من قائمة البيع. الطلبات القديمة محفوظة.", reply_markup=admin_keyboard())

async def on_product_toggle(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return
    code = c.data.split(":", 1)[1]
    product = PRODUCTS.get(code) or UC_PRODUCTS.get(code)
    if not product:
        await c.answer("المنتج غير موجود.", show_alert=True)
        return
    enabled = not PRODUCT_STATUS.get(code, True)
    await set_product_status(code, enabled)
    PRODUCT_STATUS[code] = enabled
    await c.answer("تم إظهار المنتج." if enabled else "تم إخفاء المنتج.")
    await c.message.answer(("🟢 المنتج ظاهر الآن: " if enabled else "⚫ المنتج مخفي الآن: ") + str(product["coins"]) + (" عملة TikTok" if code in PRODUCTS else " UC PUBG"), reply_markup=admin_keyboard())

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
        if str(order[4]).startswith("uc_"):
            await notify_admins(
                c.bot,
                f"🎮 مطلوب تنفيذ شحن PUBG UC يدوياً\nالطلب: #{oid}\n"
                f"Player ID: {order[3]}\nالباقة: {order[5]} UC\n"
                f"المبلغ: {order[6]} جنيه\nتم تأكيد وصول الدفع؛ نفّذ الشحن ثم تواصل مع العميل."
            )
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
        if step == "botstore_name":
            data["customer_name"] = txt[:100]
            data["step"] = "botstore_type"
            await m.answer("اكتب نوع المتجر أو النشاط الذي تريد البوت له:")
            return
        if step == "botstore_type":
            data["store_type"] = txt[:300]
            data["step"] = "botstore_features"
            await m.answer("اكتب أهم الوظائف التي تحتاجها في البوت، أو اكتب: اقترح عليّ")
            return
        if step == "botstore_features":
            package = BOT_PACKAGES[data["package"]]
            details = (
                f"🤖 طلب بوت متجر جديد\\n"
                f"الباقة: {package[0]}\\nالسعر المبدئي: {package[1]:,} جنيه\\n"
                f"العميل: {data['customer_name']}\\n"
                f"النشاط: {data['store_type']}\\n"
                f"المطلوب: {txt[:1000]}\\n"
                f"Telegram ID: {uid}\\nUsername: @{m.from_user.username or 'غير متوفر'}"
            )
            await notify_admins(m.bot, details, reply_markup=kb([
                [InlineKeyboardButton(text="📩 التواصل مع العميل", callback_data=f"reply:{uid}")]
            ]))
            pending.pop(uid, None)
            await m.answer("✅ وصل طلبك للإدارة بنجاح. هنتواصل معاك على تيليجرام لتأكيد التفاصيل والاتفاق على التنفيذ.")
            return
        if step == "new_product_category" and is_admin(uid):
            category = txt.strip().lower()
            if category not in ("tiktok", "pubg"):
                await m.answer("اكتب tiktok أو pubg فقط.", reply_markup=cancel_markup())
                return
            data.update(step="new_product_quantity", category=category)
            await m.answer("أرسل كمية العملات أو UC بالأرقام فقط:")
            return
        if step == "new_product_quantity" and is_admin(uid):
            try:
                quantity = int(txt.replace(",", "").replace("٬", ""))
                if quantity <= 0 or quantity > 1000000000:
                    raise ValueError
            except ValueError:
                await m.answer("الكمية غير صحيحة. أرسل رقماً أكبر من صفر.")
                return
            data.update(step="new_product_price", quantity=quantity)
            await m.answer("أرسل سعر الباقة بالجنيه المصري:")
            return
        if step == "new_product_price" and is_admin(uid):
            try:
                price = int(txt.replace(",", "").replace("٬", ""))
                if price <= 0 or price > 100000000:
                    raise ValueError
            except ValueError:
                await m.answer("السعر غير صحيح. أرسل رقماً أكبر من صفر.")
                return
            category = data["category"]
            quantity = data["quantity"]
            code = f"custom_{category}_{quantity}"
            product = {"code": code, "coins": quantity, "price": price}
            try:
                await add_custom_product(category, product)
            except ValueError as exc:
                await m.answer(str(exc), reply_markup=admin_keyboard())
                pending.pop(uid, None)
                return
            target = PRODUCTS if category == "tiktok" else UC_PRODUCTS
            target[code] = product
            PRODUCT_STATUS[code] = True
            pending.pop(uid, None)
            await m.answer(f"✅ تمت إضافة باقة {'TikTok' if category == 'tiktok' else 'PUBG'}: {quantity:,} — {price} جنيه. أصبحت ظاهرة للعملاء.", reply_markup=admin_keyboard())
            return
        if step == "price_edit" and is_admin(uid):
            try:
                new_price = int(txt)
                if new_price <= 0 or new_price > 100000000:
                    raise ValueError
            except ValueError:
                await m.answer("السعر غير صحيح. أرسل رقماً أكبر من صفر بالجنيه المصري.", reply_markup=cancel_markup())
                return
            code = data["code"]
            product = PRODUCTS.get(code) or UC_PRODUCTS.get(code)
            if not product:
                pending.pop(uid, None)
                await m.answer("الباقة غير موجودة.")
                return
            await set_product_price(code, new_price)
            product["price"] = new_price
            pending.pop(uid, None)
            await m.answer(f"✅ تم تعديل سعر باقة {product['coins']:,} إلى {new_price} جنيه.\nالسعر محفوظ حتى بعد إعادة تشغيل البوت.", reply_markup=admin_keyboard())
            return
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
        if step == "sell_category":
            category = txt.lower()
            if category not in ("pubg", "tiktok"):
                await m.answer("اكتب pubg أو tiktok فقط.", reply_markup=cancel_markup())
                return
            data.update(step="sell_title", category=category)
            await m.answer("اكتب اسم أو عنوان الحساب المعروض للبيع:")
            return
        if step == "sell_title":
            data.update(step="sell_description", title=txt)
            await m.answer("اكتب وصف الحساب ومميزاته، أو اكتب: بدون")
            return
        if step == "sell_description":
            data.update(step="sell_price", description="" if txt.lower() == "بدون" else txt)
            await m.answer("اكتب السعر المطلوب بالجنيه المصري (أرقام فقط):")
            return
        if step == "sell_price":
            try:
                price = int(txt.replace(",", "").replace("٬", ""))
                if price <= 0 or price > 100000000:
                    raise ValueError
            except ValueError:
                await m.answer("السعر غير صحيح. اكتب رقماً أكبر من صفر.")
                return
            data.update(step="sell_photo", price=price)
            await m.answer("أرسل صورة للحساب، أو اكتب تخطي إذا لا تريد إضافة صورة.")
            return
        if step == "sell_photo":
            if txt != "تخطي":
                await m.answer("أرسل صورة أو اكتب تخطي.")
                return
            await finish_account_submission(m, data, None)
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
        if step == "pubg_id":
            player_id = txt.strip()
            if not player_id.isdigit() or not 5 <= len(player_id) <= 20:
                await m.answer("Player ID غير صحيح. أرسل الأرقام فقط وتأكد من الـ ID.", reply_markup=cancel_markup())
                return
            data.update(step="payment", tiktok_id=player_id, service="pubg_uc")
            p = UC_PRODUCTS[data["code"]]
            await m.answer(
                f"🎮 خدمة: شحن PUBG UC\nPlayer ID: {player_id}\n"
                f"الباقة: {p['coins']} UC\nالسعر: {p['price']} جنيه\n"
                "الشحن يتم يدوياً بعد مراجعة الدفع. اختر وسيلة الدفع:",
                reply_markup=payment_methods()
            )
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

async def finish_account_submission(m, data, photo_id):
    try:
        sid = await add_account_submission(
            m.from_user.id, m.from_user.username, data["category"],
            data["title"], data.get("description", ""), data["price"], photo_id
        )
        pending.pop(m.from_user.id, None)
        await m.answer(
            f"✅ استلمنا عرضك رقم #{sid} بنجاح.\n"
            "الإدارة هتراجع بيانات الحساب، وهيتم إبلاغك بالقرار. "
            "مش هيظهر في المتجر إلا بعد الموافقة."
        )
        category_name = "TikTok" if data["category"] == "tiktok" else "PUBG"
        caption = (f"📝 عرض حساب جديد للبيع #{sid}\nالنوع: {category_name}\n"
                   f"العنوان: {data['title']}\nالوصف: {data.get('description') or 'بدون وصف'}\n"
                   f"السعر المطلوب: {data['price']} جنيه\nالبائع: {m.from_user.id}\n"
                   f"Username: @{m.from_user.username or 'غير متوفر'}")
        markup = kb([[InlineKeyboardButton(text="✅ موافقة ونشر", callback_data=f"sellapprove:{sid}"),
                      InlineKeyboardButton(text="❌ رفض", callback_data=f"sellreject:{sid}")]])
        for admin_id in ADMIN_IDS:
            try:
                if photo_id:
                    await m.bot.send_photo(admin_id, photo_id, caption=caption, reply_markup=markup)
                else:
                    await m.bot.send_message(admin_id, caption, reply_markup=markup)
            except Exception:
                log.exception("Could not notify admin about account submission %s", sid)
    except Exception:
        log.exception("Could not save account submission")
        await m.answer("حصل خطأ أثناء إرسال العرض. حاول مرة أخرى.")

async def finish_account(m, data, photo_id):
    try:
        category = str(data["category"]).strip().lower()
        if category not in ("pubg", "tiktok"):
            raise ValueError(f"Invalid account category: {category!r}")
        aid = await add_account(category, data["title"], data["description"], data["price"], photo_id)
        saved = await get_account(aid)
        if not saved:
            raise RuntimeError(f"Account #{aid} was not found after insert")
        pending.pop(m.from_user.id, None)
        category_name = "TikTok" if category == "tiktok" else "PUBG"
        await m.answer(f"✅ تمت إضافة حساب {category_name} بنجاح. رقم الحساب: #{aid}\nتقدر تلاقيه في قسم {category_name} بلوحة الإدارة والمتجر.")
    except Exception:
        log.exception("Could not save account")
        await m.answer("حدث خطأ أثناء إضافة الحساب.")

async def on_photo(m: Message):
    data = pending.get(m.from_user.id)
    photo_id = m.photo[-1].file_id
    if data and data.get("step") == "sell_photo":
        await finish_account_submission(m, data, photo_id)
        return
    if data and data.get("step") == "account_photo":
        await finish_account(m, data, photo_id)
        return
    if not data or data.get("step") != "receipt":
        return
    p = UC_PRODUCTS[data["code"]] if data.get("service") == "pubg_uc" else PRODUCTS[data["code"]]
    try:
        oid = await add_order(m.from_user.id, m.from_user.username, data["tiktok_id"], p, data["payment_method"], photo_id)
        pending.pop(m.from_user.id, None)
        await m.answer(f"✅ تم استلام الإيصال. رقم الطلب: #{oid}\nالحالة: بانتظار مراجعة الإدارة.")
        if data.get("service") == "pubg_uc":
            order_details = (
                f"🎮 الخدمة: شحن PUBG UC\nPlayer ID: {data['tiktok_id']}\n"
                f"الباقة: {p['coins']} UC\nالسعر: {p['price']} جنيه"
            )
        else:
            order_details = (
                f"الخدمة: شحن TikTok\nTikTok ID: @{data['tiktok_id']}\n"
                f"الباقة: {p['coins']} Coins\nالسعر: {p['price']} جنيه"
            )
        caption = (f"🧾 طلب جديد #{oid}\nالعميل: {m.from_user.id}\n"
                   f"Username: @{m.from_user.username or 'غير متوفر'}\n"
                   f"{order_details}\nالدفع: {data['payment_method']}\n"
                   f"📌 رقم التحويل المختار: {data.get('recipient_number', 'غير محدد')}\n"
                   "⚠️ راجع وصول المبلغ يدوياً. بعد تأكيد الدفع نفّذ شحن UC يدوياً إذا كان الطلب PUBG.")
        for aid in ADMIN_IDS:
            try:
                await m.bot.send_photo(aid, photo_id, caption=caption,
                                       reply_markup=receipt_buttons(oid, m.from_user.id))
            except Exception:
                log.exception("Receipt notification failed")
    except Exception:
        log.exception("Receipt processing failed")
        await m.answer("حدث خطأ أثناء تسجيل الإيصال. حاول مرة أخرى.")

def prepare_database():
    """Use Render's persistent disk and safely copy the legacy SQLite DB once."""
    target = os.path.abspath(DB_PATH)
    legacy = os.path.abspath("hamo_store.db")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)

    if target != legacy and not os.path.exists(target) and os.path.exists(legacy):
        # SQLite backup includes committed WAL contents; safer than copying the file.
        with sqlite3.connect(legacy) as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        log.warning("Migrated legacy database from %s to %s", legacy, target)

    log.info("Using SQLite database: %s", target)
    if os.path.exists(target):
        try:
            with sqlite3.connect(target) as db:
                tables = {row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                if "accounts" in tables:
                    rows = db.execute(
                        "SELECT LOWER(TRIM(category)), status, COUNT(*) "
                        "FROM accounts GROUP BY LOWER(TRIM(category)), status"
                    ).fetchall()
                    log.info("Saved account counts by category/status: %s", rows)
        except sqlite3.Error:
            log.exception("Could not inspect SQLite database before initialization")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير مضبوط في Environment Variables")
    if not ADMIN_IDS:
        raise RuntimeError("ADMIN_IDS غير مضبوط. ضع Telegram user ID واحداً على الأقل.")
    prepare_database()
    await init_db()
    await init_product_prices({**PRODUCTS, **UC_PRODUCTS})
    await init_product_statuses({**PRODUCTS, **UC_PRODUCTS})
    global PRODUCT_STATUS
    PRODUCT_STATUS = await get_product_statuses()
    custom_products = await get_custom_products()
    for category, product in custom_products:
        (PRODUCTS if category == "tiktok" else UC_PRODUCTS)[product["code"]] = product
    saved_prices = await get_product_prices()
    for code, price in saved_prices.items():
        product = PRODUCTS.get(code) or UC_PRODUCTS.get(code)
        if product:
            product["price"] = price
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start, CommandStart())
    dp.message.register(admin_start, Command("admin"))
    dp.message.register(on_photo, F.photo)
    dp.message.register(on_text, F.text)

    dp.callback_query.register(on_cancel, F.data == "cancel")
    dp.callback_query.register(on_home, F.data == "home")
    dp.callback_query.register(on_catalog, F.data == "catalog")
    dp.callback_query.register(on_uc_catalog, F.data == "uc_catalog")
    dp.callback_query.register(on_buy_uc, F.data.startswith("buyuc:"))
    dp.callback_query.register(on_buy, F.data.startswith("buy:"))
    dp.callback_query.register(on_accounts, F.data.startswith("accounts:"))
    dp.callback_query.register(on_sell_account, F.data == "sellaccount")
    dp.callback_query.register(on_botstore, F.data == "botstore")
    dp.callback_query.register(on_bot_package, F.data.startswith("botpackage:"))
    dp.callback_query.register(on_sell_submission_review, F.data.startswith(("sellapprove:", "sellreject:")))
    dp.callback_query.register(on_buy_account, F.data.startswith("buyacc:"))
    dp.callback_query.register(on_support, F.data == "support")
    dp.callback_query.register(on_admin, F.data.startswith("admin:"))
    dp.callback_query.register(on_price, F.data.startswith("price:"))
    dp.callback_query.register(on_product_toggle, F.data.startswith("producttoggle:"))
    dp.callback_query.register(on_product_add, F.data == "productadd")
    dp.callback_query.register(on_product_delete, F.data.startswith("productdelete:"))
    dp.callback_query.register(on_product_delete_confirm, F.data.startswith("productdelconfirm:"))
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
