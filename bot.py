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
    add_account,
    get_accounts,
    get_account,
    request_account,
    get_account_requests,
    set_account_status,
)
from catalog import PRODUCTS


if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN in .env")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

pending = {}

CASH_NUMBERS = ["01031921290", "01091924865"]


# =========================
# KEYBOARDS
# =========================

def home():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🪙 شحن العملات", callback_data="catalog")],
        [InlineKeyboardButton(text="🎮 حسابات PUBG", callback_data="accounts:pubg")],
        [InlineKeyboardButton(text="🎵 حسابات TikTok", callback_data="accounts:tiktok")],
        [InlineKeyboardButton(text="📞 الدعم", callback_data="support")]
    ])


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 الإحصائيات", callback_data="admin:stats")],
        [
            InlineKeyboardButton(text="📦 جميع الطلبات", callback_data="admin:orders"),
            InlineKeyboardButton(text="⏳ الطلبات المعلقة", callback_data="admin:pending")
        ],
        [InlineKeyboardButton(text="👥 العملاء", callback_data="admin:customers")],
        [InlineKeyboardButton(text="➕ إضافة حساب للبيع", callback_data="acctadmin:add")],
        [
            InlineKeyboardButton(text="🎮 حسابات PUBG", callback_data="acctadmin:pubg"),
            InlineKeyboardButton(text="🎵 حسابات TikTok", callback_data="acctadmin:tiktok")
        ],
        [InlineKeyboardButton(text="📨 طلبات شراء الحسابات", callback_data="acctadmin:requests")]
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


def account_buy_button(account_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🛒 اطلب الحساب",
            callback_data=f"buyacc:{account_id}"
        )]
    ])


def account_admin_buttons(account_id, status):
    if status == "available":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="✅ تحديد كمباع",
                callback_data=f"accsold:{account_id}"
            )],
            [InlineKeyboardButton(
                text="🙈 إخفاء الحساب",
                callback_data=f"acchide:{account_id}"
            )]
        ])

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="♻️ إعادة الحساب للمتاح",
            callback_data=f"accavailable:{account_id}"
        )]
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
        "متجر شحن العملات وبيع الحسابات\n\n"
        "اختار الخدمة:",
        reply_markup=home()
    )


# =========================
# COINS CATALOG
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
# CUSTOMER ACCOUNTS
# =========================

@dp.callback_query(F.data.startswith("accounts:"))
async def show_accounts(c: CallbackQuery):
    category = c.data.split(":")[1]

    if category not in ("pubg", "tiktok"):
        await c.answer("قسم غير متاح", show_alert=True)
        return

    accounts = await get_accounts(category=category)

    category_name = (
        "PUBG Mobile" if category == "pubg"
        else "TikTok"
    )

    if not accounts:
        await c.message.answer(
            f"📭 لا توجد حسابات {category_name} متاحة حالياً.\n"
            "تابعنا، سيتم إضافة حسابات جديدة قريباً."
        )
        await c.answer()
        return

    await c.message.answer(
        f"🔥 الحسابات المتاحة - {category_name}\n"
        "اختر الحساب المناسب لك:"
    )

    for account in accounts:
        account_id = account[0]
        title = account[2]
        description = account[3] or "لا يوجد وصف"
        price = account[4]
        photo = account[5]

        caption = (
            f"🎮 {title}\n\n"
            f"📝 التفاصيل: {description}\n"
            f"💰 السعر: {price} جنيه\n\n"
            "للطلب اضغط على الزر بالأسفل."
        )

        if photo:
            await c.message.answer_photo(
                photo=photo,
                caption=caption,
                reply_markup=account_buy_button(account_id)
            )
        else:
            await c.message.answer(
                caption,
                reply_markup=account_buy_button(account_id)
            )

    await c.answer()


