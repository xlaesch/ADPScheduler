import csv
import ast
from ortools.sat.python import cp_model

# =============================================================================
# 1. Read and parse the CSV file containing student availabilities.
#
# For each student, we assume that the CSV lists the shifts when the student
# is available (i.e. not in class). However, if the shifts "20:00-23:00" and 
# "23:00-2:00" are missing, we add them—assuming that all students are available 
# during those times.
# =============================================================================
students = []
student_can_drive = {}        # Map: student name -> boolean
student_availability = {}     # Map: student name -> { day: set(shifts) }

# List of all days for which we want to ensure availability
all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

csv_file = 'processed_student_availability.csv'
with open(csv_file, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row['name'].strip()
        students.append(name)
        student_can_drive[name] = row['can_drive'].strip().lower() == 'true'
        # Parse the availability dictionary stored as a string.
        try:
            avail_dict = ast.literal_eval(row['availability'])
        except Exception as e:
            print(f"Error parsing availability for {name}: {e}")
            avail_dict = {}
        avail_clean = {}
        # Process each day in the CSV (if any)
        for day, shift_list in avail_dict.items():
            # Remove duplicates by converting to a set.
            avail_clean[day] = set(shift_list)
            # Ensure that the missing evening shifts are added.
            avail_clean[day].update(["20:00-23:00", "23:00-2:00"])
        # Also, for any day missing from the CSV, assume the student is available
        # for the evening shifts.
        for day in all_days:
            if day not in avail_clean:
                avail_clean[day] = {"20:00-23:00", "23:00-2:00"}
        student_availability[name] = avail_clean

# =============================================================================
# 2. Define days, shifts, and per-shift "desired" requirements.
#
# We now have seven shifts per day:
#   - "02:00-08:00": The special night shift; hard-constrained to 2 workers.
#   - "08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00",
#     "20:00-23:00", "23:00-2:00": Regular 3-hour shifts.
#
# For the regular shifts, the ideal coverage is 3 workers (with at least 2 drivers)
# but if needed, 2 workers (with at least 1 driver) can be used.
#
# Also, on Tuesday, Thursday, and Sunday the "17:00-20:00" shift is off.
# =============================================================================
days = all_days

shifts = [
    "02:00-08:00",  # Night shift: fixed to 2 assignments.
    "08:00-11:00",
    "11:00-14:00",
    "14:00-17:00",
    "17:00-20:00",  # Off on Tue, Thu, and Sun.
    "20:00-23:00",
    "23:00-2:00"
]

# Define the "desired" coverage for each (day, shift)
shift_desired = {}
shift_driver_desired = {}  # Desired driver count when fully staffed.
for d in days:
    # Night shift:
    shift_desired[(d, "02:00-08:00")] = 2
    shift_driver_desired[(d, "02:00-08:00")] = 1

    # Regular 3-hour shifts:
    for sh in ["08:00-11:00", "11:00-14:00", "14:00-17:00", "20:00-23:00", "23:00-2:00"]:
        shift_desired[(d, sh)] = 3
        shift_driver_desired[(d, sh)] = 2  # When fully staffed.
    # The "17:00-20:00" shift:
    if d in ["Tuesday", "Thursday", "Sunday"]:
        shift_desired[(d, "17:00-20:00")] = 0
        shift_driver_desired[(d, "17:00-20:00")] = 0
    else:
        shift_desired[(d, "17:00-20:00")] = 3
        shift_driver_desired[(d, "17:00-20:00")] = 2

# =============================================================================
# 3. Create the CP-SAT model and decision variables.
#
# A binary decision variable is created for each (student, day, shift)
# if the student is available.
# =============================================================================
model = cp_model.CpModel()

assignment = {}  # (s, d, sh) -> BoolVar
for s in students:
    for d in days:
        for sh in shifts:
            # For the evening shifts ("20:00-23:00" and "23:00-2:00"), we now assume
            # availability even if not present in the CSV.
            if sh in ["20:00-23:00", "23:00-2:00"]:
                available = True
            else:
                available = (d in student_availability[s] and sh in student_availability[s][d])
            if available:
                assignment[(s, d, sh)] = model.NewBoolVar(f"{s}_{d}_{sh}")

# =============================================================================
# 4. Coverage constraints & soft relaxation.
#
# For each (day, shift):
#   - For the night shift ("02:00-08:00"): enforce exactly 2 assignments.
#   - For off shifts (desired = 0): enforce 0 assignments.
#   - For every other (regular) shift, allow between 0 and 3 assignments.
#
# For regular shifts we also define:
#   - assigned_sum[(d,sh)] = total number of workers assigned.
#   - slack[(d,sh)] = 3 - assigned_sum (penalty for missing full coverage).
#   - missing[(d,sh)] = max(0, 2 - assigned_sum) (extra penalty if fewer than 2 are assigned).
# =============================================================================
assigned_sum = {}  # (d,sh) -> IntVar (number of workers assigned)
slack = {}       # (d,sh) -> IntVar: 3 - assigned_sum.
missing = {}     # (d,sh) -> IntVar: max(0, 2 - assigned_sum).

for d in days:
    for sh in shifts:
        vars_for_shift = [assignment[(s, d, sh)] for s in students if (s, d, sh) in assignment]
        if sh == "02:00-08:00":
            model.Add(sum(vars_for_shift) == shift_desired[(d, sh)])
        elif shift_desired[(d, sh)] == 0:
            model.Add(sum(vars_for_shift) == 0)
        else:
            model.Add(sum(vars_for_shift) <= 3)
            assigned_sum[(d, sh)] = model.NewIntVar(0, 3, f"assigned_{d}_{sh}")
            model.Add(assigned_sum[(d, sh)] == sum(vars_for_shift))
            slack[(d, sh)] = model.NewIntVar(0, 3, f"slack_{d}_{sh}")
            model.Add(slack[(d, sh)] == 3 - assigned_sum[(d, sh)])
            missing[(d, sh)] = model.NewIntVar(0, 2, f"missing_{d}_{sh}")
            model.AddMaxEquality(missing[(d, sh)], [2 - assigned_sum[(d, sh)], 0])

# =============================================================================
# 5. Driver constraints.
#
# For every shift, compute the sum over drivers.
# For:
#   - Night shifts: require at least 1 driver.
#   - Regular shifts: if any worker is assigned then at least 1 driver;
#     and if fully staffed (3) then at least 2 drivers.
# =============================================================================
for d in days:
    for sh in shifts:
        driver_vars = [assignment[(s, d, sh)] for s in students 
                       if (s, d, sh) in assignment and student_can_drive[s]]
        if sh == "02:00-08:00":
            model.Add(sum(driver_vars) >= 1)
        elif shift_desired[(d, sh)] == 0:
            pass  # Off shift; no workers assigned.
        else:
            if (d, sh) in assigned_sum:
                nonempty = model.NewBoolVar(f"nonempty_{d}_{sh}")
                model.Add(assigned_sum[(d, sh)] >= 1).OnlyEnforceIf(nonempty)
                model.Add(assigned_sum[(d, sh)] == 0).OnlyEnforceIf(nonempty.Not())
                model.Add(sum(driver_vars) >= 1).OnlyEnforceIf(nonempty)
                full = model.NewBoolVar(f"full_{d}_{sh}")
                model.Add(assigned_sum[(d, sh)] == 3).OnlyEnforceIf(full)
                model.Add(assigned_sum[(d, sh)] != 3).OnlyEnforceIf(full.Not())
                model.Add(sum(driver_vars) >= 2).OnlyEnforceIf(full)

# =============================================================================
# 6. Night shift frequency.
#
# Each student may work the "02:00-08:00" shift at most once per week.
# =============================================================================
for s in students:
    night_vars = [assignment[(s, d, "02:00-08:00")] for d in days if (s, d, "02:00-08:00") in assignment]
    if night_vars:
        model.Add(sum(night_vars) <= 1)

# =============================================================================
# 7. Fairness constraints.
#
# For each student, compute the total number of shifts assigned.
# Then define global variables for the maximum and minimum shifts any student gets.
# =============================================================================
max_possible_shifts = len(days) * len(shifts)
total_shifts = {}
for s in students:
    rel_vars = [assignment[(s, d, sh)] for d in days for sh in shifts if (s, d, sh) in assignment]
    total_shifts[s] = model.NewIntVar(0, max_possible_shifts, f"total_shifts_{s}")
    model.Add(total_shifts[s] == sum(rel_vars))

max_shifts = model.NewIntVar(0, max_possible_shifts, "max_shifts")
min_shifts = model.NewIntVar(0, max_possible_shifts, "min_shifts")
for s in students:
    model.Add(total_shifts[s] <= max_shifts)
    model.Add(total_shifts[s] >= min_shifts)

# =============================================================================
# 8. Define the objective.
#
# We want to (a) minimize the staffing penalties on regular shifts and (b)
# minimize the difference between the busiest and least busy student.
#
# For each regular shift (desired = 3), we add:
#   penalty = 10000 * missing + 1000 * slack
#
# Then we add the fairness term.
# =============================================================================
coverage_penalty_terms = []
for d in days:
    for sh in shifts:
        if sh != "02:00-08:00" and shift_desired[(d, sh)] > 0:
            coverage_penalty_terms.append(10000 * missing[(d, sh)] + 1000 * slack[(d, sh)])

fairness_term = max_shifts - min_shifts
model.Minimize(sum(coverage_penalty_terms) + fairness_term)

# =============================================================================
# 9. Solve the model.
# =============================================================================
solver = cp_model.CpSolver()
status = solver.Solve(model)

if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
    print("Shift Schedule:\n")
    for d in days:
        print(f"=== {d} ===")
        for sh in shifts:
            if shift_desired[(d, sh)] == 0:
                continue  # Skip off shifts.
            assigned_students = []
            for s in students:
                key = (s, d, sh)
                if key in assignment and solver.Value(assignment[key]) == 1:
                    marker = " (D)" if student_can_drive[s] else ""
                    assigned_students.append(s + marker)
            if sh != "02:00-08:00" and shift_desired[(d, sh)] > 0 and (d, sh) in assigned_sum:
                num_assigned = solver.Value(assigned_sum[(d, sh)])
                slack_val = solver.Value(slack[(d, sh)])
                missing_val = solver.Value(missing[(d, sh)])
                print(f"  Shift {sh}: assigned {num_assigned} (ideal 3); missing penalty {missing_val}, slack {slack_val}.")
                print("      ", ", ".join(assigned_students))
            else:
                print(f"  Shift {sh}: {', '.join(assigned_students)}")
        print()
    print("Fairness Summary:")
    for s in students:
        print(f"  {s}: {solver.Value(total_shifts[s])} shifts")
    print(f"  Maximum shifts assigned: {solver.Value(max_shifts)}")
    print(f"  Minimum shifts assigned: {solver.Value(min_shifts)}")
    print("\nObjective value:", solver.ObjectiveValue())
else:
    print("No feasible solution was found.")

# =============================================================================
# 10. Checker: Verify no scheduling conflicts.
#
# This function checks that every scheduled shift is among the student's available
# times (which now, by design, always includes the evening shifts).
# =============================================================================
def check_schedule_conflicts(solver, assignment, students, days, shifts, student_availability):
    conflicts = []
    for s in students:
        for d in days:
            for sh in shifts:
                key = (s, d, sh)
                if key in assignment and solver.Value(assignment[key]) == 1:
                    if d not in student_availability[s] or sh not in student_availability[s][d]:
                        conflicts.append((s, d, sh))
    if conflicts:
        print("\nScheduling conflicts found:")
        for (s, d, sh) in conflicts:
            print(f"  Student {s} is scheduled for shift {sh} on {d} but is not available (conflict with class).")
    else:
        print("\nNo scheduling conflicts found.")

check_schedule_conflicts(solver, assignment, students, days, shifts, student_availability)
