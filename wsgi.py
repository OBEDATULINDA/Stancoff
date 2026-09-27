import app as stancoff
from production_variance_patch import apply as apply_production_variance
from station_transfer_patch import apply as apply_station_transfer

apply_production_variance(stancoff)
apply_station_transfer(stancoff)
app = stancoff.app
