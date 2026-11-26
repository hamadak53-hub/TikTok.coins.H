import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramBadRequest
)

from config import BOT_TOKEN, ADMIN_IDS, STORE_NAME
from catalog import PRODUCTS

from db import (
    init_db,
    register_customer,
    add_order,
    get_order,
    confirm_payment,
    reject_payment,
    get_orders,
    get_customers,
    get_customer_ids,
    get_dashboard_stats,
    add_account,
    get_accounts,
    get_account,
    request_account,
    get_account_requests,
    set_account_status,
    save_support_message
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
        [InlineKeyboardButton(
            text="🪙 شحن العملات",
            callback_data="catalog"
        )],
        [InlineKeyboardButton(
            text="🎮 حسابات PUBG",
            callback_data="accounts:pubg"
        )],
        [InlineKeyboardButton(
            text="🎵 حسابات TikTok",
            callback_data="accounts:tiktok"
        )],
        [InlineKeyboardButton(
            text="📞 الدعم",
            callback_data="support"
        )]
    ])


def admin_keyboard():
    return kb([
        [InlineKeyboardButton(
            text="📊 الإحصائيات",
            callback_data="admin:stats"
        )],
        [
            InlineKeyboardButton(
                text="📦 الطلبات",
                callback_data="admin:orders"
            ),
            InlineKeyboardButton(
                text="⏳ المعلقة",
                callback_data="admin:pending"
            )
        ],
        [InlineKeyboardButton(
            text="👥 العملاء",
            callback_data="admin:customers"
        )],
        [InlineKeyboardButton(
            text="➕ إضافة حساب",
            callback_data="acctadmin:add"
        )],
        [
            InlineKeyboardButton(
                text="🎮 PUBG",
                callback_data="acctadmin:pubg"
            ),
            InlineKeyboardButton(
                text="🎵 TikTok",
                callback_data="acctadmin:tiktok"
            )
        ],
        [InlineKeyboardButton(
            text="📨 طلبات الحسابات",
            callback_data="acctadmin:requests"
        )],
        [InlineKeyboardButton(
            text="📢 رسالة جماعية",
            callback_data="broadcast"
        )]
    ])


def payment_methods():
    return kb([
        [InlineKeyboardButton(
            text="📱 فودافون كاش",
            callback_data="pay:vodafone"
        )],
        [InlineKeyboardButton(
            text="💳 إنستا باي",
            callback_data="pay:instapay"
        )]
    ])


def receipt_buttons(oid, uid):
    return kb([[
        InlineKeyboardButton(
            text="✅ تأكيد الدفع",
            callback_data=f"approve:{oid}:{uid}"
        ),
        InlineKeyboardButton(
            text="❌ رفض الدفع",
            callback_data=f"reject:{oid}:{uid}"
        )
    ]])


def account_buttons(aid):
    return kb([[
        InlineKeyboardButton(
            text="🛒 اطلب الحساب",
            callback_data=f"buyacc:{aid}"
        )
    ]])


def account_admin_buttons(aid, status):
    if status == "available":
        return kb([[
            InlineKeyboardButton(
                text="✅ مباع",
                callback_data=f"accsold:{aid}"
            ),
            InlineKeyboardButton(
                text="🙈 إخفاء",
                callback_data=f"acchide:{aid}"
            )
        ]])

    return kb([[
        InlineKeyboardButton(
            text="♻️ إتاحته للبيع",
            callback_data=f"accavailable:{aid}"
        )
    ]])


async def notify_admins(bot, text, **kwargs):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, text, **kwargs)
        except Exception:
            log.exception("Admin notification failed for %s", aid)


# =========================
# بداية البوت
# =========================

async def start(message: Message):
    uid = message.from_user.id

    pending.pop(uid, None)
    support_mode.discard(uid)
    reply_targets.pop(uid, None)

    await register_customer(uid, message.from_user.username)

    await message.answer(
        f"🖤 أهلاً بك في {STORE_NAME}\n"
        "متجر شحن العملات وبيع الحسابات\n\n"
        "اختار الخدمة:",
        reply_markup=home()
    )


async def admin_start(message: Message):
    if not is_admin(message.from_user.id):
        return

    pending.pop(message.from_user.id, None)
    support_mode.discard(message.from_user.id)

    await message.answer(
        "🛠️ HAMO STORE — لوحة الإدارة",
        reply_markup=admin_keyboard()
    )


# =========================
# شحن العملات
# =========================

