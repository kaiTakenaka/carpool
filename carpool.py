import pandas as pd
import pgeocode
from geopy.distance import geodesic

def create_driver_anchor_pools(csv_file, max_capacity=4):
    # Load CSV
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()  # clean whitespace

    # Extract postcode
    df['Postcode'] = df["What's your suburb and postcode?"].astype(str).str.extract(r'(\d{4})')

    # Convert postcode to lat/long
    nomi = pgeocode.Nominatim('au')
    def get_lat_lon(postcode, nomi_obj):
        if pd.notnull(postcode):
            pc_info = nomi_obj.query_postal_code(str(postcode))
            if pc_info is not None:
                return pc_info.latitude, pc_info.longitude
        return None, None

    df[['Latitude', 'Longitude']] = df['Postcode'].apply(lambda x: get_lat_lon(x, nomi)).apply(pd.Series)
    df = df.dropna(subset=['Latitude', 'Longitude'])

    # Define driver column and departure time column
    driver_col = "Do you have access to a car and would drive for road trip? (Drivers get bed priorities and won't be included for fuel split)"
    # Dynamically find the correct 'time_col'
    found_time_col = None
    expected_time_col_base = "When can you depart for road trip".lower().strip()
    
    for col in df.columns:
        if col.lower().strip() == expected_time_col_base:
            found_time_col = col
            break
        # Also check for common variations, e.g., with a question mark
        if col.lower().strip() == expected_time_col_base + "?":
            found_time_col = col
            break

    if found_time_col is None:
        print(f"Error: Could not find a column similar to '{expected_time_col_base}' in the CSV. Available columns: {df.columns.tolist()}")
        return # Exit or raise an error as appropriate
    
    time_col = found_time_col

    # Categorise on time vs late
    df['Departure Category'] = df[time_col].apply(lambda x: "On time" if str(x).strip().lower() == "anytime friday" else "Late")

    # Split drivers and passengers by category
    drivers = df[df[driver_col].str.lower() == "yes"].copy()
    passengers = df[df[driver_col].str.lower() != "yes"].copy()

    if len(drivers) == 0:
        print("❌ No drivers available!")
        return

    # Track remaining capacity per driver
    driver_capacity = {d['Full Name']: max_capacity for _, d in drivers.iterrows()}

    assignments = []
    unassigned = []

    # Assign passengers to nearest compatible driver
    for _, p in passengers.iterrows():
        p_loc = (p['Latitude'], p['Longitude'])
        p_cat = p['Departure Category']

        nearest_driver = None
        nearest_dist = float("inf")

        for _, d in drivers.iterrows():
            d_cat = d['Departure Category']
            if d_cat != p_cat:
                continue  # skip incompatible time categories

            if driver_capacity[d['Full Name']] <= 0:
                continue  # driver full

            d_loc = (d['Latitude'], d['Longitude'])
            dist = geodesic(p_loc, d_loc).km
            if dist < nearest_dist:
                nearest_driver = d['Full Name']
                nearest_dist = dist

        if nearest_driver:
            assignments.append({
                "Passenger": p['Full Name'],
                "Assigned Driver": nearest_driver,
                "Category": p_cat,
                "Distance (km)": round(nearest_dist, 1)
            })
            driver_capacity[nearest_driver] -= 1
        else:
            unassigned.append((p['Full Name'], p_cat))

    # Group passengers by driver (include empty drivers as "None")
    grouped_rows = []
    for _, d in drivers.iterrows():
        driver_name = d['Full Name']
        driver_cat = d['Departure Category']
        passenger_list = [a["Passenger"] for a in assignments if a["Assigned Driver"] == driver_name]

        if passenger_list:
            passengers_str = ", ".join(passenger_list)
        else:
            passengers_str = "None"

        grouped_rows.append({
            "Driver": driver_name,
            "Departure Category": driver_cat,
            "Passengers": passengers_str,
            "Passenger Count": 0 if passengers_str == "None" else len(passenger_list)
        })

    grouped_df = pd.DataFrame(grouped_rows)
    grouped_df.to_csv("carpool_groups_with_time.csv", index=False)

    print("\n✅ Carpool groups saved to carpool_groups_with_time.csv")
    print(grouped_df)

    if unassigned:
        print("\n⚠️ Unassigned passengers (no compatible driver):")
        for name, cat in unassigned:
            print(f" - {name} ({cat})")

    return grouped_df


# Run program
if __name__ == "__main__":
    create_driver_anchor_pools("form_responses.csv", max_capacity=4)
