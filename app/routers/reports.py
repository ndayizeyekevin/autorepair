from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.auth import require_login
from app.db import fetch_all
from app.main import template_context

router=APIRouter();templates=Jinja2Templates(directory="app/templates")

@router.get("/reports")
async def reports(request:Request):
    require_login(request)
    query1="""SELECT r.RepairID, c.Name AS CustomerName, v.PlateNumber, v.Brand,
                     e.Name AS MechanicName, i.TotalAmount
              FROM REPAIR r
              JOIN VEHICLE v ON v.VehicleID=r.VehicleID
              JOIN CUSTOMER c ON c.CustomerID=v.CustomerID
              JOIN EMPLOYEE e ON e.EmployeeID=r.MechanicID
              LEFT JOIN INVOICE i ON i.RepairID=r.RepairID
              ORDER BY r.RepairDate DESC"""
    query2="""SELECT e.Name AS MechanicName, COUNT(r.RepairID) AS RepairCount,
                     COALESCE(SUM(i.TotalAmount),0) AS TotalRevenue
              FROM MECHANIC m
              JOIN EMPLOYEE e ON e.EmployeeID=m.EmployeeID
              LEFT JOIN REPAIR r ON r.MechanicID=m.EmployeeID
              LEFT JOIN INVOICE i ON i.RepairID=r.RepairID
              GROUP BY e.Name
              ORDER BY TotalRevenue DESC"""
    query3="""SELECT DISTINCT c.CustomerID, c.Name
              FROM CUSTOMER c
              JOIN VEHICLE v ON v.CustomerID=c.CustomerID
              JOIN REPAIR r ON r.VehicleID=v.VehicleID
              WHERE r.Cost > (SELECT AVG(Cost) FROM REPAIR)
              ORDER BY c.Name"""
    reports=[
        {"title":"Repairs, customers, vehicles, mechanics and invoices","sql":query1,"columns":["RepairID","CustomerName","PlateNumber","Brand","MechanicName","TotalAmount"],"rows":fetch_all(query1)},
        {"title":"Revenue and repairs by mechanic","sql":query2,"columns":["MechanicName","RepairCount","TotalRevenue"],"rows":fetch_all(query2)},
        {"title":"Customers with a vehicle repaired above average cost","sql":query3,"columns":["CustomerID","Name"],"rows":fetch_all(query3)},
    ]
    return templates.TemplateResponse("reports.html",template_context(request,reports=reports))
