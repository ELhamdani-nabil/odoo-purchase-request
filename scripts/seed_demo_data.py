from dateutil.relativedelta import relativedelta
from odoo import fields

MARKER = "Donnees de demonstration"
Request = env["purchase.request"]

if Request.search_count([("description", "=", MARKER)]):
    print("Demo data already present - nothing to do.")
else:
    vendor_names = [
        "Azure Interior", "Deco Addict", "Gemini Furniture",
        "Ready Mat", "Wood Corner",
    ]
    vendors = []
    for name in vendor_names:
        partner = env["res.partner"].search([("name", "=", name)], limit=1)
        if not partner:
            partner = env["res.partner"].create(
                {"name": name, "is_company": True})
        vendors.append(partner)

    products = env["product.product"].search(
        [("purchase_ok", "=", True)], limit=6)
    if not products:
        products = env["product.product"].create([
            {"name": "Article demo %d" % i, "standard_price": 50.0 * i}
            for i in range(1, 5)
        ])

    users = env["res.users"].search([("share", "=", False)], limit=3)

    # (months ago, vendor index, quantity, unit price, state, priority)
    plan = [
        (5, 0, 4, 450.0, "done", "0"),
        (5, 1, 10, 120.0, "done", "1"),
        (4, 2, 2, 1800.0, "done", "0"),
        (4, 0, 6, 300.0, "approved", "0"),
        (3, 3, 20, 85.0, "done", "0"),
        (3, 1, 3, 2500.0, "approved", "2"),
        (2, 4, 1, 12500.0, "to_approve", "2"),
        (2, 2, 8, 220.0, "approved", "0"),
        (1, 0, 5, 700.0, "to_approve", "1"),
        (1, 3, 12, 95.0, "rejected", "0"),
        (0, 1, 2, 640.0, "draft", "0"),
        (0, 4, 7, 310.0, "approved", "1"),
    ]

    today = fields.Date.today()
    for i, (months_ago, v_idx, qty, price, state, prio) in enumerate(plan):
        product = products[i % len(products)]
        request = Request.create({
            "requester_id": users[i % len(users)].id,
            "vendor_id": vendors[v_idx].id,
            "request_date": today - relativedelta(months=months_ago, days=i),
            "priority": prio,
            "description": MARKER,
            "line_ids": [(0, 0, {
                "product_id": product.id,
                "quantity": qty,
                "price_unit": price,
            })],
        })
        vals = {"state": state}
        if state in ("approved", "done"):
            vals.update({
                "approver_id": users[0].id,
                "approval_date": fields.Datetime.now(),
            })
        request.write(vals)

    env.cr.commit()
    print("Demo data created: %d requests." % len(plan))