async def on_catalog(c: CallbackQuery):
    rows = []

    for p in PRODUCTS.values():
        if int(p["price"]) <= 0:
            continue

        rows.append([
            InlineKeyboardButton(
                text=f'{p["coins"]:,} عملة — {p["price"]} جنيه',
                callback_data=f'buy:{p["code"]}'
            )
        ])

    if not rows:
        await c.answer(
            "الباقات غير مفعلة. راجع catalog.py",
            show_alert=True
        )
    else:
        await c.message.answer(
            "🪙 اختر باقة الشحن:",
            reply_markup=kb(rows)
        )
        await c.answer()


async def on_buy(c: CallbackQuery):
    code = c.data.split(":", 1)[1]

    if code not in PRODUCTS or int(PRODUCTS[code]["price"]) <= 0:
        await c.answer(
            "الباقة غير متاحة حالياً.",
            show_alert=True
        )
        return

    pending[c.from_user.id] = {
        "step": "tiktok_id",
        "code": code
    }

    await c.message.answer(
        "أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:"
    )
    await c.answer()


async def on_payment(c: CallbackQuery):
    data = pending.get(c.from_user.id)

    if not data or data.get("step") != "payment":
        await c.answer(
            "ابدأ طلب شحن جديد.",
            show_alert=True
        )
        return

    method = c.data.split(":")[1]

    if method not in ("vodafone", "instapay"):
        await c.answer("وسيلة الدفع غير صحيحة.", show_alert=True)
        return

    data["payment_method"] = (
        "فودافون كاش"
        if method == "vodafone"
        else "إنستا باي"
    )
    data["step"] = "receipt"

    nums = "\n".join("📱 " + n for n in CASH_NUMBERS)

    await c.message.answer(
        f"حوّل المبلغ إلى أحد الأرقام:\n{nums}\n\n"
        "ثم أرسل صورة الإيصال هنا."
    )
    await c.answer()


# =========================
# عرض الحسابات
# =========================

async def on_accounts(c: CallbackQuery):
    category = c.data.split(":")[1]

    if category not in ("pubg", "tiktok"):
        await c.answer("القسم غير صحيح.", show_alert=True)
        return

    accounts = await get_accounts(category)
    name = "PUBG Mobile" if category == "pubg" else "TikTok"

    if not accounts:
        await c.message.answer(
            f"📭 لا توجد حسابات {name} متاحة حالياً."
        )
    else:
        await c.message.answer(
            f"🔥 الحسابات المتاحة - {name}"
        )

        for a in accounts:
            caption = (
                f"🎮 {a[2]}\n\n"
                f"📝 {a[3] or 'لا يوجد وصف'}\n"
                f"💰 السعر: {a[4]} جنيه"
            )

            if a[5]:
                await c.message.answer_photo(
                    a[5],
                    caption=caption,
                    reply_markup=account_buttons(a[0])
                )
            else:
                await c.message.answer(
                    caption,
                    reply_markup=account_buttons(a[0])
                )

    await c.answer()


async def on_buy_account(c: CallbackQuery):
    try:
        aid = int(c.data.split(":")[1])
        a = await get_account(aid)

        if not a or a[6] != "available":
            await c.answer(
                "الحساب لم يعد متاحاً.",
                show_alert=True
            )
            return

        rid = await request_account(
            aid,
            c.from_user.id,
            c.from_user.username
        )

        if rid is None:
            await c.answer(
                "الحساب لم يعد متاحاً.",
                show_alert=True
            )
            return

        await c.message.answer(
            f"✅ استلمنا طلبك رقم #{rid} للحساب {a[2]} "
            f"بسعر {a[4]} جنيه.\n"
            "الإدارة هتتواصل معاك."
        )

        await notify_admins(
            c.bot,
            f"🛒 طلب حساب جديد #{rid}\n"
            f"الحساب: {a[2]}\n"
            f"السعر: {a[4]} جنيه\n"
            f"العميل: {c.from_user.id}\n"
            f"Username: @{c.from_user.username or 'غير متوفر'}",
            reply_markup=kb([
                [InlineKeyboardButton(
                    text="📩 مراسلة العميل",
                    callback_data=f"reply:{c.from_user.id}"
                )],
                [InlineKeyboardButton(
                    text="✅ تحديد كمباع",
                    callback_data=f"accsold:{aid}"
                )]
            ])
        )

        await c.answer("تم إرسال الطلب.")

    except Exception:
        log.exception("Account request failed")
        await c.answer(
            "حصل خطأ، حاول مرة أخرى.",
            show_alert=True
        )


