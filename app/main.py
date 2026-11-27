import secrets

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import PORT, SECRET_KEY, SEED_DEMO_USERS
from app.auth import check_csrf, ensure_csrf, hash_password, verify_password
from app.db import fetch_all, fetch_one, transaction, wait_for_database

app = FastAPI(title="Auto Service Management System")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    if request.url.path.startswith("/api"):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "403.html",
        {"request": request, "message": "Please log in to continue."},
        status_code=401,
    )


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse(
        "403.html",
        {"request": request, "message": "You do not have permission to perform this action."},
        status_code=403,
    )


@app.on_event("startup")
async def startup():
    wait_for_database()
    if SEED_DEMO_USERS:
        with transaction() as conn:
            for username, password, role in (
                ("admin", "Admin123!", "admin"),
                ("user", "User123!", "user"),
            ):
                exists = conn.execute(
                    "SELECT 1 FROM APP_USER WHERE Username = %s", (username,)
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO APP_USER (Username, PasswordHash, Role) VALUES (%s, %s, %s)",
                        (username, hash_password(password), role),
                    )


def current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return fetch_one(
        "SELECT UserID, Username, Role FROM APP_USER WHERE UserID = %s",
        (user_id,),
    )


def template_context(request: Request, **values):
    context = {
        "request": request,
        "user": current_user(request),
        "csrf_token": ensure_csrf(request),
    }
    context.update(values)
    return context


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    counts = fetch_one(
        """
        SELECT
          (SELECT COUNT(*) FROM CUSTOMER) AS customers,
          (SELECT COUNT(*) FROM VEHICLE) AS vehicles,
          (SELECT COUNT(*) FROM APPOINTMENT WHERE Status IN ('Pending','Confirmed')) AS open_appointments,
          (SELECT COUNT(*) FROM REPAIR) AS repairs,
          (SELECT COALESCE(SUM(TotalAmount),0) FROM INVOICE) AS total_invoiced
        """
    )
    monthly_revenue = fetch_all(
        """
        SELECT TO_CHAR(months.month_start, 'Mon') AS month,
               COALESCE(SUM(invoice.TotalAmount), 0)::float AS revenue
        FROM generate_series(
          date_trunc('month', CURRENT_DATE) - INTERVAL '5 months',
          date_trunc('month', CURRENT_DATE),
          INTERVAL '1 month'
        ) AS months(month_start)
        LEFT JOIN INVOICE invoice
          ON invoice.InvoiceDate >= months.month_start
         AND invoice.InvoiceDate < months.month_start + INTERVAL '1 month'
        GROUP BY months.month_start
        ORDER BY months.month_start
        """
    )
    appointment_statuses = fetch_all(
        "SELECT Status AS status, COUNT(*) AS count FROM APPOINTMENT GROUP BY Status ORDER BY count DESC"
    )
    return templates.TemplateResponse(
        "dashboard.html",
        template_context(
            request,
            counts=counts,
            chart_months=[row["month"] for row in monthly_revenue],
            chart_revenue=[row["revenue"] for row in monthly_revenue],
            appointment_status_labels=[row["status"] for row in appointment_statuses],
            appointment_status_counts=[row["count"] for row in appointment_statuses],
        ),
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if current_user(request):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", template_context(request, error=None))


@app.post("/login")
async def login(request: Request, csrf_token: str = Form(...), username: str = Form(...), password: str = Form(...)):
    from app.auth import check_csrf
    check_csrf(request, csrf_token)
    user = fetch_one(
        "SELECT UserID, Username, PasswordHash, Role FROM APP_USER WHERE Username = %s",
        (username,),
    )
    if not user or not verify_password(password, user["passwordhash"]):
        return templates.TemplateResponse(
            "login.html",
            template_context(request, error="Invalid username or password."),
            status_code=401,
        )
    request.session["user_id"] = user["userid"]
    request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/", status_code=303)


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")):
    from app.auth import check_csrf
    check_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
async def profile(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        "profile.html",
        template_context(request, password_error=None, password_success=None),
    )


@app.post("/profile/password", response_class=HTMLResponse)
async def change_password(
    request: Request,
    csrf_token: str = Form(...),
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    check_csrf(request, csrf_token)
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    account = fetch_one(
        "SELECT PasswordHash FROM APP_USER WHERE UserID = %s",
        (user_id,),
    )
    error = None
    if not account:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
    if not verify_password(current_password, account["passwordhash"]):
        error = "Your current password is incorrect."
    elif len(new_password.encode("utf-8")) < 8 or len(new_password.encode("utf-8")) > 72:
        error = "The new password must be between 8 and 72 bytes."
    elif new_password != confirm_password:
        error = "The new password and confirmation do not match."
    elif verify_password(new_password, account["passwordhash"]):
        error = "Choose a new password that differs from your current password."

    if error:
        return templates.TemplateResponse(
            "profile.html",
            template_context(request, password_error=error, password_success=None),
            status_code=400,
        )

    with transaction() as conn:
        conn.execute(
            "UPDATE APP_USER SET PasswordHash = %s WHERE UserID = %s",
            (hash_password(new_password), user_id),
        )
    request.session["csrf"] = secrets.token_urlsafe(32)
    return templates.TemplateResponse(
        "profile.html",
        template_context(
            request,
            password_error=None,
            password_success="Your password was updated successfully.",
        ),
    )


@app.get("/health")
async def health():
    fetch_one("SELECT 1")
    return {"status": "ok"}


from app.routers import customers, vehicles, employees, appointments, repairs, invoices, spare_parts, users, reports
app.include_router(customers.router)
app.include_router(vehicles.router)
app.include_router(employees.router)
app.include_router(appointments.router)
app.include_router(repairs.router)
app.include_router(invoices.router)
app.include_router(spare_parts.router)
app.include_router(users.router)
app.include_router(reports.router)
