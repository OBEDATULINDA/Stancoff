import app as stancoff
from production_variance_patch import apply

apply(stancoff)
app = stancoff.app
