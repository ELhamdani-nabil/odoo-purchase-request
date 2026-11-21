{
    "name": "Purchase Request",
    "version": "1.0",
    "category": "Purchase",
    "summary": "Demandes d'achat avec approbation à deux niveaux et analyse des dépenses",
    "author": "ELhamdani Nabil",
    "website": "https://github.com/ELhamdani-nabil/odoo-purchase-request",
    "depends": ["purchase", "hr"],
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "report/purchase_request_report.xml",
        "views/purchase_request_views.xml",
    ],
    "application": True,
    "installable": True,
    "license": "LGPL-3",
}