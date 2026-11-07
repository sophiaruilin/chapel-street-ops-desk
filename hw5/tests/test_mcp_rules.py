"""The shop rules, enforced by the MCP server itself (not by prompts)."""

from __future__ import annotations

import hashlib
import sqlite3

from conftest import ORIGINAL_DB


def cash(db) -> float:
    return sqlite3.connect(db).execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]


def prepare(server, tool, args, ticket_id=None):
    out = server.create_approval(tool, args, ticket_id=ticket_id, agent="accounting", team_run_id="test")
    return out


def test_agent_cannot_pay_without_a_human_approval(server, db):
    out = server.pay_invoice(501, "checking")
    assert out["done"] is False and "human" in out["message"].lower()
    out = server.pay_invoice(501, "checking", approval_id="nope", approved_by="Sophia Lin")
    assert out["done"] is False
    assert cash(db) == 3400.0


def test_agent_role_cannot_sign(server, db):
    appr = prepare(server, "pay_invoice", {"invoice_id": 501})["approval"]
    for fake in ("", "accounting", "Boss", "assistant"):
        assert server.pay_invoice(501, approval_id=appr["id"], approved_by=fake)["done"] is False
    assert cash(db) == 3400.0


def test_amount_is_frozen_and_paid_exactly_once(server, db):
    prep = prepare(server, "pay_invoice", {"invoice_id": 501, "account": "checking"}, ticket_id=101)
    assert prep["created"] and prep["approval"]["amount"] == 840.0 and prep["approval"]["payee"] == "Bulldog Print Co"
    aid = prep["approval"]["id"]
    first = server.pay_invoice(501, "checking", approval_id=aid, approved_by="Sophia Lin")
    assert first["done"] and first["paid"] and first["balance_after"] == 2560.0
    again = server.pay_invoice(501, "checking", approval_id=aid, approved_by="Sophia Lin")
    assert again["done"] and again["already_done"]          # idempotent: no second payment
    c = sqlite3.connect(db)
    assert c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 1
    assert c.execute("SELECT status FROM invoices WHERE id=501").fetchone()[0] == "paid"
    assert cash(db) == 2560.0


def test_duplicate_prepare_returns_the_same_pending_approval(server):
    a = prepare(server, "pay_rent", {"lease_id": 1})
    b = prepare(server, "pay_rent", {"lease_id": 1, "account": "checking"})
    assert a["created"] and not b["created"] and b["already_pending"]
    assert b["approval"]["id"] == a["approval"]["id"]


def test_record_change_after_prepare_is_refused(server, db):
    aid = prepare(server, "pay_invoice", {"invoice_id": 501})["approval"]["id"]
    c = sqlite3.connect(db)
    c.execute("UPDATE invoices SET amount = 1840 WHERE id = 501")
    c.commit()
    out = server.pay_invoice(501, approval_id=aid, approved_by="Sophia Lin")
    assert out["done"] is False and "changed since it was prepared" in out["message"]
    assert cash(db) == 3400.0


def test_arguments_must_match_what_was_approved(server, db):
    aid = prepare(server, "pay_rent", {"lease_id": 1})["approval"]["id"]
    out = server.pay_invoice(501, approval_id=aid, approved_by="Sophia Lin")
    assert out["done"] is False and "not what the human approved" in out["message"]


def test_no_negative_balances(server, db):
    c = sqlite3.connect(db)
    c.execute("UPDATE cash_accounts SET balance = 500")
    c.commit()
    out = prepare(server, "pay_rent", {"lease_id": 1})
    assert out["created"] is False and "No negative balances" in out["message"]
    # and if cash drops after preparing, executing is refused too
    c.execute("UPDATE cash_accounts SET balance = 3400")
    c.commit()
    aid = prepare(server, "pay_rent", {"lease_id": 1})["approval"]["id"]
    c.execute("UPDATE cash_accounts SET balance = 100")
    c.commit()
    out = server.pay_rent(1, approval_id=aid, approved_by="Sophia Lin")
    assert out["done"] is False and "not enough cash" in out["message"]
    assert cash(db) == 100.0


def test_two_different_approvers_above_threshold(server, db):
    server.SECOND_APPROVER_ABOVE = 1000.0
    aid = prepare(server, "pay_rent", {"lease_id": 1})["approval"]["id"]
    first = server.pay_rent(1, approval_id=aid, approved_by="Sophia Lin")
    assert first["done"] is False and first["needs_second_approver"]
    same = server.pay_rent(1, approval_id=aid, approved_by="sophia lin")
    assert same["done"] is False and "different person" in same["message"]
    second = server.pay_rent(1, approval_id=aid, approved_by="Tauhid Zaman")
    assert second["done"] and second["balance_after"] == 1000.0 and second["next_due_now"] == "2026-10-02"


