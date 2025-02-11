import pandas as pd
import ast
import os

def convert_to_24_hour(time_slot):
    mapping = {
        "8-11": "08:00-11:00",
        "11-2": "11:00-14:00",
        "2-5": "14:00-17:00",
        "5-8": "17:00-20:00",
        "8-11": "20:00-23:00",
        "11-2": "23:00-02:00",
        "2-8 (Night)": "02:00-08:00 (Night)"
    }
    return mapping.get(time_slot, time_slot)

def process_csv(input_path, output_path):
    # Read CSV
    df = pd.read_csv(input_path)
    
    # Process availability column
    df['availability'] = df['availability'].apply(lambda x: ast.literal_eval(x))
    
    # Convert times
    for i, row in df.iterrows():
        converted_availability = {day: [convert_to_24_hour(slot) for slot in slots] for day, slots in row['availability'].items()}
        df.at[i, 'availability'] = str(converted_availability)  # Convert back to string for CSV storage
    
    # Save to new CSV
    df.to_csv(output_path, index=False)
    print(f"Converted CSV saved to: {output_path}")

if __name__ == "__main__":
    input_path = input("Enter the path to the input CSV file: ")
    output_path = input("Enter the path to save the output CSV file: ")
    
    if not os.path.exists(input_path):
        print("Error: Input file does not exist.")
    else:
        process_csv(input_path, output_path)
