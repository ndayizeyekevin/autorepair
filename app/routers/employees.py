from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/employees")
async def list_employees(request: Request, q: str = ""):
    require_login(request)
    sql = """SELECT e.*, CASE e.Position
      WHEN 'Receptionist' THEN r.Shift || '; ' || r.Languages
      WHEN 'Manager' THEN m.Department || '; Bonus: ' || m.Bonus
      WHEN 'Mechanic' THEN mc.Specialty || '; ' || mc.ExperienceYears || ' years'
    END AS details
    FROM EMPLOYEE e
    LEFT JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID
    LEFT JOIN MANAGER m ON m.EmployeeID=e.EmployeeID
    LEFT JOIN MECHANIC mc ON mc.EmployeeID=e.EmployeeID"""
    params = ()
    if q.strip():
        sql += " WHERE e.Name ILIKE %s OR e.Position ILIKE %s"
        params = (f"%{q}%", f"%{q}%")
    sql += " ORDER BY e.EmployeeID"
    return templates.TemplateResponse("employees/list.html", template_context(request, rows=fetch_all(sql, params), q=q))


@router.get("/employees/new")
async def employee_new(request: Request):
    require_role("admin")(request)
    return templates.TemplateResponse("employees/form.html", template_context(request, item=None, error=None))


@router.post("/employees/new")
async def employee_create(request: Request, csrf_token: str = Form(...), name: str = Form(...), phone: str = Form(""), position: str = Form(...), shift: str = Form(""), languages: str = Form(""), department: str = Form(""), bonus: float = Form(None), specialty: str = Form(""), experienceyears: int = Form(None)):
    require_role("admin")(request)
    check_csrf(request, csrf_token)
    if position not in ("Receptionist","Manager","Mechanic"):
        return templates.TemplateResponse("employees/form.html", template_context(request, item=None, error="Choose a valid position."), status_code=400)
    with transaction() as conn:
        row = conn.execute("INSERT INTO EMPLOYEE (Name,Phone,Position) VALUES (%s,%s,%s) RETURNING EmployeeID", (name.strip(), phone.strip() or None, position)).fetchone()
        employee_id = row["employeeid"]
        if position == "Receptionist":
            conn.execute("INSERT INTO RECEPTIONIST (EmployeeID,Shift,Languages) VALUES (%s,%s,%s)", (employee_id, shift or None, languages or None))
        elif position == "Manager":
            conn.execute("INSERT INTO MANAGER (EmployeeID,Department,Bonus) VALUES (%s,%s,%s)", (employee_id, department or None, bonus))
        else:
            conn.execute("INSERT INTO MECHANIC (EmployeeID,Specialty,ExperienceYears) VALUES (%s,%s,%s)", (employee_id, specialty or None, experienceyears))
    return RedirectResponse("/employees", status_code=303)


@router.get("/employees/{employee_id}/edit")
async def employee_edit(request: Request, employee_id: int):
    require_role("admin")(request)
    item = fetch_one("""SELECT e.*, r.Shift,r.Languages,m.Department,m.Bonus,mc.Specialty,mc.ExperienceYears
                        FROM EMPLOYEE e
                        LEFT JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID
                        LEFT JOIN MANAGER m ON m.EmployeeID=e.EmployeeID
                        LEFT JOIN MECHANIC mc ON mc.EmployeeID=e.EmployeeID
                        WHERE e.EmployeeID=%s""", (employee_id,))
    if not item:
        return RedirectResponse("/employees", status_code=303)
    return templates.TemplateResponse("employees/form.html", template_context(request, item=item, error=None))


@router.post("/employees/{employee_id}/edit")
async def employee_update(request: Request, employee_id: int, csrf_token: str = Form(...), name: str = Form(...), phone: str = Form(""), position: str = Form(...), shift: str = Form(""), languages: str = Form(""), department: str = Form(""), bonus: float = Form(None), specialty: str = Form(""), experienceyears: int = Form(None)):
    require_role("admin")(request)
    check_csrf(request, csrf_token)
    with transaction() as conn:
        conn.execute("UPDATE EMPLOYEE SET Name=%s,Phone=%s WHERE EmployeeID=%s", (name.strip(), phone.strip() or None, employee_id))
        if position == "Receptionist":
            conn.execute("UPDATE RECEPTIONIST SET Shift=%s,Languages=%s WHERE EmployeeID=%s", (shift or None, languages or None, employee_id))
        elif position == "Manager":
            conn.execute("UPDATE MANAGER SET Department=%s,Bonus=%s WHERE EmployeeID=%s", (department or None, bonus, employee_id))
        else:
            conn.execute("UPDATE MECHANIC SET Specialty=%s,ExperienceYears=%s WHERE EmployeeID=%s", (specialty or None, experienceyears, employee_id))
    return RedirectResponse("/employees", status_code=303)


@router.post("/employees/{employee_id}/delete")
async def employee_delete(request: Request, employee_id: int, csrf_token: str = Form(...)):
    require_role("admin")(request)
    check_csrf(request, csrf_token)
    with transaction() as conn:
        conn.execute("DELETE FROM EMPLOYEE WHERE EmployeeID=%s", (employee_id,))
    return RedirectResponse("/employees", status_code=303)
