import math
import hashlib
from io import BytesIO
from pathlib import Path

import streamlit as st
import pandas as pd
import folium
import requests

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
from geopy.exc import (
    GeocoderTimedOut,
    GeocoderUnavailable,
    GeocoderQuotaExceeded
)
from streamlit_folium import st_folium


# ==========================================
# 1. PAGE CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="SolarLand Finder",
    page_icon="☀️",
    layout="wide"
)

DATA_FILE = Path(__file__).parent / "data" / "land_data.csv"


# ==========================================
# 2. LOAD LAND DATA
# ==========================================

@st.cache_data
def load_base_data():
    return pd.read_csv(DATA_FILE)


base_df = load_base_data()

# ==========================================
# 3. SEARCH LOCATION
# ==========================================

@st.cache_resource
def get_geocoder():

    geolocator = Nominatim(
        user_agent="solarland_finder_perkasa_assessment"
    )

    return RateLimiter(
        geolocator.geocode,
        min_delay_seconds=1.2,
        max_retries=1,
        error_wait_seconds=5
    )


@st.cache_data(ttl=86400)
def geocode_location(query):

    clean_query = query.strip()

    if clean_query.upper().startswith("PMU "):
        clean_query = clean_query[4:].strip()

    if "Malaysia" not in clean_query:
        clean_query += ", Malaysia"

    geocode = get_geocoder()

    result = geocode(
        clean_query,
        timeout=15,
        country_codes="my"
    )

    if result:
        return {
            "address": result.address,
            "latitude": float(result.latitude),
            "longitude": float(result.longitude)
        }

    return None

# ==========================================
# 4. CALCULATE STRAIGHT-LINE DISTANCE
# ==========================================

def haversine_km(lat1, lon1, lat2, lon2):

    radius = 6371.0088

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(a))


# ==========================================
# 5. CALCULATE ROAD DISTANCE USING OSRM
# ==========================================

