from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.errors import UniqueViolation

from app.auth import check_csrf, hash_password, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router=APIRouter();templates=Jinja2Templates(directory="app/templates")

@router.get("/users")
async def users_list(request:Request):
    require_role("admin")(request)
    return templates.TemplateResponse("users/list.html",template_context(request,rows=fetch_all("SELECT UserID,Username,Role FROM APP_USER ORDER BY Username")))

@router.get("/users/new")
async def user_new(request:Request):
    require_role("admin")(request)
    return templates.TemplateResponse("users/form.html",template_context(request,item=None,error=None))

@router.post("/users/new")
async def user_create(request:Request,csrf_token:str=Form(...),username:str=Form(...),password:str=Form(...),role:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    if role not in ("admin","user") or len(password)<8:
        return templates.TemplateResponse("users/form.html",template_context(request,item=None,error="Use role admin or user and a password of at least 8 characters."),status_code=400)
    try:
        with transaction() as conn:conn.execute("INSERT INTO APP_USER (Username,PasswordHash,Role) VALUES (%s,%s,%s)",(username.strip(),hash_password(password),role))
    except UniqueViolation:
        return templates.TemplateResponse("users/form.html",template_context(request,item=None,error="Username already exists."),status_code=400)
    return RedirectResponse("/users",status_code=303)

@router.get("/users/{user_id}/edit")
async def user_edit(request:Request,user_id:int):
    require_role("admin")(request)
    item=fetch_one("SELECT UserID,Username,Role FROM APP_USER WHERE UserID=%s",(user_id,))
    return templates.TemplateResponse("users/form.html",template_context(request,item=item,error=None))

@router.post("/users/{user_id}/edit")
async def user_update(request:Request,user_id:int,csrf_token:str=Form(...),username:str=Form(...),password:str=Form(""),role:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    try:
        with transaction() as conn:
            if password:
                conn.execute("UPDATE APP_USER SET Username=%s,PasswordHash=%s,Role=%s WHERE UserID=%s",(username.strip(),hash_password(password),role,user_id))
            else:
                conn.execute("UPDATE APP_USER SET Username=%s,Role=%s WHERE UserID=%s",(username.strip(),role,user_id))
    except UniqueViolation:
        return templates.TemplateResponse("users/form.html",template_context(request,item=fetch_one("SELECT UserID,Username,Role FROM APP_USER WHERE UserID=%s",(user_id,)),error="Username already exists."),status_code=400)
    return RedirectResponse("/users",status_code=303)

@router.post("/users/{user_id}/delete")
async def user_delete(request:Request,user_id:int,csrf_token:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    with transaction() as conn:conn.execute("DELETE FROM APP_USER WHERE UserID=%s",(user_id,))
    return RedirectResponse("/users",status_code=303)
