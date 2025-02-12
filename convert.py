
import csv
import re
import json
from datetime import datetime

def parse_time_ranges(class_times):
    """Converts class times into available time slots based on given shifts."""
    all_shifts = [
        ("02:00-08:00", datetime.strptime("02:00", "%H:%M"), datetime.strptime("08:00", "%H:%M")),
        ("08:00-11:00", datetime.strptime("08:00", "%H:%M"), datetime.strptime("11:00", "%H:%M")),
        ("11:00-14:00", datetime.strptime("11:00", "%H:%M"), datetime.strptime("14:00", "%H:%M")),
        ("14:00-17:00", datetime.strptime("14:00", "%H:%M"), datetime.strptime("17:00", "%H:%M")),
        ("17:00-20:00", datetime.strptime("17:00", "%H:%M"), datetime.strptime("20:00", "%H:%M")),
        ("20:00-23:00", datetime.strptime("20:00", "%H:%M"), datetime.strptime("23:00", "%H:%M")),
    ]
    
    class_periods = []
    if class_times.strip():
        class_periods = re.findall(r"\d{2}:\d{2}–\d{2}:\d{2}", class_times)
    
    occupied_shifts = set()
    for period in class_periods:
        start, end = period.split("–")
        start_time = datetime.strptime(start, "%H:%M")
        end_time = datetime.strptime(end, "%H:%M")
        
        for shift, shift_start, shift_end in all_shifts:
            if not (end_time <= shift_start or start_time >= shift_end):
                occupied_shifts.add(shift)
    
    available_shifts = [shift for shift, _, _ in all_shifts if shift not in occupied_shifts]
    return available_shifts

def process_schedule(file_path, output_file):
    """Processes the student schedule file and outputs formatted availability."""
    all_shifts = [
        ("02:00-08:00", datetime.strptime("02:00", "%H:%M"), datetime.strptime("08:00", "%H:%M")),
        ("08:00-11:00", datetime.strptime("08:00", "%H:%M"), datetime.strptime("11:00", "%H:%M")),
        ("11:00-14:00", datetime.strptime("11:00", "%H:%M"), datetime.strptime("14:00", "%H:%M")),
        ("14:00-17:00", datetime.strptime("14:00", "%H:%M"), datetime.strptime("17:00", "%H:%M")),
        ("17:00-20:00", datetime.strptime("17:00", "%H:%M"), datetime.strptime("20:00", "%H:%M")),
        ("20:00-23:00", datetime.strptime("20:00", "%H:%M"), datetime.strptime("23:00", "%H:%M")),
    ]
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        headers = next(reader)
        days = headers[1:-1]
        
        results = []
        
        for row in reader:
            name = row[0].replace(" 🚗", "")
            can_drive = "yes" in row[-1].lower()
            
            availability = {}
            for i, day in enumerate(days):
                availability[day] = parse_time_ranges(row[i + 1])
            
            # Assume full availability on weekends
            availability["Saturday"] = [shift[0] for shift in all_shifts]
            availability["Sunday"] = [shift[0] for shift in all_shifts]
            
            results.append({
                "name": name,
                "can_drive": can_drive,
                "availability": json.dumps(availability, ensure_ascii=False)
            })
    
    # Writing the formatted data to a new CSV file
    with open(output_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["name", "can_drive", "availability"])
        for r in results:
            writer.writerow([r["name"], r["can_drive"], r["availability"]])

# Example Usage:
process_schedule("data.txt", "formatted_availability.csv")
