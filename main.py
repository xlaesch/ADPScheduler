from ortools.sat.python import cp_model
import pandas as pd
import random

# Load processed student availability data from CSV
csv_file_path = "processed_student_availability.csv"
students_df = pd.read_csv(csv_file_path)

# Convert DataFrame to structured dictionary
students = []
for _, row in students_df.iterrows():
    availability = eval(row["availability"])  # Convert string representation of dict back to dict
    students.append({"name": row["name"], "can_drive": row["can_drive"], "availability": availability})

# Define shifts per day (excluding unnecessary shifts)
shifts_per_day = {
    "Monday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Tuesday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"],
    "Wednesday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Thursday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"],
    "Friday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Saturday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Sunday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"]
}

# Define shift requirements
shift_requirements = {
    "8-11": {"needed": 3, "drivers": 2},
    "11-2": {"needed": 2, "drivers": 1},
    "2-5": {"needed": 3, "drivers": 2},
    "5-8": {"needed": 3, "drivers": 2},
    "8-11": {"needed": 3, "drivers": 2},
    "11-2": {"needed": 2, "drivers": 1},
    "2-8 (Night)": {"needed": 2, "drivers": 1},  # Rotating night shift
}

# Night shift rotation: Ensure different workers each night
night_shift_schedule = []
all_students = [s["name"] for s in students]
for i in range(7):  # 7 days
    night_shift_schedule.append(all_students[i * 2 % len(all_students)])  # Rotates through students
    night_shift_schedule.append(all_students[(i * 2 + 1) % len(all_students)])

# Initialize model
model = cp_model.CpModel()

# Decision variables
schedule = {}
for student in students:
    for day, shifts in shifts_per_day.items():
        for shift in shifts:
            schedule[(student["name"], day, shift)] = model.NewBoolVar(f"{student['name']}_{day}_{shift}")

# Shift constraints: Ensure best effort to fill shifts
for day, shifts in shifts_per_day.items():
    for shift in shifts:
        available_students = [s for s in students if shift in s["availability"].get(day, [])]
        min_needed = min(len(available_students), shift_requirements[shift]["needed"])
        min_drivers = min(sum(s["can_drive"] for s in available_students), shift_requirements[shift]["drivers"])
        
        model.Add(
            sum(schedule[(s["name"], day, shift)] for s in available_students) >= min_needed
        )
        model.Add(
            sum(schedule[(s["name"], day, shift)] for s in available_students if s["can_drive"]) >= min_drivers
        )

# Rotate night shift workers (no two consecutive nights)
for i, day in enumerate(shifts_per_day.keys()):
    model.Add(schedule[(night_shift_schedule[i], day, "2-8 (Night)")] == 1)
    model.Add(schedule[(night_shift_schedule[i + 1], day, "2-8 (Night)")] == 1)

# Solve model
solver = cp_model.CpSolver()
status = solver.Solve(model)

# Output schedule
schedule_result = []
for day, shifts in shifts_per_day.items():
    for shift in shifts:
        assigned_students = [
            s["name"] for s in students if solver.Value(schedule[(s["name"], day, shift)]) == 1
        ]
        schedule_result.append({"Day": day, "Shift": shift, "Assigned": ", ".join(assigned_students)})

# Convert to DataFrame for viewing
df = pd.DataFrame(schedule_result)
print(df)
