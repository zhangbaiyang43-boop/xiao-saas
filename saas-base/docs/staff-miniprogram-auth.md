# Staff WeChat / Mini-program Auth (historical)

Staff WeChat Authentication Provider exited 2026-08.

Formal staff Authentication is H5 Password + Trusted Device
(`POST /api/v1/login/staff`, `POST /api/v1/login/staff/device`).

`merchant_account_wechat_bindings` table/model may remain for Alembic history only;
no runtime staff WeChat bind/login path.
