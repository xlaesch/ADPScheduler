import csv
import ast
from ortools.sat.python import cp_model

# =============================================================================
students = []
student_can_drive = {}        # Map: student name - boolean
student_availability = {}     # Map: student name - { day: set(shifts) }

all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

csv_file = 'processed_student_availability.csv'
with open(csv_file, newline='') as f:
    reader = csv.DictReader(f)
    for row in reader:
        name = row['name'].strip()
        students.append(name)
        student_can_drive[name] = row['can_drive'].strip().lower() == 'true'
        try:
            avail_dict = ast.literal_eval(row['availability'])
        except Exception as e:
            print(f"Error parsing availability for {name}: {e}")
            avail_dict = {}
        avail_clean = {}
        for day, shift_list in avail_dict.items():
            avail_clean[day] = set(shift_list)
            avail_clean[day].update(["20:00-23:00", "23:00-2:00"])
        # Also, for any day missing from the CSV, assume the student is available for the evening shifts
        for day in all_days:
            if day not in avail_clean:
                avail_clean[day] = {"20:00-23:00", "23:00-2:00"}
        student_availability[name] = avail_clean

# Debug: Print student availability
for student, availability in student_availability.items():
    print(f"Availability for {student}: {availability}")

# =============================================================================
days = all_days

shifts = [
    "02:00-08:00",  
    "08:00-11:00",
    "11:00-14:00",
    "14:00-17:00",
    "17:00-20:00",  # Off on Tue, Thu, and Sun
    "20:00-23:00",
    "23:00-2:00"
]

shift_desired = {}
shift_driver_desired = {}  
for d in days:
    shift_desired[(d, "02:00-08:00")] = 2
    shift_driver_desired[(d, "02:00-08:00")] = 1

    for sh in ["08:00-11:00", "11:00-14:00", "14:00-17:00", "20:00-23:00", "23:00-2:00"]:
        shift_desired[(d, sh)] = 3
        shift_driver_desired[(d, sh)] = 2

    if d in ["Tuesday", "Thursday", "Sunday"]:
        shift_desired[(d, "17:00-20:00")] = 0
        shift_driver_desired[(d, "17:00-20:00")] = 0
    else:
        shift_desired[(d, "17:00-20:00")] = 3
        shift_driver_desired[(d, "17:00-20:00")] = 2

    # Remove the shift of 20:00-23:00 and 23:00-2:00 on Thursday, Friday, Saturday
    if d in ["Thursday", "Friday", "Saturday"]:
        shift_desired[(d, "20:00-23:00")] = 0
        shift_driver_desired[(d, "20:00-23:00")] = 0
        shift_desired[(d, "23:00-2:00")] = 0
        shift_driver_desired[(d, "23:00-2:00")] = 0

# Debug: Print desired shifts
for (day, shift), desired in shift_desired.items():
    print(f"Desired for {day} {shift}: {desired} students, {shift_driver_desired[(day, shift)]} drivers")

# =============================================================================
model = cp_model.CpModel()

assignment = {}  # (s, d, sh) -> BoolVar
for s in students:
    for d in days:
        for sh in shifts:
            if sh in ["20:00-23:00", "23:00-2:00"]:
                available = True
            else:
                available = (d in student_availability[s] and sh in student_availability[s][d])
            if available:
                assignment[(s, d, sh)] = model.NewBoolVar(f"{s}_{d}_{sh}")

# =============================================================================
assigned_sum = {}  # (d,sh) -> IntVar (number of workers assigned)
slack = {}       # (d,sh) -> IntVar: 3 - assigned_sum
missing = {}     # (d,sh) -> IntVar: max(0, 2 - assigned_sum)

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

# Debug: Print constraints
print("Constraints added to the model:")
for d in days:
    for sh in shifts:
        if (d, sh) in assigned_sum:
            print(f"  {d} {sh}: assigned_sum <= 3, slack = 3 - assigned_sum, missing = max(0, 2 - assigned_sum)")

# =============================================================================
for d in days:
    for sh in shifts:
        driver_vars = [assignment[(s, d, sh)] for s in students 
                       if (s, d, sh) in assignment and student_can_drive[s]]
        if sh == "02:00-08:00":
            model.Add(sum(driver_vars) >= 1)
        elif shift_desired[(d, sh)] == 0:
            pass  # Off shift so no workers assigned
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
for s in students:
    night_vars = [assignment[(s, d, "02:00-08:00")] for d in days if (s, d, "02:00-08:00") in assignment]
    if night_vars:
        model.Add(sum(night_vars) <= 1)

# Add this constraint so each student has at most one shift per day
for s in students:
    for d in days:
        day_vars = [assignment[(s, d, sh)] for sh in shifts if (s, d, sh) in assignment]
        model.Add(sum(day_vars) <= 1)

# =============================================================================
max_possible_shifts = len(days) * len(shifts)
total_shifts = {}
for s in students:
    weighted_assignments = []
    for d in days:
        for sh in shifts:
            if (s, d, sh) in assignment:
                if sh == "02:00-08:00":
                    weighted_assignments.append(2 * assignment[(s, d, sh)])
                else:
                    weighted_assignments.append(assignment[(s, d, sh)])
    total_shifts[s] = model.NewIntVar(0, max_possible_shifts, f"total_shifts_{s}")
    model.Add(total_shifts[s] == sum(weighted_assignments))

max_shifts = model.NewIntVar(0, max_possible_shifts, "max_shifts")
min_shifts = model.NewIntVar(0, max_possible_shifts, "min_shifts")
for s in students:
    model.Add(total_shifts[s] <= max_shifts)
    model.Add(total_shifts[s] >= min_shifts)

# =============================================================================
coverage_penalty_terms = []
for d in days:
    for sh in shifts:
        if sh != "02:00-08:00" and shift_desired[(d, sh)] > 0:
            coverage_penalty_terms.append(10000 * missing[(d, sh)] + 1000 * slack[(d, sh)])

fairness_term = max_shifts - min_shifts
model.Minimize(sum(coverage_penalty_terms) + fairness_term)

# =============================================================================
solver = cp_model.CpSolver()
status = solver.Solve(model)

if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
    print("Shift Schedule:\n")
    for d in days:
        print(f"=== {d} ===")
        for sh in shifts:
            if shift_desired[(d, sh)] == 0:
                continue  # Skip off shifts
            
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
                print(f"  Shift {sh}: {', '.join(assigned_students)}")
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
    # Debug: Print variable values
    for s in students:
        for d in days:
            for sh in shifts:
                key = (s, d, sh)
                if key in assignment:
                    print(f"Assignment {key}: {solver.Value(assignment[key])}")

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
