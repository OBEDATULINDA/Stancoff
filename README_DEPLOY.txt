STANCOFF MULTI-USER APP

LOCAL TEST
1. Install Python 3.
2. pip install -r requirements.txt
3. python app.py
4. Open http://127.0.0.1:8000
5. Default login: admin / ChangeMe123!

RENDER DEPLOYMENT
1. Create a GitHub repository.
2. Upload all files in this folder.
3. Sign in to Render.
4. New > Blueprint.
5. Select your GitHub repository.
6. Render reads render.yaml and creates the web app and PostgreSQL database.
7. During setup, set ADMIN_PASSWORD to a strong password.
8. Open the generated HTTPS address.
9. Log in as admin.
10. Go to Users to create accounts and assign roles.

ROLES
Admin: all access
Manager: operational modules and reports
Receiving Clerk: suppliers, batches and purchases
Processing Supervisor: batches and reports
Payroll Officer: casuals, rates, attendance and payments
Viewer: dashboard and reports

PHONE INSTALL
Open the hosted address in Chrome, open the browser menu, and choose Add to Home screen.

SECURITY
Change the default password immediately.
Use a strong SECRET_KEY in production.
Only Admin can manage users and view the audit log.
