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

# Define shifts per day (each entry in the list is a distinct shift instance)
shifts_per_day = {
    "Monday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Tuesday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"],
    "Wednesday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Thursday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"],
    "Friday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Saturday": ["8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night)"],
    "Sunday": ["8-11", "11-2", "2-5", "8-11", "11-2", "2-8 (Night)"]
}

# Define shift requirements per shift label (each instance inherits these).
shift_requirements = {
    "8-11": {"needed": 3, "drivers": 2},
    "11-2": {"needed": 2, "drivers": 1},
    "2-5": {"needed": 3, "drivers": 2},
    "5-8": {"needed": 3, "drivers": 2},
    "2-8 (Night)": {"needed": 2, "drivers": 1},  # Rotating night shift requirement
}

# Initialize model
model = cp_model.CpModel()

# Decision variables: now each decision variable is keyed by (student, day, shift_index, shift_label)
schedule = {}
for student in students:
    for day, shift_list in shifts_per_day.items():
        for idx, shift in enumerate(shift_list):
            schedule[(student["name"], day, idx, shift)] = model.NewBoolVar(
                f"{student['name']}_{day}_{shift}_{idx}"
            )

# Slack variables for soft constraints on meeting required available and driver counts.
slack_avail = {}
slack_drivers = {}
for day, shift_list in shifts_per_day.items():
    for idx, shift in enumerate(shift_list):
        # Students available to work this shift instance on that day:
        available_students = [s for s in students if shift in s["availability"].get(day, [])]
        slack_avail[(day, idx, shift)] = model.NewIntVar(0, shift_requirements[shift]["needed"],
                                                           f"slack_avail_{day}_{shift}_{idx}")
        slack_drivers[(day, idx, shift)] = model.NewIntVar(0, shift_requirements[shift]["drivers"],
                                                             f"slack_driver_{day}_{shift}_{idx}")
        model.Add(
            sum(schedule[(s["name"], day, idx, shift)] for s in available_students) + slack_avail[(day, idx, shift)]
            >= shift_requirements[shift]["needed"]
        )
        model.Add(
            sum(schedule[(s["name"], day, idx, shift)] for s in available_students if s["can_drive"])
            + slack_drivers[(day, idx, shift)]
            >= shift_requirements[shift]["drivers"]
        )

# Fairness: calculate each student's total assigned shifts across all days and shift instances.
upper_bound = len(shifts_per_day) * max(len(shift_list) for shift_list in shifts_per_day.values())
student_load = {}
for s in students:
    student_load[s["name"]] = model.NewIntVar(0, upper_bound, f"load_{s['name']}")
    model.Add(
        student_load[s["name"]] ==
        sum(schedule[(s["name"], day, idx, shift)]
            for day, shift_list in shifts_per_day.items()
            for idx, shift in enumerate(shift_list))
    )

max_load = model.NewIntVar(0, upper_bound, "max_load")
min_load = model.NewIntVar(0, upper_bound, "min_load")
for s in students:
    model.Add(student_load[s["name"]] <= max_load)
    model.Add(student_load[s["name"]] >= min_load)

# Prevent any student from working consecutive night shifts ("2-8 (Night)")
# For each student and consecutive days, the sum of assignments over all night shift instances is <= 1.
days = list(shifts_per_day.keys())
for i in range(len(days) - 1):
    day1 = days[i]
    day2 = days[i+1]
    # Get indices (could be more than one occurrence of night shift per day)
    night_indices_day1 = [idx for idx, shift in enumerate(shifts_per_day[day1]) if shift == "2-8 (Night)"]
    night_indices_day2 = [idx for idx, shift in enumerate(shifts_per_day[day2]) if shift == "2-8 (Night)"]
    for s in students:
        assignments_day1 = [schedule[(s["name"], day1, idx, "2-8 (Night)")] for idx in night_indices_day1]
        assignments_day2 = [schedule[(s["name"], day2, idx, "2-8 (Night)")] for idx in night_indices_day2]
        model.Add(sum(assignments_day1) + sum(assignments_day2) <= 1)

# NEW: Add maximum staffing constraints for each shift instance.
for day, shift_list in shifts_per_day.items():
    for idx, shift in enumerate(shift_list):
        cap = 2 if shift == "2-8 (Night)" else 3
        model.Add(sum(schedule[(s["name"], day, idx, shift)] for s in students) <= cap)

# Ensure each student gets at most one shift per day.
for s in students:
    for day, shift_list in shifts_per_day.items():
        model.Add(sum(schedule[(s["name"], day, idx, shift)]
                      for idx, shift in enumerate(shift_list)) <= 1)

# Set objective: balance fairness and penalize unmet requirements.
penalty_weight = 10  # Adjust weight as needed.
model.Minimize(
    (max_load - min_load) +
    penalty_weight * (sum(slack_avail.values()) + sum(slack_drivers.values()))
)

# Solve model with a time limit.
solver = cp_model.CpSolver()
solver.parameters.max_time_in_seconds = 60  # 60-second time limit.
solver.parameters.log_search_progress = True
status = solver.Solve(model)

# Output schedule with an additional column for drivers.
schedule_result = []
for day, shift_list in shifts_per_day.items():
    for idx, shift in enumerate(shift_list):
        assigned_students = [
            s["name"] for s in students if solver.Value(schedule[(s["name"], day, idx, shift)]) == 1
        ]
        assigned_drivers = [
            s["name"] for s in students if solver.Value(schedule[(s["name"], day, idx, shift)]) == 1 and s["can_drive"]
        ]
        schedule_result.append({
            "Day": day,
            "Shift": shift,
            "Instance": idx,
            "Assigned": ", ".join(assigned_students),
            "Drivers": ", ".join(assigned_drivers)
        })

# Convert to DataFrame for viewing and save to Excel.
df = pd.DataFrame(schedule_result)
output_file_path = "schedule_output.xlsx"
df.to_excel(output_file_path, index=False)

print(f"Schedule saved to {output_file_path}")
