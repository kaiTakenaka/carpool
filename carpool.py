import pandas as pd
import pgeocode
from geopy.distance import geodesic

def create_driver_anchor_pools(csv_file, max_capacity=4):
    # Load CSV
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()  # clean up any whitespace

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
    df = df.dropna(subset=['Latitude', 'Longitude'])  # drop if coords missing

    # Split drivers vs passengers
    driver_col = "Do you have access to a car and would drive for road trip? (Drivers get bed priorities and won't be included for fuel split)"
    drivers = df[df[driver_col].str.lower() == "yes"].copy()
    passengers = df[df[driver_col].str.lower() != "yes"].copy()

    if len(drivers) == 0:
        print("❌ No drivers available!")
        return

    # Track remaining capacity per driver
    driver_capacity = {d['Full Name']: max_capacity for _, d in drivers.iterrows()}

    assignments = []
    unassigned = []

    # Assign each passenger to the nearest driver with capacity
    for _, p in passengers.iterrows():
        p_loc = (p['Latitude'], p['Longitude'])
        nearest_driver = None
        nearest_dist = float("inf")

        for _, d in drivers.iterrows():
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
                "Distance (km)": round(nearest_dist, 1)
            })
            driver_capacity[nearest_driver] -= 1
        else:
            unassigned.append(p['Full Name'])

    # Group passengers by driver
    grouped = {}
    for a in assignments:
        driver = a["Assigned Driver"]
        if driver not in grouped:
            grouped[driver] = []
        grouped[driver].append(a["Passenger"])

    grouped_rows = []
    for driver, passenger_list in grouped.items():
        grouped_rows.append({
            "Driver": driver,
            "Passengers": ", ".join(passenger_list),
            "Passenger Count": len(passenger_list)
        })

    grouped_df = pd.DataFrame(grouped_rows)
    grouped_df.to_csv("carpool_groups.csv", index=False)

    print("\n✅ Carpool groups saved to carpool_groups.csv")
    print(grouped_df)

    if unassigned:
        print("\n⚠️ Unassigned passengers (no available driver seats):")
        for name in unassigned:
            print(" -", name)

    return grouped_df


# Run program
if __name__ == "__main__":
    create_driver_anchor_pools("form_responses.csv", max_capacity=4)
