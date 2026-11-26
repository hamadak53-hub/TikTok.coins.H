import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from config import BOT_TOKEN, ADMIN_IDS
from db import (
    init_db,
    add_order,
    latest_orders,
    confirm_payment,
    reject_payment,
    register_customer,
    get_dashboard_stats,
    get_orders,
    get_customers,
    get_order,
)
from catalog import PRODUCTS


if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

pending = {}

CASH_NUMBERS = ["01031921290", "01091924865"]


# =========================
# MAIN KEYBOARDS
# =========================

def home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 شحن العملات", callback_data="catalog")],
        [InlineKeyboardButton(text="📞 الدعم", callback_data="support")]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📊 الإحصائيات",
                callback_data="admin:stats"
            )
        ],
        [
            InlineKeyboardButton(
                text="📦 جميع الطلبات",
                callback_data="admin:orders"
            ),
            InlineKeyboardButton(
                text="⏳ الطلبات المعلقة",
                callback_data="admin:pending"
            )
        ],
        [
            InlineKeyboardButton(
                text="👥 العملاء",
                callback_data="admin:customers"
            )
        ],
    ])


def payment_methods():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 فودافون كاش", callback_data="pay:vodafone")],
        [InlineKeyboardButton(text="💳 إنستا باي", callback_data="pay:instapay")],
        [InlineKeyboardButton(text="🏦 تحويل بنكي", callback_data="pay:bank")],
        [InlineKeyboardButton(text="🌐 بوابة إلكترونية", callback_data="pay:gateway")]
    ])


def receipt_buttons(order_id, user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ تأكيد الدفع",
                callback_data=f"approve:{order_id}:{user_id}"
            ),
            InlineKeyboardButton(
                text="❌ رفض الدفع",
                callback_data=f"reject:{order_id}:{user_id}"
            )
        ]
    ])


def is_admin(user_id):
    return user_id in ADMIN_IDS


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(m: Message):
    pending.pop(m.from_user.id, None)

    await register_customer(
        m.from_user.id,
        m.from_user.username
    )

    await m.answer(
        "🖤 أهلاً بك في HAMO STORE\n"
        "متجر شحن عملات TikTok\n\n"
        "اختار الخدمة:",
        reply_markup=home()
    )


# =========================
# CATALOG
# =========================

