from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import check_csrf, require_login, require_role
from app.db import fetch_all, fetch_one, transaction
from app.main import template_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
STATUSES = ["Pending","Confirmed","Completed","Cancelled"]


@router.get("/appointments")
async def list_appointments(request: Request, status: str = ""):
    require_login(request)
    sql = """SELECT a.*,c.Name customer_name,v.PlateNumber vehicle_plate,e.Name receptionist_name
             FROM APPOINTMENT a JOIN CUSTOMER c ON c.CustomerID=a.CustomerID
             JOIN VEHICLE v ON v.VehicleID=a.VehicleID JOIN EMPLOYEE e ON e.EmployeeID=a.ReceptionistID"""
    params = ()
    if status:
        sql += " WHERE a.Status=%s"; params=(status,)
    sql += " ORDER BY a.AppointmentDate DESC"
    return templates.TemplateResponse("appointments/list.html", template_context(request, rows=fetch_all(sql,params), statuses=STATUSES, status=status))


@router.get("/appointments/vehicles/{customer_id}")
async def appointment_vehicles(request: Request, customer_id: int):
    require_login(request)
    return fetch_all("SELECT VehicleID,PlateNumber,Brand,Model FROM VEHICLE WHERE CustomerID=%s ORDER BY PlateNumber",(customer_id,))


@router.get("/appointments/new")
async def appointment_new(request: Request):
    require_login(request)
    return templates.TemplateResponse("appointments/form.html", template_context(request,item=None,error=None,statuses=STATUSES,
        customers=fetch_all("SELECT * FROM CUSTOMER ORDER BY Name"),
        vehicles=[],
        receptionists=fetch_all("SELECT e.EmployeeID,e.Name FROM EMPLOYEE e JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID ORDER BY e.Name")))


@router.post("/appointments/new")
async def appointment_create(request: Request, csrf_token: str=Form(...), appointmentdate: str=Form(...), status: str=Form(...), customerid:int=Form(...), vehicleid:int=Form(...), receptionistid:int=Form(...)):
    require_login(request); check_csrf(request,csrf_token)
    vehicle=fetch_one("SELECT 1 FROM VEHICLE WHERE VehicleID=%s AND CustomerID=%s",(vehicleid,customerid))
    if status not in STATUSES or not vehicle:
        return templates.TemplateResponse("appointments/form.html",template_context(request,item=None,error="Choose a valid status and a vehicle belonging to the selected customer.",statuses=STATUSES,customers=fetch_all("SELECT * FROM CUSTOMER"),vehicles=[],receptionists=fetch_all("SELECT e.EmployeeID,e.Name FROM EMPLOYEE e JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID")),status_code=400)
    with transaction() as conn:
        conn.execute("INSERT INTO APPOINTMENT (AppointmentDate,Status,CustomerID,VehicleID,ReceptionistID) VALUES (%s,%s,%s,%s,%s)",(appointmentdate,status,customerid,vehicleid,receptionistid))
    return RedirectResponse("/appointments",status_code=303)


@router.get("/appointments/{appointment_id}/edit")
async def appointment_edit(request: Request,appointment_id:int):
    require_login(request)
    item=fetch_one("SELECT * FROM APPOINTMENT WHERE AppointmentID=%s",(appointment_id,))
    if not item:return RedirectResponse("/appointments",status_code=303)
    return templates.TemplateResponse("appointments/form.html",template_context(request,item=item,error=None,statuses=STATUSES,customers=fetch_all("SELECT * FROM CUSTOMER ORDER BY Name"),vehicles=fetch_all("SELECT * FROM VEHICLE WHERE CustomerID=%s",(item["customerid"],)),receptionists=fetch_all("SELECT e.EmployeeID,e.Name FROM EMPLOYEE e JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID")))


@router.post("/appointments/{appointment_id}/edit")
async def appointment_update(request: Request,appointment_id:int,csrf_token:str=Form(...),appointmentdate:str=Form(...),status:str=Form(...),customerid:int=Form(...),vehicleid:int=Form(...),receptionistid:int=Form(...)):
    require_login(request);check_csrf(request,csrf_token)
    if status not in STATUSES or not fetch_one("SELECT 1 FROM VEHICLE WHERE VehicleID=%s AND CustomerID=%s",(vehicleid,customerid)):
        item=fetch_one("SELECT * FROM APPOINTMENT WHERE AppointmentID=%s",(appointment_id,))
        return templates.TemplateResponse("appointments/form.html",template_context(request,item=item,error="Invalid status or vehicle/customer combination.",statuses=STATUSES,customers=fetch_all("SELECT * FROM CUSTOMER"),vehicles=[],receptionists=fetch_all("SELECT e.EmployeeID,e.Name FROM EMPLOYEE e JOIN RECEPTIONIST r ON r.EmployeeID=e.EmployeeID")),status_code=400)
    with transaction() as conn:
        conn.execute("UPDATE APPOINTMENT SET AppointmentDate=%s,Status=%s,CustomerID=%s,VehicleID=%s,ReceptionistID=%s WHERE AppointmentID=%s",(appointmentdate,status,customerid,vehicleid,receptionistid,appointment_id))
    return RedirectResponse("/appointments",status_code=303)


@router.post("/appointments/{appointment_id}/delete")
async def appointment_delete(request:Request,appointment_id:int,csrf_token:str=Form(...)):
    require_role("admin")(request);check_csrf(request,csrf_token)
    with transaction() as conn:conn.execute("DELETE FROM APPOINTMENT WHERE AppointmentID=%s",(appointment_id,))
    return RedirectResponse("/appointments",status_code=303)
