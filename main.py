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

# Replace strict shift constraints with soft constraints using slack variables.
slack_avail = {}
slack_drivers = {}
for day, shifts in shifts_per_day.items():
    for shift in shifts:
        available_students = [s for s in students if shift in s["availability"].get(day, [])]
        slack_avail[(day, shift)] = model.NewIntVar(0, shift_requirements[shift]["needed"], f"slack_avail_{day}_{shift}")
        slack_drivers[(day, shift)] = model.NewIntVar(0, shift_requirements[shift]["drivers"], f"slack_driver_{day}_{shift}")
        model.Add(
            sum(schedule[(s["name"], day, shift)] for s in available_students) + slack_avail[(day, shift)]
            >= shift_requirements[shift]["needed"]
        )
        model.Add(
            sum(schedule[(s["name"], day, shift)] for s in available_students if s["can_drive"]) + slack_drivers[(day, shift)]
            >= shift_requirements[shift]["drivers"]
        )

# Fairness: calculate each student's total assigned shifts.
# Compute an upper bound: maximum possible shifts per student = #days * max shifts per day.
upper_bound = len(shifts_per_day) * max(len(shifts) for shifts in shifts_per_day.values())
student_load = {}
for s in students:
    student_load[s["name"]] = model.NewIntVar(0, upper_bound, f"load_{s['name']}")
    model.Add(
        student_load[s["name"]] ==
        sum(schedule[(s["name"], day, shift)] for day in shifts_per_day for shift in shifts_per_day[day])
    )

# Define max and min load variables.
max_load = model.NewIntVar(0, upper_bound, "max_load")
min_load = model.NewIntVar(0, upper_bound, "min_load")
for s in students:
    model.Add(student_load[s["name"]] <= max_load)
    model.Add(student_load[s["name"]] >= min_load)

# Prevent any student from working consecutive night shifts ("2-8 (Night)")
days = list(shifts_per_day.keys())
for i in range(len(days) - 1):
    for s in students:
        # At least one of the two consecutive night shift assignments must be off.
        model.AddBoolOr([
            schedule[(s["name"], days[i], "2-8 (Night)")].Not(),
            schedule[(s["name"], days[i+1], "2-8 (Night)")].Not()
        ])

# Set the objective to balance fairness and penalize unmet shift requirements.
penalty_weight = 10  # Adjust weight as needed.
model.Minimize(
    (max_load - min_load) +
    penalty_weight * (sum(slack_avail.values()) + sum(slack_drivers.values()))
)

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

# Save DataFrame to an Excel file
output_file_path = "schedule_output.xlsx"
df.to_excel(output_file_path, index=False)

print(f"Schedule saved to {output_file_path}")
