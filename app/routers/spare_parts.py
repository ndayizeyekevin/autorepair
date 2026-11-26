from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import ForeignKeyViolation

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router=APIRouter();templates=Jinja2Templates(directory="app/templates")

@router.get("/parts")
async def parts_list(request:Request,q:str=""):
    require_login(request)
    params=()
    sql="SELECT * FROM SPARE_PART"
    if q.strip():sql+=" WHERE PartName ILIKE %s";params=(f"%{q}%",)
    sql+=" ORDER BY PartName"
    return templates.TemplateResponse("parts/list.html",template_context(request,rows=fetch_all(sql,params),q=q))

@router.get("/parts/new")
async def part_new(request:Request):
    require_role("admin")(request)
    return templates.TemplateResponse("parts/form.html",template_context(request,item=None,error=None))

@router.post("/parts/new")
async def part_create(request:Request,csrf_token:str=Form(...),partname:str=Form(...),price:float=Form(...),stockquantity:int=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    if price<0 or stockquantity<0:return templates.TemplateResponse("parts/form.html",template_context(request,item=None,error="Price and stock must be zero or greater."),status_code=400)
    with transaction() as conn:conn.execute("INSERT INTO SPARE_PART (PartName,Price,StockQuantity) VALUES (%s,%s,%s)",(partname.strip(),price,stockquantity))
    return RedirectResponse("/parts",status_code=303)

@router.get("/parts/{part_id}/edit")
async def part_edit(request:Request,part_id:int):
    require_role("admin")(request)
    item=fetch_one("SELECT * FROM SPARE_PART WHERE PartID=%s",(part_id,))
    if not item:return RedirectResponse("/parts",status_code=303)
    return templates.TemplateResponse("parts/form.html",template_context(request,item=item,error=None))

@router.post("/parts/{part_id}/edit")
async def part_update(request:Request,part_id:int,csrf_token:str=Form(...),partname:str=Form(...),price:float=Form(...),stockquantity:int=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    if price<0 or stockquantity<0:return templates.TemplateResponse("parts/form.html",template_context(request,item=fetch_one("SELECT * FROM SPARE_PART WHERE PartID=%s",(part_id,)),error="Price and stock must be zero or greater."),status_code=400)
    with transaction() as conn:conn.execute("UPDATE SPARE_PART SET PartName=%s,Price=%s,StockQuantity=%s WHERE PartID=%s",(partname.strip(),price,stockquantity,part_id))
    return RedirectResponse("/parts",status_code=303)

@router.post("/parts/{part_id}/delete")
async def part_delete(request:Request,part_id:int,csrf_token:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    try:
        with transaction() as conn:conn.execute("DELETE FROM SPARE_PART WHERE PartID=%s",(part_id,))
    except ForeignKeyViolation:
        return templates.TemplateResponse("403.html",template_context(request,message="This spare part is referenced by a repair and cannot be deleted."),status_code=400)
    return RedirectResponse("/parts",status_code=303)
