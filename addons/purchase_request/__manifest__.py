{
    "name": "Purchase Request",
    "version": "1.0",
    "category": "Purchase",
    "summary": "Demandes d'achat avec workflow d'approbation",
    "author": "ELhamdani Nabil",
    "website": "https://github.com/ELhamdani-nabil/odoo-purchase-request",
    "depends": ["purchase", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "views/purchase_request_views.xml",
    ],
    "application": True,
    "license": "LGPL-3",
}