@dp.callback_query(F.data == "catalog")
async def catalog(c: CallbackQuery):
    rows = []

    for p in PRODUCTS.values():
        rows.append([
            InlineKeyboardButton(
                text=f'{p["coins"]:,} عملة — {p["price"]} جنيه',
                callback_data=f'buy:{p["code"]}'
            )
        ])

    await c.message.answer(
        "🪙 اختر باقة الشحن:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await c.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def buy(c: CallbackQuery):
    code = c.data.split(":", 1)[1]

    if code not in PRODUCTS:
        await c.answer("الباقة غير متاحة", show_alert=True)
        return

    pending[c.from_user.id] = {
        "code": code,
        "step": "tiktok_id"
    }

    await c.message.answer(
        "🎮 أرسل TikTok ID أو اسم المستخدم المطلوب شحنه:"
    )
    await c.answer()


# =========================
# CUSTOMER TEXT
# =========================

@dp.message(F.text & ~F.text.startswith("/"))
async def get_text(m: Message):
    data = pending.get(m.from_user.id)

    if not data:
        return

    if data["step"] == "tiktok_id":
        tiktok_id = m.text.strip().lstrip("@")

        if not 2 <= len(tiktok_id) <= 64:
            await m.answer("اسم الحساب غير صحيح. حاول مرة أخرى.")
            return

        data["tiktok_id"] = tiktok_id
        data["step"] = "payment"

        p = PRODUCTS[data["code"]]

        await m.answer(
            f"✅ الحساب: @{tiktok_id}\n"
            f"🪙 الباقة: {p['coins']} كوين\n"
            f"💰 السعر: {p['price']} جنيه\n\n"
            "اختر وسيلة الدفع:",
            reply_markup=payment_methods()
        )


# =========================
# PAYMENT
# =========================

@dp.callback_query(F.data.startswith("pay:"))
async def choose_payment(c: CallbackQuery):
    data = pending.get(c.from_user.id)

    if not data or data.get("step") != "payment":
        await c.answer("ابدأ طلب جديد.", show_alert=True)
        return

    method = c.data.split(":")[1]

    if method in ("bank", "gateway"):
        await c.answer(
            "هذه الوسيلة قيد التجهيز حالياً.",
            show_alert=True
        )
        return

    method_name = (
        "فودافون كاش" if method == "vodafone"
        else "إنستا باي"
    )

    data["payment_method"] = method_name
    data["step"] = "receipt"

    numbers = "\n".join(
        f"📱 {number}" for number in CASH_NUMBERS
    )

    await c.message.answer(
        f"💳 وسيلة الدفع: {method_name}\n\n"
        f"حوّل المبلغ إلى أحد الرقمين:\n\n"
        f"{numbers}\n\n"
        "📸 بعد التحويل أرسل صورة الإيصال هنا.\n"
        "سيتم مراجعة التحويل من الإدارة."
    )

    await c.answer()


# =========================
# RECEIPT
# =========================

@dp.message(F.photo)
async def receive_receipt(m: Message):
    data = pending.get(m.from_user.id)

    if not data or data.get("step") != "receipt":
        return

    p = PRODUCTS[data["code"]]
    receipt_id = m.photo[-1].file_id

    try:
        order_id = await add_order(
            m.from_user.id,
            m.from_user.username,
            data["tiktok_id"],
            p,
            data["payment_method"],
            receipt_id
        )

        pending.pop(m.from_user.id, None)

        await m.answer(
            f"✅ تم استلام الإيصال.\n\n"
            f"رقم الطلب: #{order_id}\n"
            f"الباقة: {p['coins']} كوين\n"
            f"السعر: {p['price']} جنيه\n"
            "الحالة: بانتظار مراجعة الدفع."
        )

        caption = (
            f"🧾 طلب جديد #{order_id}\n\n"
            f"العميل: {m.from_user.id}\n"
            f"Username: @{m.from_user.username or 'غير متوفر'}\n"
            f"TikTok: @{data['tiktok_id']}\n"
            f"الباقة: {p['coins']} Coins\n"
            f"السعر: {p['price']} جنيه\n"
            f"الدفع: {data['payment_method']}"
        )

        for aid in ADMIN_IDS:
            await bot.send_photo(
                aid,
                receipt_id,
                caption=caption,
                reply_markup=receipt_buttons(
                    order_id,
                    m.from_user.id
                )
            )

    except Exception as e:
        print("Receipt error:", e)
        await m.answer("حدث خطأ. حاول مرة أخرى أو تواصل مع الدعم.")


# =========================
# ADMIN DASHBOARD
# =========================

@dp.message(Command("admin"))
async def admin(m: Message):
    if not is_admin(m.from_user.id):
        return

    await m.answer(
        "🛠️ HAMO STORE\n"
        "لوحة تحكم الإدارة\n\n"
        "اختر القسم المطلوب:",
        reply_markup=admin_keyboard()
    )


@dp.callback_query(F.data.startswith("admin:"))
async def admin_sections(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    section = c.data.split(":")[1]

    if section == "home":
        await c.message.answer(
            "🛠️ لوحة تحكم HAMO STORE",
            reply_markup=admin_keyboard()
        )

    elif section == "stats":
        s = await get_dashboard_stats()

        await c.message.answer(
            "📊 إحصائيات HAMO STORE\n\n"
            f"📦 إجمالي الطلبات: {s['orders']}\n"
            f"👥 عدد العملاء: {s['customers']}\n"
            f"💰 المبيعات المؤكدة: {s['revenue']} جنيه\n"
            f"⏳ مدفوعات معلقة: {s['pending']}\n"
            f"✅ مدفوعات مؤكدة: {s['paid']}\n"
            f"❌ مدفوعات مرفوضة: {s['rejected']}\n"
            f"📬 طلبات مكتملة: {s['completed']}\n\n"
            "ملاحظة: المبيعات ليست صافي الأرباح.",
            reply_markup=admin_keyboard()
        )

    elif section in ("orders", "pending"):
        status = (
            "pending_payment_review"
            if section == "pending" else None
        )

        rows = await get_orders(status=status, limit=15)

        if not rows:
            await c.message.answer("لا توجد طلبات في هذا القسم.")
        else:
            await c.message.answer(
                "📦 الطلبات:\n\n" +
                "\n\n".join(
                    f"#{r[0]} | العميل: {r[1]}\n"
                    f"TikTok: @{r[3]}\n"
                    f"العملات: {r[4]}\n"
                    f"السعر: {r[5]} جنيه\n"
                    f"الدفع: {r[6] or 'غير محدد'}\n"
                    f"الحالة: {r[8]}"
                    for r in rows
                ),
                reply_markup=admin_keyboard()
            )

    elif section == "customers":
        rows = await get_customers(limit=30)

        if not rows:
            await c.message.answer(
                "لا يوجد عملاء مسجلون حتى الآن."
            )
        else:
            await c.message.answer(
                "👥 قائمة العملاء:\n\n" +
                "\n\n".join(
                    f"🆔 {r[0]}\n"
                    f"Username: @{r[1] or 'غير متوفر'}\n"
                    f"عدد الطلبات: {r[2]}\n"
                    f"إجمالي المدفوع: {r[3]} جنيه"
                    for r in rows
                ),
                reply_markup=admin_keyboard()
            )

    await c.answer()


# =========================
# PAYMENT APPROVAL
# =========================

@dp.callback_query(F.data.startswith("approve:"))
async def approve(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    _, order_id, user_id = c.data.split(":")

    try:
        order = await get_order(int(order_id))

        if not order or order[9] != "pending":
            await c.answer(
                "الطلب تمت مراجعته بالفعل.",
                show_alert=True
            )
            return

        await confirm_payment(int(order_id))

        await bot.send_message(
            int(user_id),
            f"✅ تم تأكيد دفع طلبك #{order_id}.\n"
            "طلبك بانتظار تنفيذ الشحن."
        )

        await c.message.edit_reply_markup(reply_markup=None)
        await c.answer("تم تأكيد الدفع.")

    except Exception as e:
        print("Approve error:", e)
        await c.answer("تعذر تأكيد الطلب.", show_alert=True)


@dp.callback_query(F.data.startswith("reject:"))
async def reject(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    _, order_id, user_id = c.data.split(":")

    try:
        order = await get_order(int(order_id))

        if not order or order[9] != "pending":
            await c.answer(
                "الطلب تمت مراجعته بالفعل.",
                show_alert=True
            )
            return

        await reject_payment(int(order_id))

        await bot.send_message(
            int(user_id),
            f"❌ تم رفض إيصال الطلب #{order_id}.\n"
            "تواصل مع الإدارة للمساعدة."
        )

        await c.message.edit_reply_markup(reply_markup=None)
        await c.answer("تم رفض الدفع.")

    except Exception as e:
        print("Reject error:", e)
        await c.answer("تعذر رفض الطلب.", show_alert=True)


# =========================
# SUPPORT
# =========================

@dp.callback_query(F.data == "support")
async def support(c: CallbackQuery):
    await c.message.answer(
        "📞 دعم HAMO STORE\n"
        "تواصل مع الإدارة للمساعدة."
    )
    await c.answer()


# =========================
# RUN
# =========================

async def main():
    await init_db()
    print("HAMO STORE is running...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
    
