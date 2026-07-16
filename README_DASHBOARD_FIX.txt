STANCOFF DASHBOARD SERVER ERROR FIX

Cause addressed:
The dashboard used database-specific SQL grouping and date functions.
The updated dashboard now aggregates purchases in Python, so it works with:
- PostgreSQL on Render
- SQLite during local testing

Update steps:
1. Extract this ZIP.
2. Replace app.py in GitHub.
3. Also replace templates/dashboard.html, templates/base.html and static/style.css
   if those files were not already updated.
4. Commit the changes.
5. In Render choose Manual Deploy > Clear build cache & deploy.
6. Log in and open Dashboard.

The PostgreSQL database and existing records are not deleted or changed.