@dp.callback_query(F.data.startswith("buyacc:"))
async def buy_account(c: CallbackQuery):
    account_id = int(c.data.split(":")[1])
    account = await get_account(account_id)

    if not account or account[6] != "available":
        await c.answer(
            "عذراً، الحساب لم يعد متاحاً.",
            show_alert=True
        )
        return

    request_id = await request_account(
        account_id,
        c.from_user.id,
        c.from_user.username
    )

    if request_id is None:
        await c.answer(
            "الحساب لم يعد متاحاً.",
            show_alert=True
        )
        return

    category_name = (
        "PUBG Mobile" if account[1] == "pubg"
        else "TikTok"
    )

    await c.message.answer(
        "✅ تم إرسال طلبك بنجاح.\n\n"
        f"رقم الطلب: #{request_id}\n"
        f"الحساب: {account[2]}\n"
        f"السعر: {account[4]} جنيه\n\n"
        "سيتم التواصل معك من الإدارة لإتمام البيع."
    )

    admin_text = (
        f"🛒 طلب شراء حساب جديد #{request_id}\n\n"
        f"نوع الحساب: {category_name}\n"
        f"الحساب: {account[2]}\n"
        f"السعر: {account[4]} جنيه\n\n"
        f"العميل: {c.from_user.id}\n"
        f"Username: @{c.from_user.username or 'غير متوفر'}"
    )

    for aid in ADMIN_IDS:
        try:
            await bot.send_message(
                aid,
                admin_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="📩 التواصل مع العميل",
                        url=f"tg://user?id={c.from_user.id}"
                    )],
                    [InlineKeyboardButton(
                        text="✅ تحديد الحساب كمباع",
                        callback_data=f"accsold:{account_id}"
                    )]
                ])
            )
        except Exception as e:
            print("Account notification error:", e)

    await c.answer("تم إرسال طلبك.")


# =========================
# ADMIN ACCOUNT MANAGEMENT
# =========================

@dp.callback_query(F.data == "acctadmin:add")
async def admin_add_account(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    await c.message.answer(
        "➕ إضافة حساب جديد\n\nاختر نوع الحساب:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎮 PUBG Mobile",
                callback_data="acctadd:pubg"
            )],
            [InlineKeyboardButton(
                text="🎵 TikTok",
                callback_data="acctadd:tiktok"
            )]
        ])
    )
    await c.answer()


