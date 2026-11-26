from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/vehicles")
async def list_vehicles(request: Request, q: str = ""):
    require_login(request)
    params = ()
    sql = """SELECT v.*, c.Name AS customer_name FROM VEHICLE v
             JOIN CUSTOMER c ON c.CustomerID=v.CustomerID"""
    if q.strip():
        sql += " WHERE v.PlateNumber ILIKE %s OR v.Brand ILIKE %s OR v.Model ILIKE %s"
        params = (f"%{q}%", f"%{q}%", f"%{q}%")
    sql += " ORDER BY v.VehicleID"
    return templates.TemplateResponse("vehicles/list.html", template_context(request, rows=fetch_all(sql, params), q=q))


@router.get("/vehicles/new")
async def vehicle_new(request: Request):
    require_login(request)
    return templates.TemplateResponse("vehicles/form.html", template_context(request, item=None, customers=fetch_all("SELECT * FROM CUSTOMER ORDER BY Name"), error=None))


@router.post("/vehicles/new")
async def vehicle_create(request: Request, csrf_token: str = Form(...), platenumber: str = Form(...), brand: str = Form(...), model: str = Form(...), year: int = Form(None), customerid: int = Form(...)):
    require_login(request)
    check_csrf(request, csrf_token)
    customers = fetch_all("SELECT * FROM CUSTOMER ORDER BY Name")
    if not (1900 <= year <= 2100) if year else False:
        return templates.TemplateResponse("vehicles/form.html", template_context(request, item=None, customers=customers, error="Year must be between 1900 and 2100."), status_code=400)
    try:
        with transaction() as conn:
            conn.execute("INSERT INTO VEHICLE (PlateNumber,Brand,Model,Year,CustomerID) VALUES (%s,%s,%s,%s,%s)", (platenumber.strip(), brand.strip(), model.strip(), year, customerid))
    except UniqueViolation:
        return templates.TemplateResponse("vehicles/form.html", template_context(request, item=None, customers=customers, error="That plate number already exists."), status_code=400)
    return RedirectResponse("/vehicles", status_code=303)


@router.get("/vehicles/{vehicle_id}/edit")
async def vehicle_edit(request: Request, vehicle_id: int):
    require_login(request)
    item = fetch_one("SELECT * FROM VEHICLE WHERE VehicleID=%s", (vehicle_id,))
    if not item:
        return RedirectResponse("/vehicles", status_code=303)
    return templates.TemplateResponse("vehicles/form.html", template_context(request, item=item, customers=fetch_all("SELECT * FROM CUSTOMER ORDER BY Name"), error=None))


@router.post("/vehicles/{vehicle_id}/edit")
async def vehicle_update(request: Request, vehicle_id: int, csrf_token: str = Form(...), platenumber: str = Form(...), brand: str = Form(...), model: str = Form(...), year: int = Form(None), customerid: int = Form(...)):
    require_login(request)
    check_csrf(request, csrf_token)
    try:
        with transaction() as conn:
            conn.execute("UPDATE VEHICLE SET PlateNumber=%s,Brand=%s,Model=%s,Year=%s,CustomerID=%s WHERE VehicleID=%s", (platenumber.strip(), brand.strip(), model.strip(), year, customerid, vehicle_id))
    except UniqueViolation:
        item = fetch_one("SELECT * FROM VEHICLE WHERE VehicleID=%s", (vehicle_id,))
        return templates.TemplateResponse("vehicles/form.html", template_context(request, item=item, customers=fetch_all("SELECT * FROM CUSTOMER ORDER BY Name"), error="That plate number already exists."), status_code=400)
    return RedirectResponse("/vehicles", status_code=303)


@router.post("/vehicles/{vehicle_id}/delete")
async def vehicle_delete(request: Request, vehicle_id: int, csrf_token: str = Form(...)):
    require_role("admin")(request)
    check_csrf(request, csrf_token)
    try:
        with transaction() as conn:
            conn.execute("DELETE FROM VEHICLE WHERE VehicleID=%s", (vehicle_id,))
    except ForeignKeyViolation:
        return templates.TemplateResponse("403.html", template_context(request, message="This vehicle is still referenced and cannot be deleted."), status_code=400)
    return RedirectResponse("/vehicles", status_code=303)
