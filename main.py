from ortools.sat.python import cp_model
import pandas as pd
import random

# Load processed student availability data from CSV
csv_file_path = "processed_student_availability.csv"
students_df = pd.read_csv(csv_file_path)

def convert_slot(slot):
    mapping = {
        "8-11": "08:00-11:00",
        "11-2": "11:00-14:00",
        "2-5": "14:00-17:00",
        "5-8": "17:00-20:00",
        "2-8 (Night)": "02:00-08:00 (Night)"
    }
    return mapping.get(slot, slot)

# Convert DataFrame to structured dictionary with converted time formats
students = []
for _, row in students_df.iterrows():
    availability = eval(row["availability"])  # Convert string representation of dict back to dict
    converted_availability = {}
    for day, slots in availability.items():
        converted_availability[day] = [convert_slot(slot) for slot in slots]
    students.append({
        "name": row["name"],
        "can_drive": row["can_drive"],
        "availability": converted_availability
    })

# Define shifts per day using 24h time
shifts_per_day = {
    "Monday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Tuesday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Wednesday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Thursday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Friday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Saturday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
    "Sunday": ["08:00-11:00", "11:00-14:00", "14:00-17:00", "17:00-20:00", "20:00-23:00", "23:00-02:00", "02:00-08:00 (Night)"],
}

# Define updated shift requirements per shift label.
shift_requirements = {
    "08:00-11:00": {"needed": 3, "drivers": 2},
    "11:00-14:00": {"needed": 3, "drivers": 2},
    "14:00-17:00": {"needed": 3, "drivers": 2},
    "17:00-20:00": {"needed": 3, "drivers": 2},
    "20:00-23:00": {"needed": 3, "drivers": 2},
    "23:00-02:00": {"needed": 3, "drivers": 2},
    "02:00-08:00 (Night)": {"needed": 2, "drivers": 1},  # Rotating night shift requirement
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

# For each student, day, and shift instance, force schedule to 0 if the student is not available.
for student in students:
    for day, shift_list in shifts_per_day.items():
        available_shifts = student["availability"].get(day, [])
        for idx, shift in enumerate(shift_list):
            if shift not in available_shifts:
                model.Add(schedule[(student["name"], day, idx, shift)] == 0)

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

# Prevent any student from working consecutive night shifts ("02:00-08:00 (Night)")
# For each student and consecutive days, the sum of assignments over all night shift instances is <= 1.
days = list(shifts_per_day.keys())
for i in range(len(days) - 1):
    day1 = days[i]
    day2 = days[i+1]
    # Get indices (could be more than one occurrence of night shift per day)
    night_indices_day1 = [idx for idx, shift in enumerate(shifts_per_day[day1]) if shift == "02:00-08:00 (Night)"]
    night_indices_day2 = [idx for idx, shift in enumerate(shifts_per_day[day2]) if shift == "02:00-08:00 (Night)"]
    for s in students:
        assignments_day1 = [schedule[(s["name"], day1, idx, "02:00-08:00 (Night)")] for idx in night_indices_day1]
        assignments_day2 = [schedule[(s["name"], day2, idx, "02:00-08:00 (Night)")] for idx in night_indices_day2]
        model.Add(sum(assignments_day1) + sum(assignments_day2) <= 1)

# NEW: Add maximum staffing constraints for each shift instance.
for day, shift_list in shifts_per_day.items():
    for idx, shift in enumerate(shift_list):
        cap = 2 if shift == "02:00-08:00 (Night)" else 3
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

# New: Check for scheduling conflicts
import pandas as pd

conflicts = []

# Load students availability from CSV into a lookup dictionary.
students_avail_df = pd.read_csv("processed_student_availability.csv")
availability_lookup = {}
for _, row in students_avail_df.iterrows():
    # Convert the string representation back to a dictionary.
    availability_lookup[row["name"]] = eval(row["availability"])

# Load the generated schedule from Excel.
schedule_df = pd.read_excel("schedule_output.xlsx")

# Check for class conflicts (student assigned when not available)
for _, row in schedule_df.iterrows():
    day = row["Day"]
    shift = row["Shift"]
    assigned = row["Assigned"]
    if pd.isna(assigned) or assigned.strip() == "":
        continue
    # Split the assigned students from the generated schedule.
    assigned_students = [s.strip() for s in assigned.split(",") if s.strip()]
    for student in assigned_students:
        if shift not in availability_lookup.get(student, {}).get(day, []):
            conflicts.append(f"Conflict: {student} assigned to shift {shift} on {day} but not available (might be in class).")

# Check that no student is assigned more than one shift in the same day.
# We'll aggregate assignments per day.
for day, group in schedule_df.groupby("Day"):
    daily_assignments = {}
    for _, row in group.iterrows():
        assigned = row["Assigned"]
        if pd.isna(assigned) or assigned.strip() == "":
            continue
        assigned_students = [s.strip() for s in assigned.split(",") if s.strip()]
        for student in assigned_students:
            daily_assignments[student] = daily_assignments.get(student, 0) + 1
            if daily_assignments[student] > 1:
                conflicts.append(f"Conflict: {student} has more than one shift on {day}.")

if conflicts:
    print("\nScheduling Conflicts Detected:")
    for conflict in conflicts:
        print(conflict)
else:
    print("\nNo scheduling conflicts detected.")

