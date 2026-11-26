from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import ForeignKeyViolation

from app.auth import check_csrf, require_login
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/customers")
async def list_customers(request: Request, q: str = ""):
    require_login(request)
    params = ()
    sql = "SELECT * FROM CUSTOMER"
    if q.strip():
        sql += " WHERE Name ILIKE %s OR Email ILIKE %s OR Phone ILIKE %s"
        params = (f"%{q}%", f"%{q}%", f"%{q}%")
    sql += " ORDER BY CustomerID"
    return templates.TemplateResponse("customers/list.html", template_context(request, rows=fetch_all(sql, params), q=q))


@router.get("/customers/new")
async def customer_new(request: Request):
    require_login(request)
    return templates.TemplateResponse("customers/form.html", template_context(request, item=None, error=None))


@router.post("/customers/new")
async def customer_create(request: Request, csrf_token: str = Form(...), name: str = Form(...), phone: str = Form(""), address: str = Form(""), email: str = Form("")):
    require_login(request)
    check_csrf(request, csrf_token)
    if not name.strip():
        return templates.TemplateResponse("customers/form.html", template_context(request, item=None, error="Name is required."), status_code=400)
    with transaction() as conn:
        conn.execute("INSERT INTO CUSTOMER (Name,Phone,Address,Email) VALUES (%s,%s,%s,%s)", (name.strip(), phone.strip() or None, address.strip() or None, email.strip() or None))
    return RedirectResponse("/customers", status_code=303)


@router.get("/customers/{customer_id}/edit")
async def customer_edit(request: Request, customer_id: int):
    require_login(request)
    item = fetch_one("SELECT * FROM CUSTOMER WHERE CustomerID=%s", (customer_id,))
    if not item:
        return RedirectResponse("/customers", status_code=303)
    return templates.TemplateResponse("customers/form.html", template_context(request, item=item, error=None))


@router.post("/customers/{customer_id}/edit")
async def customer_update(request: Request, customer_id: int, csrf_token: str = Form(...), name: str = Form(...), phone: str = Form(""), address: str = Form(""), email: str = Form("")):
    require_login(request)
    check_csrf(request, csrf_token)
    if not name.strip():
        item = fetch_one("SELECT * FROM CUSTOMER WHERE CustomerID=%s", (customer_id,))
        return templates.TemplateResponse("customers/form.html", template_context(request, item=item, error="Name is required."), status_code=400)
    with transaction() as conn:
        conn.execute("UPDATE CUSTOMER SET Name=%s,Phone=%s,Address=%s,Email=%s WHERE CustomerID=%s", (name.strip(), phone.strip() or None, address.strip() or None, email.strip() or None, customer_id))
    return RedirectResponse("/customers", status_code=303)


@router.post("/customers/{customer_id}/delete")
async def customer_delete(request: Request, customer_id: int, csrf_token: str = Form(...)):
    from app.auth import require_role
    require_role("admin")(request)
    check_csrf(request, csrf_token)
    try:
        with transaction() as conn:
            conn.execute("DELETE FROM CUSTOMER WHERE CustomerID=%s", (customer_id,))
    except ForeignKeyViolation:
        return templates.TemplateResponse("403.html", template_context(request, message="This customer is still referenced and cannot be deleted."), status_code=400)
    return RedirectResponse("/customers", status_code=303)
