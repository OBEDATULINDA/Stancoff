"""Production variance rule for Commercial Coffee production.

Gains and losses are both valid. Variances above 50 kg are flagged for review.
"""
from flask import flash


def apply(app_module):
    def calculate(row, values):
        process_type = row.process_type
        if row.source_coffee_type == "DRUGAR FAQ":
            if process_type == "Hulling Only":
                clean = values["hulled_output"]
            elif process_type == "Gravity Table Only":
                clean = values["gravity_clean_weight"]
            elif process_type == "Color Sorting Only":
                clean = values["color_sorted_weight"]
            else:
                clean = values["drugar_clean_weight"]
        else:
            if process_type == "Hulling Only":
                clean = values["hulled_output"]
            elif process_type == "Grading Only":
                clean = values["aa_weight"] + values["ab_weight"] + values["cpb_weight"] + values["wugar_weight"]
            elif process_type == "Gravity Table Only":
                clean = values["gravity_clean_weight"]
            elif process_type == "Color Sorting Only":
                clean = values["color_sorted_weight"]
            else:
                clean = values["aa_weight"] + values["ab_weight"] + values["cpb_weight"] + values["wugar_weight"]

        if clean <= 0:
            raise ValueError("Enter the actual clean/grade output before completing production.")

        byproducts = (
            values["blacks"] + values["triage"] + values["broken"] + values["pods"] +
            values["dust"] + values["stones"] + values["rabble"] +
            values["foreign_matter"] + values["other_byproducts"]
        )
        total_accounted = clean + byproducts
        confirmed_input = float(row.actual_input_weight or 0)
        variance = confirmed_input - total_accounted

        if abs(variance) > 50.0:
            direction = "loss" if variance > 0 else "gain"
            flash(
                f"Production variance warning: {abs(variance):,.2f} kg {direction}. "
                "This is above the 50 kg review threshold; the production record has still been allowed.",
                "warning",
            )

        outturn = (clean / confirmed_input * 100) if confirmed_input else 0
        mass_balance = (total_accounted / confirmed_input * 100) if confirmed_input else 0
        return clean, byproducts, variance, outturn, mass_balance

    app_module._mhs_calculate_production = calculate