@st.cache_data(ttl=86400)
def get_road_distance_km(start_lat, start_lon, end_lat, end_lon):

    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )

    params = {
        "overview": "false",
        "alternatives": "false",
        "steps": "false"
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        if data.get("code") == "Ok" and data.get("routes"):

            distance_meters = data["routes"][0]["distance"]

            return round(distance_meters / 1000, 2)

        return None

    except requests.RequestException:

        return None


# ==========================================
# 6. GENERATE SIMULATED PARCELS
# ==========================================

def make_demo_parcels(source_df, center_lat, center_lon, location_name):

    seed_text = (
        f"{location_name}|{center_lat:.5f}|{center_lon:.5f}"
    )

    seed = int(
        hashlib.sha256(
            seed_text.encode()
        ).hexdigest()[:8],
        16
    )

    result = source_df.copy()

    parcel_lats = []
    parcel_lons = []
    distances = []

    for i in range(len(result)):

        digest = hashlib.sha256(
            f"{seed}:{i}".encode()
        ).hexdigest()

        bearing = (
            int(digest[:8], 16) / 0xFFFFFFFF
        ) * 2 * math.pi

        distance = (
            0.6
            + (int(digest[8:16], 16) / 0xFFFFFFFF) * 7
        )

        angular = distance / 6371.0088

        lat1 = math.radians(center_lat)
        lon1 = math.radians(center_lon)

        lat2 = math.asin(
            math.sin(lat1) * math.cos(angular)
            + math.cos(lat1)
            * math.sin(angular)
            * math.cos(bearing)
        )

        lon2 = lon1 + math.atan2(
            math.sin(bearing)
            * math.sin(angular)
            * math.cos(lat1),
            math.cos(angular)
            - math.sin(lat1) * math.sin(lat2)
        )

        parcel_lat = math.degrees(lat2)
        parcel_lon = math.degrees(lon2)

        parcel_lats.append(parcel_lat)
        parcel_lons.append(parcel_lon)

        distances.append(
            haversine_km(
                center_lat,
                center_lon,
                parcel_lat,
                parcel_lon
            )
        )

    result["Parcel_Latitude"] = parcel_lats
    result["Parcel_Longitude"] = parcel_lons

    result["Reference_Distance_KM"] = [
        round(x, 2) for x in distances
    ]

    result["Data_Type"] = "Simulation"
    result["Target_Location"] = location_name

    return result


# ==========================================
# LAND CLASSIFICATION
# ==========================================

def evaluate_land(row):

    size = float(row["Land_Size_Acres"])
    distance = float(row["Evaluation_Distance_KM"])

    score = 0
    reasons = []

    # LAND SIZE EVALUATION
    if 80 <= size <= 100:
        score += 2
        reasons.append("Preferred land size")

    elif size > 100:
        reasons.append("Above preferred land size")

    else:
        reasons.append("Below preferred land size")

    # DISTANCE EVALUATION
    if distance <= 5:
        score += 2
        reasons.append("Within 5 km")

    elif distance <= 8:
        score += 1
        reasons.append("Within 8 km")

    else:
        reasons.append("Outside 8 km")

    # FINAL CLASSIFICATION
    if 80 <= size <= 100 and distance <= 5:
        classification = "Good Fit"

    elif distance <= 8 and (
        size >= 80 or distance <= 5
    ):
        classification = "Worth a Look"

    else:
        classification = "No Good"

    reason = " | ".join(reasons)

    return pd.Series([
        classification,
        score,
        reason
    ])

# ==========================================
# 8. SIDEBAR
# ==========================================

st.sidebar.title("☀️ SolarLand Finder")

st.sidebar.caption(
    "Land Evaluation & Monitoring System"
)

st.sidebar.divider()

st.sidebar.subheader("Target Location")

location_method = st.sidebar.radio(
    "Choose Location Method",
    ["Select Existing PMU", "Enter Custom Location"]
)

if location_method == "Select Existing PMU":

    target_input = st.sidebar.selectbox(
        "Select PMU",
        [
            "PMU Bukit Kayu Hitam, Kedah (Example)",
            "Other / Custom Location"
        ]
    )

    if target_input == "Other / Custom Location":

        target_input = st.sidebar.text_input(
            "Enter Target Location",
            placeholder="Example: PMU Alor Setar, Kedah"
        )

    else:

        target_input = "PMU Bukit Kayu Hitam, Kedah"

else:

    target_input = st.sidebar.text_input(
        "Enter Target Location",
        placeholder="Example: Sungai Petani, Kedah"
    )


search_clicked = st.sidebar.button(
    "🔎 Search Location",
    use_container_width=True
)


if search_clicked:

    if not target_input or not target_input.strip():

        st.sidebar.error("Please enter a location.")

    else:

        try:

            with st.spinner("Searching location..."):

                found = geocode_location(target_input)

            if found:

                st.session_state["target_name"] = found["address"]
                st.session_state["target_lat"] = found["latitude"]
                st.session_state["target_lon"] = found["longitude"]

                st.sidebar.success("Location found!")

            else:

                st.sidebar.warning(
                    "Location not found. Please try again."
                )

        except (GeocoderTimedOut, GeocoderUnavailable):

            st.sidebar.error(
                "Location service unavailable. Try again later."
            )

        except Exception as error:

            st.sidebar.error(f"Error: {error}")


# ==========================================
# 9. SEARCH RESULTS
# ==========================================

st.sidebar.divider()

st.sidebar.subheader("Search Results")

if "target_lat" in st.session_state:

    st.sidebar.success(
        st.session_state["target_name"]
    )

    st.sidebar.write(
        f"Latitude: {st.session_state['target_lat']:.6f}"
    )

    st.sidebar.write(
        f"Longitude: {st.session_state['target_lon']:.6f}"
    )

else:

    st.sidebar.info(
        "Search for a target location first."
    )


# ==========================================
# 10. MAIN PAGE
# ==========================================

st.title("☀️ SolarLand Finder")

st.subheader(
    "Solar Farm Land Evaluation System"
)

st.warning(
    "Prototype limitation: Parcel records and coordinates "
    "are simulated. Road distances are demonstration routes "
    "from simulated coordinates, not verified vacant land. "
    "Straight-line fallback is used when routing is unavailable."
)


if "target_lat" not in st.session_state:

    st.info(
        "Please search for a target location using the sidebar."
    )

    st.stop()


# ==========================================
# 11. GET TARGET LOCATION
# ==========================================

lat = st.session_state["target_lat"]
lon = st.session_state["target_lon"]

target_name = st.session_state["target_name"]


# ==========================================
# 12. PREPARE LAND DATA
# ==========================================

parcels = make_demo_parcels(
    base_df,
    lat,
    lon,
    target_name
)


# ==========================================
# 13. CALCULATE ROAD DISTANCE
# ==========================================

with st.spinner("Calculating road distances..."):

    road_distances = []

    for _, parcel in parcels.iterrows():

        distance = get_road_distance_km(
            lat,
            lon,
            parcel["Parcel_Latitude"],
            parcel["Parcel_Longitude"]
        )

        road_distances.append(distance)

    parcels["Road_Distance_KM"] = road_distances


# ==========================================
# 14. SELECT DISTANCE FOR EVALUATION
# ==========================================

parcels["Evaluation_Distance_KM"] = parcels.apply(
    lambda row: (
        row["Road_Distance_KM"]
        if pd.notna(row["Road_Distance_KM"])
        else row["Reference_Distance_KM"]
    ),
    axis=1
)


parcels["Distance_Basis"] = parcels["Road_Distance_KM"].apply(
    lambda x: (
        "OSRM road route"
        if pd.notna(x)
        else "Straight-line fallback"
    )
)


# ==========================================
# 15. CLASSIFICATION
# ==========================================

parcels[
    ["Classification", "Suitability_Score", "Evaluation_Reason"]
] = parcels.apply(
    evaluate_land,
    axis=1
)


# ==========================================
# 16. RANK LAND PARCELS
# ==========================================

ranked = parcels.sort_values(
    [
        "Suitability_Score",
        "Evaluation_Distance_KM"
    ],
    ascending=[False, True]
).reset_index(drop=True)

ranked.insert(
    0,
    "Rank",
    range(1, len(ranked) + 1)
)


# ==========================================
# 17. MAP
# ==========================================

st.header("📍 PMU / Target Location Map")

st.caption(
    f"Current target: {target_name}"
)

land_map = folium.Map(
    location=[lat, lon],
    zoom_start=12,
    control_scale=True
)


# TARGET MARKER
folium.Marker(
    [lat, lon],
    tooltip="Selected PMU",
    popup=f"Target Location: {target_name}",
    icon=folium.Icon(
        color="blue",
        icon="bolt",
        prefix="fa"
    )
).add_to(land_map)


# 5 KM CIRCLE
folium.Circle(
    [lat, lon],
    radius=5000,
    color="green",
    fill=True,
    fill_opacity=0.10,
    tooltip="5 km reference zone"
).add_to(land_map)


# 8 KM CIRCLE
folium.Circle(
    [lat, lon],
    radius=8000,
    color="orange",
    fill=True,
    fill_opacity=0.06,
    tooltip="8 km reference zone"
).add_to(land_map)


# PARCEL MARKERS
colors = {
    "Good Fit": "green",
    "Worth a Look": "orange",
    "No Good": "red"
}


for _, parcel in ranked.iterrows():

    road_value = (
        f"{parcel['Road_Distance_KM']:.2f} km"
        if pd.notna(parcel["Road_Distance_KM"])
        else "Unavailable"
    )

    popup_html = (
        f"<b>{parcel['Parcel_ID']}</b><br>"
        f"Land Size: {parcel['Land_Size_Acres']} acres<br>"
        f"Straight-line Distance: "
        f"{parcel['Reference_Distance_KM']:.2f} km<br>"
        f"Road Distance: {road_value}<br>"
        f"Classification: {parcel['Classification']}<br>"
        f"Score: {parcel['Suitability_Score']}/4<br>"
        f"Distance Basis: {parcel['Distance_Basis']}<br>"
        "<i>Simulated demonstration parcel</i>"
    )

    folium.Marker(
        [
            parcel["Parcel_Latitude"],
            parcel["Parcel_Longitude"]
        ],
        tooltip=str(parcel["Parcel_ID"]),
        popup=folium.Popup(
            popup_html,
            max_width=280
        ),
        icon=folium.Icon(
            color=colors[parcel["Classification"]],
            icon="info-sign"
        )
    ).add_to(land_map)


st_folium(
    land_map,
    use_container_width=True,
    height=540,
    returned_objects=[]
)


st.caption(
    "Blue = Target | Green = 5 km | Orange = 8 km | "
    "Parcel markers = Simulated"
)


# ==========================================
# 18. DASHBOARD
# ==========================================

st.header("📊 Land Evaluation Dashboard")

c1, c2, c3, c4 = st.columns(4)

c1.metric(
    "Total Parcels",
    len(ranked)
)

c2.metric(
    "Good Fit",
    int((ranked["Classification"] == "Good Fit").sum())
)

c3.metric(
    "Worth a Look",
    int((ranked["Classification"] == "Worth a Look").sum())
)

c4.metric(
    "No Good",
    int((ranked["Classification"] == "No Good").sum())
)


# ==========================================
# 19. SMART LAND RANKING
# ==========================================

st.subheader("🏆 Smart Land Ranking")

if not ranked.empty:

    best = ranked.iloc[0]

    st.success(
        f"Top demonstration candidate: "
        f"{best['Parcel_ID']} - {best['Classification']}"
    )

    st.write(
        best["Evaluation_Reason"]
    )

# ==========================================
# LAND PARCEL RESULTS
# ==========================================

st.subheader("Land Parcel Results")

st.caption(
    "Compare demonstration parcels based on land size, "
    "road distance and suitability classification."
)

selected_categories = st.multiselect(
    "Filter by Classification",
    ["Good Fit", "Worth a Look", "No Good"],
    default=["Good Fit", "Worth a Look", "No Good"]
)

filtered = ranked[
    ranked["Classification"].isin(selected_categories)
].copy()


# RENAME TABLE COLUMNS
display_df = filtered.rename(columns={
    "Rank": "Rank",
    "Parcel_ID": "Parcel ID",
    "Land_Size_Acres": "Land Size (Acres)",
    "Reference_Distance_KM": "Straight-line Distance (km)",
    "Road_Distance_KM": "Road Distance (km)",
    "Distance_Basis": "Distance Source",
    "Classification": "Classification",
    "Suitability_Score": "Suitability Score",
    "Evaluation_Reason": "Evaluation Reason",
    "Data_Type": "Data Type",
    "Source": "Data Source"
})


display_columns = [
    "Rank",
    "Parcel ID",
    "Land Size (Acres)",
    "Straight-line Distance (km)",
    "Road Distance (km)",
    "Distance Source",
    "Classification",
    "Suitability Score",
    "Evaluation Reason",
    "Data Type",
    "Data Source"
]


st.dataframe(
    display_df[display_columns],
    use_container_width=True,
    hide_index=True,
    column_config={
        "Rank": st.column_config.NumberColumn(
            "Rank",
            format="%d"
        ),
        "Land Size (Acres)": st.column_config.NumberColumn(
            "Land Size (Acres)",
            format="%.2f"
        ),
        "Straight-line Distance (km)": st.column_config.NumberColumn(
            "Straight-line Distance (km)",
            format="%.2f km"
        ),
        "Road Distance (km)": st.column_config.NumberColumn(
            "Road Distance (km)",
            format="%.2f km"
        ),
        "Suitability Score": st.column_config.NumberColumn(
            "Suitability Score",
            format="%d / 4"
        )
    }
)

# ==========================================
# 21. LAND SIZE CHART
# ==========================================

st.subheader("Land Size Comparison")

if not filtered.empty:

    st.bar_chart(
        filtered.set_index("Parcel_ID")["Land_Size_Acres"]
    )

else:

    st.info(
        "No parcels match the selected classifications."
    )


# ==========================================
# 22. DOWNLOAD CSV
# ==========================================

st.subheader("📥 Download Evaluation Results")

export_df = filtered.copy()

csv_data = export_df.to_csv(
    index=False
).encode("utf-8-sig")


st.download_button(
    "Download CSV",
    data=csv_data,
    file_name="solarland_results.csv",
    mime="text/csv"
)


# ==========================================
# 23. DOWNLOAD EXCEL
# ==========================================

excel_buffer = BytesIO()

with pd.ExcelWriter(
    excel_buffer,
    engine="openpyxl"
) as writer:

    export_df.to_excel(
        writer,
        index=False,
        sheet_name="Land Results"
    )


st.download_button(
    "Download Excel",
    data=excel_buffer.getvalue(),
    file_name="solarland_results.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# ==========================================
# ABOUT THIS PROTOTYPE
# ==========================================

with st.expander("About This Prototype"):

    st.markdown("""
    ### Land Evaluation Criteria

    **1. Land Size**
    - Preferred size: 80–100 acres.
    - Smaller or larger parcels receive different evaluation scores.

    **2. Distance**
    - Good Fit: Within 5 km.
    - Worth a Look: Within 8 km.
    - No Good: Outside 8 km, subject to land size criteria.

    **3. Road Distance**
    - Calculated using OSRM when a route is available.
    - Straight-line distance is used as a fallback.

    ### Data Limitations

    - Parcel IDs and land sizes use demonstration data.
    - Parcel coordinates are simulated.
    - Road distances are calculated for simulated coordinates.
    - Actual vacant land has not been verified.
    - Real parcel, land-use and ownership data are required
      for an actual land assessment.
    """)
