from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router=APIRouter()
templates=Jinja2Templates(directory="app/templates")


@router.get("/repairs")
async def repair_list(request:Request,q:str=""):
    require_login(request)
    sql="""SELECT r.*,v.PlateNumber vehicle_plate,e.Name mechanic_name FROM REPAIR r JOIN VEHICLE v ON v.VehicleID=r.VehicleID JOIN EMPLOYEE e ON e.EmployeeID=r.MechanicID"""
    params=()
    if q.strip():
        sql+=" WHERE r.ProblemDescription ILIKE %s OR v.PlateNumber ILIKE %s OR e.Name ILIKE %s";params=(f"%{q}%","%"+q+"%","%"+q+"%")
    sql+=" ORDER BY r.RepairDate DESC"
    return templates.TemplateResponse("repairs/list.html",template_context(request,rows=fetch_all(sql,params),q=q))


@router.get("/repairs/new")
async def repair_new(request:Request):
    require_login(request)
    return templates.TemplateResponse("repairs/form.html",template_context(request,item=None,error=None,vehicles=fetch_all("SELECT * FROM VEHICLE ORDER BY PlateNumber"),mechanics=fetch_all("SELECT e.EmployeeID,e.Name,m.Specialty FROM EMPLOYEE e JOIN MECHANIC m ON m.EmployeeID=e.EmployeeID")))