# =========================
# الدعم
# =========================

async def on_support(c: CallbackQuery):
    support_mode.add(c.from_user.id)
    pending.pop(c.from_user.id, None)

    await c.message.answer(
        "📞 اكتب رسالتك هنا، وسيتم إرسالها للإدارة.\n"
        "لإلغاء الدعم اكتب /cancel"
    )
    await c.answer()


async def on_reply(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    uid = int(c.data.split(":")[1])

    reply_targets[c.from_user.id] = uid

    await c.message.answer(
        f"اكتب رسالتك للعميل {uid}:\n"
        "لإلغاء الرد اكتب /cancel"
    )
    await c.answer()


# =========================
# لوحة الإدارة
# =========================

async def on_admin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    section = c.data.split(":")[1]

    if section == "stats":
        s = await get_dashboard_stats()

        await c.message.answer(
            "📊 الإحصائيات\n"
            f"الطلبات: {s['orders']}\n"
            f"الإيرادات: {s['revenue']} جنيه\n"
            f"المعلقة: {s['pending']}\n"
            f"المدفوعة: {s['paid']}\n"
            f"المرفوضة: {s['rejected']}\n"
            f"المكتملة: {s['completed']}\n"
            f"العملاء: {s['customers']}\n"
            f"الحسابات: {s['accounts']}"
        )

    elif section in ("orders", "pending"):
        orders = await get_orders(
            limit=40,
            status="pending" if section == "pending" else None
        )

        if not orders:
            await c.message.answer("لا توجد طلبات.")
        else:
            for o in orders:
                text = (
                    f"📦 طلب #{o[0]}\n"
                    f"العميل: {o[1]}\n"
                    f"TikTok: @{o[3]}\n"
                    f"الكمية: {o[4]} Coins\n"
                    f"السعر: {o[5]} جنيه\n"
                    f"الدفع: {o[6]}\n"
                    f"حالة الدفع: {o[7]}\n"
                    f"حالة الطلب: {o[8]}"
                )

                buttons = (
                    receipt_buttons(o[0], o[1])
                    if o[7] == "pending"
                    else None
                )

                await c.message.answer(
                    text,
                    reply_markup=buttons
                )

    elif section == "customers":
        customers = await get_customers(1000)

        await c.message.answer(
            f"👥 عدد العملاء المسجلين: {len(customers)}"
        )

    await c.answer()


async def on_acctadmin(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    section = c.data.split(":")[1]

    if section == "add":
        pending[c.from_user.id] = {
            "step": "account_category"
        }

        await c.message.answer(
            "اكتب نوع الحساب: pubg أو tiktok"
        )

    elif section == "requests":
        reqs = await get_account_requests(limit=40)

        if not reqs:
            await c.message.answer(
                "لا توجد طلبات شراء حسابات."
            )

        for r in reqs:
            await c.message.answer(
                f"طلب حساب #{r[0]}\n"
                f"الحساب: {r[7]}\n"
                f"النوع: {r[6]}\n"
                f"السعر: {r[8]} جنيه\n"
                f"العميل: {r[2]}\n"
                f"الحالة: {r[4]}",
                reply_markup=kb([[
                    InlineKeyboardButton(
                        text="📩 مراسلة العميل",
                        callback_data=f"reply:{r[2]}"
                    )
                ]])
            )

    else:
        if section not in ("pubg", "tiktok"):
            await c.answer("القسم غير صحيح.", show_alert=True)
            return

        accounts = await get_accounts(
            section,
            available_only=False
        )

        if not accounts:
            await c.message.answer(
                "لا توجد حسابات في هذا القسم."
            )

        for a in accounts:
            text = (
                f"#{a[0]} — {a[2]}\n"
                f"السعر: {a[4]} جنيه\n"
                f"الحالة: {a[6]}"
            )

            if a[5]:
                await c.message.answer_photo(
                    a[5],
                    caption=text,
                    reply_markup=account_admin_buttons(a[0], a[6])
                )
            else:
                await c.message.answer(
                    text,
                    reply_markup=account_admin_buttons(a[0], a[6])
                )

    await c.answer()


async def on_account_status(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    action, raw = c.data.split(":")
    status = {
        "accsold": "sold",
        "acchide": "hidden",
        "accavailable": "available"
    }[action]

    await set_account_status(int(raw), status)

    await c.answer("تم تحديث حالة الحساب.")
    await c.message.answer("✅ تم تحديث حالة الحساب.")


# =========================
# تأكيد ورفض الدفع
# =========================

async def on_approval(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    action, oid_s, uid_s = c.data.split(":")
    oid = int(oid_s)
    uid = int(uid_s)

    order = await get_order(oid)

    if not order or order[9] != "pending" or order[1] != uid:
        await c.answer(
            "الطلب غير موجود أو تمت مراجعته.",
            show_alert=True
        )
        return

    if action == "approve":
        await confirm_payment(oid)

        customer_text = (
            f"✅ تم تأكيد الدفع للطلب #{oid}.\n"
            "سيتم تنفيذ طلبك."
        )
        status_text = "تم تأكيد الدفع بنجاح."

    else:
        await reject_payment(oid)

        customer_text = (
            f"❌ تم رفض إيصال الطلب #{oid}.\n"
            "تواصل مع الدعم للمراجعة."
        )
        status_text = "تم رفض الإيصال."

    try:
        await c.bot.send_message(uid, customer_text)
    except Exception:
        log.exception("Could not notify customer %s", uid)

    await c.message.answer(status_text)
    await c.answer("تم تحديث الطلب.")


# =========================
# الرسائل الجماعية
# =========================

async def on_broadcast(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    pending[c.from_user.id] = {
        "step": "broadcast"
    }

    await c.message.answer(
        "أرسل نص الإعلان الجماعي الآن.\n"
        "اكتب /cancel للإلغاء."
    )
    await c.answer()


async def send_broadcast(m: Message, txt):
    customer_ids = await get_customer_ids()

    sent = 0
    failed = 0

    for customer_id in customer_ids:
        try:
            await m.bot.send_message(
                customer_id,
                f"📢 HAMO STORE\n\n{txt}"
            )
            sent += 1

        except (
            TelegramForbiddenError,
            TelegramBadRequest
        ):
            failed += 1

        except Exception:
            log.exception(
                "Broadcast failed for customer %s",
                customer_id
            )
            failed += 1

    pending.pop(m.from_user.id, None)

    await m.answer(
        "انتهى الإرسال.\n"
        f"تم الإرسال: {sent}\n"
        f"تعذر الإرسال: {failed}"
    )


# =========================
# إنهاء إضافة الحساب
# =========================

async def finish_account(m: Message, data, photo_id):
    try:
        aid = await add_account(
            data["category"],
            data["title"],
            data["description"],
            data["price"],
            photo_id
        )

        pending.pop(m.from_user.id, None)

        await m.answer(
            f"✅ تمت إضافة الحساب بنجاح.\n"
            f"رقم الحساب: #{aid}"
        )

    except Exception:
        log.exception("Could not save account")
        await m.answer(
            "حدث خطأ أثناء إضافة الحساب."
        )


# =========================
# استقبال الرسائل النصية
# =========================

async def on_text(m: Message):
    uid = m.from_user.id
    txt = (m.text or "").strip()

    if txt == "/cancel":
        pending.pop(uid, None)
        support_mode.discard(uid)
        reply_targets.pop(uid, None)

        await m.answer("تم الإلغاء.")
        return

    # رد الأدمن على عميل
    if uid in reply_targets and is_admin(uid):
        customer_id = reply_targets.pop(uid)

        try:
            await m.bot.send_message(
                customer_id,
                f"📩 رسالة من إدارة HAMO STORE:\n\n{txt}"
            )

            await save_support_message(
                customer_id,
                txt,
                "admin",
                uid
            )

            await m.answer(
                "✅ تم إرسال الرد للعميل."
            )

        except Exception:
            log.exception("Support reply failed")
            await m.answer(
                "تعذر إرسال الرسالة لهذا العميل."
            )

        return

    data = pending.get(uid)

    if data:
        step = data.get("step")

        # إعلان جماعي
        if step == "broadcast" and is_admin(uid):
            await send_broadcast(m, txt)
            return

        # إضافة حساب
        if step == "account_category" and is_admin(uid):
            category = txt.lower()

            if category not in ("pubg", "tiktok"):
                await m.answer(
                    "اكتب pubg أو tiktok فقط."
                )
                return

            data.update(
                step="account_title",
                category=category
            )

            await m.answer(
                "اكتب اسم أو عنوان الحساب:"
            )
            return

        if step == "account_title" and is_admin(uid):
            data.update(
                step="account_description",
                title=txt
            )

            await m.answer(
                "اكتب وصف الحساب أو اكتب: بدون"
            )
            return

        if step == "account_description" and is_admin(uid):
            data.update(
                step="account_price",
                description
