\# Odoo Purchase Request



Custom Odoo 19 module implementing a \*\*Procure-to-Pay\*\* workflow:

purchase request → approval → purchase order.



Module Odoo 19 personnalisé qui implémente un workflow \*\*Procure-to-Pay\*\* :

demande d'achat → approbation → bon de commande.



\## Features / Fonctionnalités



\- Purchase request with lines (product, quantity, unit price) and computed total

\- Automatic sequence (`PR/0001`)

\- Workflow: Draft → To approve → Approved / Rejected → Purchase order created

\- Approval rule: requests above 1,000 require a manager

\- One-click generation of a native Odoo purchase order (`purchase.order`)

\- Change tracking in the chatter (`mail.thread`)

\- Two security groups: User and Manager



\## Workflow



```

Draft ──Submit──> To approve ──Approve──> Approved ──Create PO──> Done

&#x20;                      │

&#x20;                      └──Reject──> Rejected

```



\## Stack



Python · Odoo 19 ORM · XML views · QWeb · PostgreSQL 16 · Docker



\## Quick start / Démarrage rapide



```bash

git clone https://github.com/ELhamdani-nabil/odoo-purchase-request.git

cd odoo-purchase-request

docker compose up -d

```



1\. Open http://localhost:8069 and create a database (with demo data)

2\. Activate developer mode: http://localhost:8069/odoo/apps?debug=1

3\. Install the \*\*Purchase\*\* and \*\*Employees\*\* apps

4\. Apps → Update Apps List → install \*\*Purchase Request\*\*



\## Project structure



```

addons/purchase\_request/

├── \_\_manifest\_\_.py

├── models/        # purchase.request, purchase.request.line

├── views/         # list, form, action, menu

├── security/      # groups and access rights

├── data/          # sequence

└── tests/         # unit tests (TransactionCase)

```



\## Relation with Oracle processes



| Oracle (Procure-to-Pay) | This module |

|---|---|

| Requisition | Purchase request |

| Approval | Manager approval above the threshold |

| Purchase order | Generated `purchase.order` |



\## Screenshots



!\[Request list](docs/screenshots/list.png)

!\[Request form](docs/screenshots/form.png)

!\[Generated purchase order](docs/screenshots/purchase\_order.png)



\## Author



ELhamdani Nabil

