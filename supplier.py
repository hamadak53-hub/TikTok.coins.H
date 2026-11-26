"""واجهة مورد فارغة عمدًا حتى اعتماد المورد واستلام توثيق API الرسمي."""
class SupplierNotConfigured(Exception):
    pass

async def create_topup(*, client_reference: str, tiktok_id: str, product_code: str):
    raise SupplierNotConfigured("Supplier API is not configured; order requires admin review.")
