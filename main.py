from ortools.sat.python import cp_model
import pandas as pd
import random

# Define students
students = [
    {"name": "Alice", "can_drive": True, "max_shifts": 3, "availability": ["8-11", "11-2", "5-8"]},
    {"name": "Bob", "can_drive": False, "max_shifts": 3, "availability": ["8-11", "2-5", "8-11"]},
    {"name": "Charlie", "can_drive": True, "max_shifts": 3, "availability": ["2-5", "5-8", "11-2"]},
    # Add all 24 students here
]

# Define shifts
shifts = [
    "8-11", "11-2", "2-5", "5-8", "8-11", "11-2", "2-8 (Night Shift)"
]
shift_requirements = {
    "8-11": {"needed": 3, "drivers": 2},
    "11-2": {"needed": 3, "drivers": 2},
    "2-5": {"needed": 3, "drivers": 2},
    "5-8": {"needed": 3, "drivers": 2},
    "8-11": {"needed": 3, "drivers": 2},
    "11-2": {"needed": 3, "drivers": 2},
    "2-8 (Night Shift)": {"needed": 2, "drivers": 1},  # Fixed team all week
}

# Assign fixed night shift workers
night_shift_workers = random.sample([s for s in students if "2-8 (Night Shift)" in s["availability"]], 2)

# Initialize Model
model = cp_model.CpModel()

# Create decision variables
schedule = {}
for student in students:
    for shift in shifts:
        schedule[(student["name"], shift)] = model.NewBoolVar(f"{student['name']}_{shift}")

# Shift constraints: Each shift must have the required number of people
for shift, reqs in shift_requirements.items():
    model.Add(sum(schedule[(s["name"], shift)] for s in students if shift in s["availability"]) == reqs["needed"])

    # Ensure drivers requirement
    model.Add(sum(schedule[(s["name"], shift)] for s in students if s["can_drive"] and shift in s["availability"]) >= reqs["drivers"])

# Maximum shift constraints
for student in students:
    model.Add(sum(schedule[(student["name"], shift)] for shift in shifts if shift in student["availability"]) <= student["max_shifts"])

# Solve model
solver = cp_model.CpSolver()
status = solver.Solve(model)

# Print schedule
if status == cp_model.FEASIBLE or status == cp_model.OPTIMAL:
    schedule_result = []
    for shift in shifts:
        assigned_students = [
            s["name"] for s in students if solver.Value(schedule[(s["name"], shift)]) == 1
        ]
        schedule_result.append({"Shift": shift, "Assigned": ", ".join(assigned_students)})
    
    # Convert to dataframe
    df = pd.DataFrame(schedule_result)
    import ace_tools as tools
    tools.display_dataframe_to_user(name="Generated Shift Schedule", dataframe=df)

else:
    print("No feasible schedule found.")
