import csv

def get_available_people(day, time_slot):
    available_people = []
    with open("/Users/alexsch/ADPScheduler/processed_student_availability.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data = row["availability"]
            day_marker = f'"{day}": ['
            start = data.find(day_marker)
            if start == -1:
                continue
            bracket_start = data.find("[", start)
            bracket_end = data.find("]", bracket_start)
            if bracket_start == -1 or bracket_end == -1:
                continue
            segment = data[bracket_start+1:bracket_end].strip()
            times = [t.strip().strip('"') for t in segment.split(",")]
            if time_slot in times:
                available_people.append(row["name"])
    return available_people

# Example usage
if __name__ == "__main__":
    print(get_available_people("Thursday", "11:00-14:00"))