@router.post("/repairs/new")
async def repair_create(request:Request,csrf_token:str=Form(...),repairdate:str=Form(...),cost:float=Form(0),problemdescription:str=Form(""),vehicleid:int=Form(...),mechanicid:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    if cost<0:return templates.TemplateResponse("repairs/form.html",template_context(request,item=None,error="Cost cannot be negative.",vehicles=fetch_all("SELECT * FROM VEHICLE"),mechanics=fetch_all("SELECT e.EmployeeID,e.Name,m.Specialty FROM EMPLOYEE e JOIN MECHANIC m ON m.EmployeeID=e.EmployeeID")),status_code=400)
    with transaction() as conn:
        conn.execute("INSERT INTO REPAIR (ProblemDescription,RepairDate,Cost,VehicleID,MechanicID) VALUES (%s,%s,%s,%s,%s)",(problemdescription or None,repairdate,cost,vehicleid,mechanicid))
    return RedirectResponse("/repairs",status_code=303)


@router.get("/repairs/{repair_id}/edit")
async def repair_edit(request:Request,repair_id:int):
    require_login(request)
    item=fetch_one("SELECT * FROM REPAIR WHERE RepairID=%s",(repair_id,))
    if not item:return RedirectResponse("/repairs",status_code=303)
    return templates.TemplateResponse("repairs/form.html",template_context(request,item=item,error=None,vehicles=fetch_all("SELECT * FROM VEHICLE"),mechanics=fetch_all("SELECT e.EmployeeID,e.Name,m.Specialty FROM EMPLOYEE e JOIN MECHANIC m ON m.EmployeeID=e.EmployeeID")))


@router.post("/repairs/{repair_id}/edit")
async def repair_update(request:Request,repair_id:int,csrf_token:str=Form(...),repairdate:str=Form(...),cost:float=Form(0),problemdescription:str=Form(""),vehicleid:int=Form(...),mechanicid:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    with transaction() as conn:
        conn.execute("UPDATE REPAIR SET ProblemDescription=%s,RepairDate=%s,Cost=%s,VehicleID=%s,MechanicID=%s WHERE RepairID=%s",(problemdescription or None,repairdate,cost,vehicleid,mechanicid,repair_id))
    return RedirectResponse("/repairs",status_code=303)


@router.get("/repairs/{repair_id}")
async def repair_detail(request:Request,repair_id:int):
    require_login(request)
    repair=fetch_one("""SELECT r.*,v.PlateNumber vehicle_plate,e.Name mechanic_name FROM REPAIR r JOIN VEHICLE v ON v.VehicleID=r.VehicleID JOIN EMPLOYEE e ON e.EmployeeID=r.MechanicID WHERE r.RepairID=%s""",(repair_id,))
    if not repair:return RedirectResponse("/repairs",status_code=303)
    parts=fetch_all("""SELECT rp.PartID,rp.Quantity,p.PartName,p.Price FROM REPAIR_PART rp JOIN SPARE_PART p ON p.PartID=rp.PartID WHERE rp.RepairID=%s""",(repair_id,))
    invoice=fetch_one("SELECT * FROM INVOICE WHERE RepairID=%s",(repair_id,))
    proposed=fetch_one("""SELECT COALESCE((SELECT Cost FROM REPAIR WHERE RepairID=%s),0)+COALESCE((SELECT SUM(rp.Quantity*p.Price) FROM REPAIR_PART rp JOIN SPARE_PART p ON p.PartID=rp.PartID WHERE rp.RepairID=%s),0) AS proposed""",(repair_id,repair_id))["proposed"]
    return templates.TemplateResponse("repairs/detail.html",template_context(request,repair=repair,parts=parts,invoice=invoice,proposed=proposed,available=fetch_all("SELECT * FROM SPARE_PART WHERE StockQuantity>0 ORDER BY PartName")))


@router.post("/repairs/{repair_id}/parts")
async def add_repair_part(request:Request,repair_id:int,csrf_token:str=Form(...),partid:int=Form(...),quantity:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    if quantity<1:return templates.TemplateResponse("403.html",template_context(request,message="Quantity must be at least 1."),status_code=400)
    try:
        with transaction() as conn:
            part=conn.execute("SELECT StockQuantity FROM SPARE_PART WHERE PartID=%s",(partid,)).fetchone()
            existing=conn.execute("SELECT Quantity FROM REPAIR_PART WHERE RepairID=%s AND PartID=%s",(repair_id,partid)).fetchone()
            if existing:return RedirectResponse(f"/repairs/{repair_id}",status_code=303)
            if not part or quantity>part["stockquantity"]:
                raise ValueError("The requested quantity exceeds available stock.")
            conn.execute("INSERT INTO REPAIR_PART (RepairID,PartID,Quantity) VALUES (%s,%s,%s)",(repair_id,partid,quantity))
            conn.execute("UPDATE SPARE_PART SET StockQuantity=StockQuantity-%s WHERE PartID=%s",(quantity,partid))
    except ValueError as exc:return templates.TemplateResponse("403.html",template_context(request,message=str(exc)),status_code=400)
    return RedirectResponse(f"/repairs/{repair_id}",status_code=303)


@router.post("/repairs/{repair_id}/parts/{part_id}/quantity")
async def edit_repair_part(request:Request,repair_id:int,part_id:int,csrf_token:str=Form(...),quantity:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    if quantity<1:return templates.TemplateResponse("403.html",template_context(request,message="Quantity must be at least 1."),status_code=400)
    try:
        with transaction() as conn:
            row=conn.execute("SELECT Quantity FROM REPAIR_PART WHERE RepairID=%s AND PartID=%s",(repair_id,part_id)).fetchone()
            stock=conn.execute("SELECT StockQuantity FROM SPARE_PART WHERE PartID=%s",(part_id,)).fetchone()
            needed=quantity-row["quantity"]
            if needed>stock["stockquantity"]:raise ValueError("The requested quantity exceeds available stock.")
            conn.execute("UPDATE REPAIR_PART SET Quantity=%s WHERE RepairID=%s AND PartID=%s",(quantity,repair_id,part_id))
            conn.execute("UPDATE SPARE_PART SET StockQuantity=StockQuantity-%s WHERE PartID=%s",(needed,part_id))
    except ValueError as exc:return templates.TemplateResponse("403.html",template_context(request,message=str(exc)),status_code=400)
    return RedirectResponse(f"/repairs/{repair_id}",status_code=303)


@router.post("/repairs/{repair_id}/parts/{part_id}/remove")
async def remove_repair_part(request:Request,repair_id:int,part_id:int,csrf_token:str=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    with transaction() as conn:
        row=conn.execute("SELECT Quantity FROM REPAIR_PART WHERE RepairID=%s AND PartID=%s",(repair_id,part_id)).fetchone()
        if row:
            conn.execute("UPDATE SPARE_PART SET StockQuantity=StockQuantity+%s WHERE PartID=%s",(row["quantity"],part_id))
            conn.execute("DELETE FROM REPAIR_PART WHERE RepairID=%s AND PartID=%s",(repair_id,part_id))
    return RedirectResponse(f"/repairs/{repair_id}",status_code=303)


@router.post("/repairs/{repair_id}/generate-invoice")
async def generate_invoice(request:Request,repair_id:int,csrf_token:str=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    existing=fetch_one("SELECT 1 FROM INVOICE WHERE RepairID=%s",(repair_id,))
    if existing:return RedirectResponse(f"/repairs/{repair_id}",status_code=303)
    with transaction() as conn:
        total=conn.execute("""SELECT COALESCE((SELECT Cost FROM REPAIR WHERE RepairID=%s),0)+COALESCE((SELECT SUM(rp.Quantity*p.Price) FROM REPAIR_PART rp JOIN SPARE_PART p ON p.PartID=rp.PartID WHERE rp.RepairID=%s),0) AS total""",(repair_id,repair_id)).fetchone()["total"]
        conn.execute("INSERT INTO INVOICE (InvoiceDate,TotalAmount,RepairID) VALUES (NOW(),%s,%s)",(total,repair_id))
    return RedirectResponse(f"/repairs/{repair_id}",status_code=303)


@router.post("/repairs/{repair_id}/delete")
async def repair_delete(request:Request,repair_id:int,csrf_token:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    with transaction() as conn:conn.execute("DELETE FROM REPAIR WHERE RepairID=%s",(repair_id,))
    return RedirectResponse("/repairs",status_code=303)
