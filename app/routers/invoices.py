from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router=APIRouter(); templates=Jinja2Templates(directory="app/templates")

@router.get("/invoices")
async def invoice_list(request:Request):
    require_login(request)
    return templates.TemplateResponse("invoices/list.html",template_context(request,rows=fetch_all("SELECT * FROM INVOICE ORDER BY InvoiceDate DESC")))

@router.get("/invoices/new")
async def invoice_new(request:Request):
    require_login(request)
    repairs=fetch_all("SELECT r.*, (r.Cost+COALESCE((SELECT SUM(rp.Quantity*p.Price) FROM REPAIR_PART rp JOIN SPARE_PART p ON p.PartID=rp.PartID WHERE rp.RepairID=r.RepairID),0)) AS proposed FROM REPAIR r WHERE NOT EXISTS (SELECT 1 FROM INVOICE i WHERE i.RepairID=r.RepairID)")
    return templates.TemplateResponse("invoices/form.html",template_context(request,item=None,repairs=repairs,proposed=0,error=None))

@router.post("/invoices/new")
async def invoice_create(request:Request,csrf_token:str=Form(...),invoicedate:str=Form(...),totalamount:float=Form(...),repairid:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    if totalamount<0:return templates.TemplateResponse("invoices/form.html",template_context(request,item=None,repairs=fetch_all("SELECT * FROM REPAIR"),proposed=0,error="Total amount cannot be negative."),status_code=400)
    try:
        with transaction() as conn:conn.execute("INSERT INTO INVOICE (InvoiceDate,TotalAmount,RepairID) VALUES (%s,%s,%s)",(invoicedate,totalamount,repairid))
    except UniqueViolation:
        return templates.TemplateResponse("invoices/form.html",template_context(request,item=None,repairs=fetch_all("SELECT * FROM REPAIR"),proposed=0,error="A repair can have only one invoice."),status_code=400)
    return RedirectResponse("/invoices",status_code=303)

@router.get("/invoices/{invoice_id}/edit")
async def invoice_edit(request:Request,invoice_id:int):
    require_login(request)
    item=fetch_one("SELECT * FROM INVOICE WHERE InvoiceID=%s",(invoice_id,))
    if not item:return RedirectResponse("/invoices",status_code=303)
    return templates.TemplateResponse("invoices/form.html",template_context(request,item=item,repairs=fetch_all("SELECT * FROM REPAIR"),proposed=item["totalamount"],error=None))

@router.post("/invoices/{invoice_id}/edit")
async def invoice_update(request:Request,invoice_id:int,csrf_token:str=Form(...),invoicedate:str=Form(...),totalamount:float=Form(...),repairid:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    try:
        with transaction() as conn:conn.execute("UPDATE INVOICE SET InvoiceDate=%s,TotalAmount=%s,RepairID=%s WHERE InvoiceID=%s",(invoicedate,totalamount,repairid,invoice_id))
    except UniqueViolation:
        item=fetch_one("SELECT * FROM INVOICE WHERE InvoiceID=%s",(invoice_id,))
        return templates.TemplateResponse("invoices/form.html",template_context(request,item=item,repairs=fetch_all("SELECT * FROM REPAIR"),proposed=0,error="A repair can have only one invoice."),status_code=400)
    return RedirectResponse("/invoices",status_code=303)

@router.post("/invoices/{invoice_id}/delete")
async def invoice_delete(request:Request,invoice_id:int,csrf_token:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    with transaction() as conn:conn.execute("DELETE FROM INVOICE WHERE InvoiceID=%s",(invoice_id,))
    return RedirectResponse("/invoices",status_code=303)