@dp.callback_query(F.data.startswith("acctadd:"))
async def choose_account_category(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    category = c.data.split(":")[1]

    if category not in ("pubg", "tiktok"):
        await c.answer("نوع غير صحيح.", show_alert=True)
        return

    pending[c.from_user.id] = {
        "step": "account_title",
        "category": category
    }

    await c.message.answer("اكتب اسم أو عنوان الحساب:")
    await c.answer()


@dp.callback_query(F.data.startswith("acctadmin:"))
async def admin_account_sections(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    section = c.data.split(":")[1]

    if section in ("pubg", "tiktok"):
        accounts = await get_accounts(
            category=section,
            available_only=False
        )

        if not accounts:
            await c.message.answer("لا توجد حسابات في هذا القسم.")
            await c.answer()
            return

        await c.message.answer(
            "📋 إدارة الحسابات\n"
            "الحالة: متاح / مباع / مخفي"
        )

        for account in accounts:
            account_id = account[0]
            category_name = (
                "PUBG Mobile" if account[1] == "pubg"
                else "TikTok"
            )

            text = (
                f"#{account_id} - {category_name}\n"
                f"الحساب: {account[2]}\n"
                f"السعر: {account[4]} جنيه\n"
                f"الحالة: {account[6]}"
            )

            if account[5]:
                await c.message.answer_photo(
                    account[5],
                    caption=text,
                    reply_markup=account_admin_buttons(
                        account_id, account[6]
                    )
                )
            else:
                await c.message.answer(
                    text,
                    reply_markup=account_admin_buttons(
                        account_id, account[6]
                    )
                )

    elif section == "requests":
        requests = await get_account_requests(limit=30)

        if not requests:
            await c.message.answer("لا توجد طلبات شراء حسابات حتى الآن.")
        else:
            for r in requests:
                await c.message.answer(
                    f"🛒 طلب شراء حساب #{r[0]}\n\n"
                    f"الحساب: {r[7]}\n"
                    f"النوع: {r[6]}\n"
                    f"السعر: {r[8]} جنيه\n"
                    f"العميل: {r[2]}\n"
                    f"Username: @{r[3] or 'غير متوفر'}\n"
                    f"الحالة: {r[4]}"
                )

    await c.answer()


@dp.callback_query(F.data.startswith("accsold:"))
async def mark_account_sold(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    account_id = int(c.data.split(":")[1])
    account = await get_account(account_id)

    if not account:
        await c.answer("الحساب غير موجود.", show_alert=True)
        return

    await set_account_status(account_id, "sold")

    await c.message.answer(
        f"✅ تم تحديد الحساب #{account_id} كمباع."
    )
    await c.answer("تم تحديث حالة الحساب.")


@dp.callback_query(F.data.startswith("acchide:"))
async def hide_account(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    account_id = int(c.data.split(":")[1])
    await set_account_status(account_id, "hidden")

    await c.message.answer("🙈 تم إخفاء الحساب.")
    await c.answer()


@dp.callback_query(F.data.startswith("accavailable:"))
async def make_account_available(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("غير مسموح لك.", show_alert=True)
        return

    account_id = int(c.data.split(":")[1])
    await set_account_status(account_id, "available")

    await c.message.answer("♻️ الحساب أصبح متاحاً للبيع.")
    await c.answer()


# =========================
# CUSTOMER TEXT INPUT
# =========================

@dp.message(F.text & ~F.text.startswith("/"))
async def get_text(m: Message):
    data = pending.get(m.from_user.id)

    if not data:
        return

    step = data.get("step")

    if step == "tiktok_id":
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

    elif step == "account_title":
        data["title"] = m.text.strip()
        data["step"] = "account_description"
        await m.answer(
            "اكتب وصف الحساب ومميزاته.\n"
            "لو مش عايز تضيف وصف اكتب: بدون"
        )

    elif step == "account_description":
        description = m.text.strip()
        data["description"] = (
            "" if description == "بدون" else description
        )
        data["step"] = "account_price"
        await m.answer("اكتب سعر الحساب بالجنيه المصري، أرقام فقط:")

    elif step == "account_price":
        try:
            price = int(m.text.strip())
            if price <= 0:
                raise ValueError
        except ValueError:
            await m.answer("السعر غير صحيح. اكتب رقماً أكبر من صفر.")
            return

        data["price"] = price
        data["step"] = "account_photo"

        await m.answer(
            "📸 ابعت صورة الحساب الآن.\n"
            "أو اكتب «تخطي» لإضافة الحساب بدون صورة."
        )

    elif step == "account_photo":
        if m.text.strip() != "تخطي":
            await m.answer(
                "أرسل صورة للحساب أو اكتب «تخطي»."
            )
            return

        await save_new_account(m, data, None)


async def save_new_account(m, data, photo_file_id):
    try:
        account_id = await add_account(
            category=data["category"],
            title=data["title"],
            description=data["description"],
            price=data["price"],
            photo_file_id=photo_file_id
        )

        pending.pop(m.from_user.id, None)

        category_name = (
            "PUBG Mobile" if data["category"] == "pubg"
            else "TikTok"
        )

        await m.answer(
            "✅ تمت إضافة الحساب بنجاح.\n\n"
            f"رقم الحساب: #{account_id}\n"
            f"القسم: {category_name}\n"
            f"الاسم: {data['title']}\n"
            f"السعر: {data['price']} جنيه"
        )

    except Exception as e:
        print("Add account error:", e)
        await m.answer("حدث خطأ أثناء إضافة الحساب. حاول مرة أخرى.")


# =========================
# PAYMENT METHODS
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
# RECEIPT AND ACCOUNT PHOTO
# =========================

@dp.message(F.photo)
async def receive_photo(m: Message):
    data = pending.get(m.from_user.id)

    if data and data.get("step") == "account_photo":
        await save_new_account(
            m,
            data,
            m.photo[-1].file_id
        )
        return

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
            try:
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
                print("Admin receipt notification error:", e)

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

    pending.pop(m.from_user.id, None)

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

    section