def test_rent_cannot_be_paid_ahead(server):
    aid = prepare(server, "pay_rent", {"lease_id": 1})["approval"]["id"]
    assert server.pay_rent(1, approval_id=aid, approved_by="Sophia Lin")["done"]
    again = prepare(server, "pay_rent", {"lease_id": 1})
    assert again["created"] is False and "already paid ahead" in again["message"]


def test_purchase_blocked_while_vendor_has_unpaid_invoice(server, db):
    args = {"vendor_id": 1, "sku": "CC-HOOD-NAVY", "size": "M", "qty": 12}
    blocked = prepare(server, "order_stock", args)
    assert blocked["created"] is False and "will not ship" in blocked["message"]
    aid = prepare(server, "pay_invoice", {"invoice_id": 501})["approval"]["id"]
    server.pay_invoice(501, approval_id=aid, approved_by="Sophia Lin")
    prep = prepare(server, "order_stock", args, ticket_id=103)
    assert prep["created"] and prep["approval"]["amount"] == 264.0       # 12 x $22 unit cost
    done = server.order_stock(1, "CC-HOOD-NAVY", "M", 12, approval_id=prep["approval"]["id"],
                              approved_by="Sophia Lin")
    assert done["done"] and done["expected_by"] == "2026-09-05"         # desk date + 5 lead days
    c = sqlite3.connect(db)
    assert c.execute("SELECT kind, amount FROM payments WHERE kind='purchase'").fetchone() == ("purchase", 264.0)
    assert c.execute("SELECT qty FROM purchase_orders").fetchone()[0] == 12
    assert cash(db) == 3400.0 - 840.0 - 264.0


def test_bulk_price_floor_and_no_cash(server, db):
    below = prepare(server, "set_bulk_price", {"ticket_id": 103, "sku": "CC-HOOD-NAVY", "size": "M",
                                               "qty": 20, "unit_price": 20})
    assert below["created"] is False and "below" in below["message"]
    ok = prepare(server, "set_bulk_price", {"ticket_id": 103, "sku": "CC-HOOD-NAVY", "size": "M",
                                            "qty": 20, "unit_price": 50})
    assert ok["created"] and ok["approval"]["kind"] == "price"
    done = server.set_bulk_price(103, "CC-HOOD-NAVY", "M", 20, 50, approval_id=ok["approval"]["id"],
                                 approved_by="Sophia Lin")
    assert done["done"] and done["price_approved"]
    assert cash(db) == 3400.0                                           # a price approval moves no cash


def test_declined_approval_never_executes(server, db):
    aid = prepare(server, "pay_invoice", {"invoice_id": 501})["approval"]["id"]
    assert server.decline_approval(aid, "Sophia Lin", "not this week")["declined"]
    out = server.pay_invoice(501, approval_id=aid, approved_by="Sophia Lin")
    assert out["done"] is False and cash(db) == 3400.0


def test_customer_and_internal_drafts_are_kept_apart(server):
    assert server.add_ticket_draft(101, "Hi Tauhid ...", "customer")["saved"]
    assert server.add_ticket_draft(101, "cash note", "internal")["saved"]
    assert server.add_ticket_draft(101, "x", "everyone")["saved"] is False
    drafts = server.get_ticket(101)["drafts"]
    assert {d["audience"] for d in drafts} == {"customer", "internal"}
    assert all(d["sent"] == 0 for d in drafts)
    assert server.get_ticket(101)["ticket"]["notes"] == "Needs a tee in size S."   # notes untouched


def test_ticket_text_is_flagged_untrusted_and_context_is_complete(server):
    ctx = server.get_ticket_context(101)
    assert ctx["ticket"]["notes_are_untrusted_input"] is True
    assert ctx["stock_requested_size"]["qty"] == 0 and ctx["pricing"]["unit_cost"] == 8.0
    assert ctx["open_invoices"][0]["id"] == 501 and ctx["date_today"] == "2026-08-31"
    assert server.get_ticket_context(102)["lease"]["days_until_due"] == 2


def test_original_database_is_never_modified(server):
    before = hashlib.sha256(ORIGINAL_DB.read_bytes()).hexdigest()
    aid = prepare(server, "pay_invoice", {"invoice_id": 501})["approval"]["id"]
    server.pay_invoice(501, approval_id=aid, approved_by="Sophia Lin")
    assert hashlib.sha256(ORIGINAL_DB.read_bytes()).hexdigest() == before
